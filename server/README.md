# Менеджер задач — REST API на FastAPI

[![CI](https://github.com/777werona-afk/vr-gaze-site/actions/workflows/ci.yml/badge.svg)](https://github.com/777werona-afk/vr-gaze-site/actions/workflows/ci.yml)

Курс «Разработка на Python и инженерия данных».
**Выполнила:** Кожевяткина Марина

- Практическая работа № 3 (Задание 7) — тесты, контейнеризация и CI/CD: раздел [«Задание 7»](#задание-7-тестирование-контейнеризация-и-cicd).
- Практическая работа № 2 (Задание 6) — REST API на FastAPI + PostgreSQL + SQLAlchemy + Pydantic: разделы начиная с [«Структура проекта»](#структура-проекта).

Сервер лежит в папке `server/` репозитория [vr-gaze-site](https://github.com/777werona-afk/vr-gaze-site) (основной проект — сайт с результатами по стабилизации взгляда в VR). Все команды ниже выполняются из папки `server/`.

Сервис хранит пользователей и их задачи и даёт REST API для работы с ними.
Стек: **FastAPI**, **PostgreSQL 16**, **SQLAlchemy 2.0** (async, `asyncpg`), **Pydantic v2**, **pydantic-settings**, **Alembic**, middleware на **Starlette**.

## Содержание

0. [Задание 7: тестирование, контейнеризация и CI/CD](#задание-7-тестирование-контейнеризация-и-cicd)
1. [Структура проекта](#структура-проекта)
2. [Инструкция по запуску](#инструкция-по-запуску)
3. [Эндпоинты](#эндпоинты)
4. [Скриншоты Swagger UI](#скриншоты-swagger-ui)
5. [Таблицы в БД](#таблицы-в-бд-dt)
6. [Middleware](#middleware)
7. [Автоматическая проверка и выкладка (CI)](#автоматическая-проверка-и-выкладка-ci)
8. [Ответы на контрольные вопросы (задание 6)](#ответы-на-контрольные-вопросы-задание-6)

## Задание 7: тестирование, контейнеризация и CI/CD

Практическая работа № 3: автоматические тесты на реальной PostgreSQL, Docker-образ и конвейер GitHub Actions с публикацией образа.

![CI](https://github.com/777werona-afk/vr-gaze-site/actions/workflows/ci.yml/badge.svg)

### Что сделано

| Шаг | Где | Что |
|-----|-----|-----|
| 1. Зависимости для разработки | `requirements-dev.txt` | `-r requirements.txt`, `pytest`, `pytest-asyncio`, `httpx`, `ruff` |
| 2. Конфигурация pytest | `pytest.ini` | `asyncio_mode = auto`, общий event loop на сессию, `testpaths = tests`, `pythonpath = .` |
| 3. Фикстуры | `tests/conftest.py` | отдельная БД `tasks_test` (создаётся автоматически), схема накатывается миграциями Alembic, перед каждым тестом `TRUNCATE ... RESTART IDENTITY`, `get_session` подменяется через `app.dependency_overrides`, клиент — `httpx.AsyncClient` + `ASGITransport` |
| 4. Тесты | `tests/test_api.py` | **16 тестов**: 9 обязательных + дополнительные (см. таблицу ниже) |
| 5. Dockerfile | `Dockerfile` | многоэтапная сборка `builder → test → runtime`, итоговый образ без компиляторов и кэша pip, запуск от пользователя `app` (uid 10001), `HEALTHCHECK` |
| 6. docker-compose | `docker-compose.yml` | `db` с healthcheck → `app` ждёт `service_healthy`, выполняет `alembic upgrade head`, затем запускает uvicorn; сервис `tests` (профиль `test`) гоняет pytest в контейнере |
| 7. CI | [`.github/workflows/ci.yml`](../.github/workflows/ci.yml) | job-ы `lint` → `test` → `build` (+ `deploy-ssh` из прошлых работ) |
| 8. Проверка | [PR #1](https://github.com/777werona-afk/vr-gaze-site/pull/1) | PR с намеренно сломанным тестом → pipeline «красный», исправление → «зелёный», merge |

Обязательные тесты (шаг 4):

| № | Тест | Что проверяет |
|---|------|---------------|
| 1 | `test_create_user_201` | создание пользователя — 201 |
| 2 | `test_duplicate_email_409` | повторный email — 409 |
| 3 | `test_invalid_email_422` | невалидный email — 422 |
| 4 | `test_create_task_201` | создание задачи — 201, `done=false` по умолчанию |
| 5 | `test_create_task_unknown_owner_404` | задача с несуществующим владельцем — 404 |
| 6 | `test_filter_done_and_pagination` | фильтр `done` и пагинация `limit`/`offset` |
| 7 | `test_patch_changes_only_sent_fields` | PATCH меняет только переданные поля |
| 8 | `test_delete_then_get_404` | DELETE (204), затем GET — 404 |
| 9 | `test_process_time_header` | заголовок `X-Process-Time` |

Дополнительно: GET пользователя 200/404, `limit` вне диапазона 1–100 → 422, длина `title` (пустой и 201 символ) → 422, явный `null` в PATCH → 422, PATCH/DELETE несуществующей задачи → 404.

### Как устроен CI

```
push / pull_request ──► lint (ruff check + ruff format --check)
                    └─► test (PostgreSQL 16 как service-контейнер, alembic upgrade head, pytest -v)
                              │  needs: [lint, test]
                              ▼
                        build: docker compose up --build --wait  (db → миграции → app)
                               смоук-тест запущенного контейнера
                               docker compose --profile test run tests  (pytest внутри Docker)
                               docker build (target runtime)
                               только push в main: push в GHCR и Docker Hub
                              │  needs: build, только main
                              ▼
                        deploy-ssh: выкладка кода action-ом rsync-ssh-deploy
```

- На pull request и в других ветках образ только собирается и проверяется; публикуется он только при push в `main`.
- В GHCR образ публикуется с токеном `GITHUB_TOKEN` (право `packages: write` выдаётся только job-у `build`), в Docker Hub — с секретами репозитория `DOCKERHUB_USERNAME` и `DOCKERHUB_TOKEN`.
- Теги образа: `latest` и `sha-<коммит>`.

### Команды

**Тесты локально** (нужны Python 3.11+ и Docker для базы):

```bash
cd server
docker compose up -d db                  # PostgreSQL 16
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
pytest -v                                # БД tasks_test создаётся автоматически
ruff check . && ruff format --check .    # линтер, как в CI
```

Адрес тестовой БД можно переопределить переменной `TEST_DATABASE_URL` (по умолчанию `postgresql+asyncpg://app:app@localhost:5432/tasks_test`).

**Через Docker Compose:**

```bash
cd server
docker compose up -d --build                      # db -> миграции -> app, API: http://127.0.0.1:8000/docs
docker compose --profile test run --rm tests      # тесты внутри контейнера (образ target test)
docker compose --profile test down -v             # остановить всё и удалить данные
```

**Готовый образ:**

```bash
docker pull ghcr.io/777werona-afk/task-manager-api:latest
docker pull mkkey22/task-manager-api:latest
```

### Опубликованные образы

- GHCR: <https://github.com/777werona-afk/vr-gaze-site/pkgs/container/task-manager-api> (`ghcr.io/777werona-afk/task-manager-api`)
- Docker Hub: <https://hub.docker.com/r/mkkey22/task-manager-api> (`mkkey22/task-manager-api`)

### Скриншоты pipeline

**Запуски CI для PR #1**: сначала «красный» (#5, намеренно сломанный тест), после исправления — «зелёный» (#7).

![Запуски CI для PR #1](docs/screenshots/ci_runs_pr.jpg)

**Успешный pipeline** — PR #1 после исправления теста: lint, test и build зелёные (deploy-ssh на pull request не запускается).

![Успешный pipeline](docs/screenshots/ci_green.jpg)

**«Упавший» pipeline из шага 8** — PR #1 с намеренно сломанным тестом (`assert resp.status_code == 200` вместо 201): job `test` красный, `build` и `deploy-ssh` не запускались.

![Упавший pipeline](docs/screenshots/ci_red_summary.jpg)

![Лог упавшего теста](docs/screenshots/ci_red_log.jpg)

### Ответы на контрольные вопросы (задание 7)

**1. Чем CI отличается от CD (continuous delivery и continuous deployment)?**

CI (continuous integration) — изменения часто вливаются в общую ветку, и на каждый push или pull request автоматически запускаются сборка, линтер и тесты; цель — сразу узнать, что изменение что-то сломало. Continuous delivery идёт дальше: каждое изменение, прошедшее pipeline, автоматически доводится до готового к выпуску артефакта (здесь — Docker-образ в GHCR и Docker Hub), но выкладка в production остаётся ручным решением. Continuous deployment убирает и этот ручной шаг: всё, что прошло pipeline, автоматически выкладывается в production. В этой работе job-ы `lint` и `test` — это CI, публикация образа в `build` — continuous delivery.

**2. Как работает `dependency_overrides` и зачем он нужен в тестах?**

`app.dependency_overrides` — словарь у приложения FastAPI: ключ — исходная зависимость, значение — функция-замена. Когда FastAPI разрешает `Depends(get_session)`, он сначала смотрит в этот словарь и, если замена есть, вызывает её. В тестах так подменяется сессия: вместо рабочей БД обработчики получают сессию к `tasks_test`, а код приложения не меняется. Так же можно подменить авторизацию или внешние сервисы. После теста словарь очищается (`app.dependency_overrides.clear()`), чтобы подмена не влияла на другие тесты.

**3. Зачем нужна многоэтапная сборка образа?**

Чтобы отделить окружение сборки от окружения запуска. На этапе `builder` ставятся зависимости (там могут понадобиться компиляторы и кэш pip), а в итоговый образ `runtime` копируется только готовое виртуальное окружение и код. Образ получается меньше, быстрее скачивается, в нём меньше пакетов, а значит меньше уязвимостей и поверхности атаки. Кроме того, из одного Dockerfile собираются разные цели: здесь `test` (с pytest и тестами) для CI и `runtime` для production, а общие слои кэшируются.

**4. Почему контейнер не следует запускать от root?**

Это принцип минимальных привилегий. Если в приложении найдётся уязвимость с выполнением кода, злоумышленник получит права процесса. Root внутри контейнера без user namespaces — это тот же root на хосте: при ошибке конфигурации (примонтированный каталог хоста, `docker.sock`, лишние capabilities) или уязвимости ядра он может выйти за пределы контейнера и изменить файлы хоста. Непривилегированный пользователь ограничивает ущерб. Многие платформы (например, Kubernetes с политикой `restricted`, OpenShift) вообще не запускают контейнеры от root. Здесь процесс работает от пользователя `app` (uid 10001), файлы приложения принадлежат ему, порт 8000 не требует привилегий.

**5. Как в GitHub Actions передаются секреты и почему их нельзя хранить в репозитории?**

Секреты хранятся в зашифрованном виде в настройках репозитория (окружения или организации) и попадают в workflow только через выражение `${{ secrets.ИМЯ }}` — в переменные окружения шага или входы action, как `DOCKERHUB_TOKEN` здесь. В логах их значения автоматически маскируются `***`, а pull request из форков их не получают. Токен `GITHUB_TOKEN` GitHub выдаёт сам на время job-а с правами из `permissions`. Хранить секреты в репозитории нельзя: история git сохраняется навсегда и копируется в каждый клон и форк, в публичном репозитории ключ сразу виден всем (боты находят утёкшие ключи за минуты), удаление коммитом не помогает — ключ остаётся в истории, и его придётся перевыпускать.

**6. Что произойдёт с job-ом build, если упадёт test? Где это задаётся?**

`build` не запустится: он будет помечен как пропущенный (skipped), образ не соберётся и не опубликуется, а весь workflow получит статус failure — это видно на скриншоте «упавшего» pipeline. Задаётся это в `ci.yml` строкой `needs: [lint, test]` у job-а `build`: job ждёт завершения перечисленных и по умолчанию (неявное условие `if: success()`) выполняется, только если они все успешны. Так же `deploy-ssh` зависит от `build`. Изменить поведение можно условием `if:` (например, `if: always()`), но для публикации образа это было бы ошибкой.

**7. Где лучше применять миграции: при старте контейнера или отдельным шагом в CD? Каковы плюсы и минусы каждого варианта?**

*При старте контейнера* (так сделано в `docker-compose.yml`: `alembic upgrade head && uvicorn ...`). Плюсы: просто, схема всегда соответствует коду, удобно для разработки и одного экземпляра. Минусы: при нескольких репликах миграции запускаются одновременно (гонка, нужны блокировки), старт медленнее, приложению нужны права на DDL, неудачная миграция приводит к бесконечным перезапускам контейнера, откат миграций привязан к выкладке приложения.

*Отдельным шагом в CD* (отдельный job или одноразовый контейнер перед выкладкой новой версии). Плюсы: миграция выполняется один раз и под контролем, с отдельными правами и логами; если она упала, выкладка останавливается до запуска новой версии. Минусы: pipeline сложнее; пока идёт миграция, работает старая версия приложения, поэтому миграции должны быть обратно совместимыми (подход expand/contract).

Итого: для локальной разработки и учебного стенда удобен запуск при старте, для production с несколькими экземплярами лучше отдельный шаг в CD.

## Структура проекта

```
server/
├── app/
│   ├── __init__.py
│   ├── main.py          # создание приложения, middleware, подключение роутеров
│   ├── config.py        # настройки (pydantic-settings), DATABASE_URL из окружения
│   ├── db.py            # асинхронный движок, фабрика сессий, Base, get_session
│   ├── models.py        # ORM-модели User и Task (Mapped / mapped_column)
│   ├── schemas.py       # Pydantic-схемы *Create / *Read / *Update
│   └── routers/
│       ├── users.py
│       └── tasks.py
├── migrations/          # Alembic (alembic init -t async migrations)
│   └── versions/        # первая миграция создана через --autogenerate
├── tests/
│   ├── conftest.py      # тестовая БД tasks_test, миграции, чистые таблицы, dependency_overrides
│   └── test_api.py      # 16 тестов API (9 обязательных + дополнительные)
├── scripts/smoke_test.py  # смоук-тест запущенного сервиса (только стандартная библиотека)
├── docs/screenshots/    # скриншоты для отчёта
├── Dockerfile           # многоэтапная сборка: builder -> test -> runtime (non-root)
├── docker-compose.yml   # db (healthcheck) -> миграции -> app; tests по профилю test
├── alembic.ini
├── pytest.ini
├── ruff.toml
├── requirements.txt
├── requirements-dev.txt
├── .dockerignore
├── .env.example
└── README.md
```

### Модель данных

| Сущность | Поля |
|----------|------|
| `User` | `id` (PK), `email` (уникальный), `name`, `created_at` |
| `Task` | `id` (PK), `title` (1–200 символов), `description` (необязательно), `done` (bool, по умолчанию `false`), `created_at`, `owner_id` (FK → `users.id`) |

Связь: один пользователь — много задач (`relationship(..., back_populates=...)`, при удалении пользователя его задачи удаляются каскадно).

## Инструкция по запуску

Нужны Python 3.11+, Docker и Docker Compose, Git.

**1. Клонировать репозиторий и перейти в папку сервера**

```bash
git clone https://github.com/777werona-afk/vr-gaze-site.git
cd vr-gaze-site/server
```

**2. Запустить PostgreSQL и проверить, что база доступна**

```bash
docker compose up -d db
docker compose exec db psql -U app -d tasks -c "select 1"
```

**3. Создать виртуальное окружение и установить зависимости**

```bash
python -m venv .venv
# Linux / macOS:
source .venv/bin/activate
# Windows (PowerShell):
# .venv\Scripts\Activate.ps1

pip install -r requirements.txt
```

> В `requirements.txt` указаны `pydantic[email]` и `sqlalchemy[asyncio]`: тип `EmailStr` требует пакет `email-validator`, а асинхронный режим SQLAlchemy 2.1 — пакет `greenlet`; оба ставятся только с этими extras.

**4. Создать файл `.env` со строкой подключения**

```bash
cp .env.example .env          # Windows: copy .env.example .env
```

В `.env` одна переменная: `DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/tasks`. В коде строки подключения нет, её читает `pydantic-settings` (`app/config.py`).

**5. Применить миграции (таблицы создаёт Alembic, а не `create_all`)**

```bash
alembic upgrade head
```

**6. Запустить сервис**

```bash
uvicorn app.main:app --reload
```

**7. Открыть Swagger UI:** <http://127.0.0.1:8000/docs>

**8. Посмотреть таблицы в БД**

```bash
docker compose exec db psql -U app -d tasks -c "\dt"
```

**9. (необязательно) Прогнать смоук-тест всех эндпоинтов** — в другом терминале, пока сервис запущен:

```bash
python scripts/smoke_test.py http://127.0.0.1:8000
```

Остановить базу: `docker compose down` (данные сохранятся в volume `pgdata`; `docker compose down -v` удалит и их).

Как создавались миграции (уже сделано, повторять не нужно):

```bash
alembic init -t async migrations
alembic revision --autogenerate -m "create users and tasks"
alembic upgrade head
```

## Эндпоинты

| Метод | Путь | Описание | Коды ответа |
|-------|------|----------|-------------|
| POST | `/users` | создать пользователя | 201, 409 (email занят), 422 |
| GET | `/users/{id}` | получить пользователя | 200, 404 |
| POST | `/tasks` | создать задачу | 201, 404 (нет владельца), 422 |
| GET | `/tasks` | список задач, фильтры `done`, `owner_id`, пагинация `limit` (1–100), `offset` | 200 (422 при неверных параметрах) |
| GET | `/tasks/{id}` | получить задачу | 200, 404 |
| PATCH | `/tasks/{id}` | частично обновить задачу | 200, 404, 422 |
| DELETE | `/tasks/{id}` | удалить задачу | 204, 404 |

Сессия БД во всех обработчиках получается только через `Depends(get_session)`, ошибки возвращаются через `HTTPException`.
В `PATCH` изменяются только переданные поля (`model_dump(exclude_unset=True)`); явный `null` для `title` или `done` отклоняется с кодом 422.

## Скриншоты Swagger UI

Все запросы выполнены через Swagger UI («Try it out → Execute») на запущенном сервисе с PostgreSQL 16.

**Общий вид `/docs`**

![Swagger UI — список эндпоинтов](docs/screenshots/01_swagger_overview.png)

**POST /users → 201 Created**

![POST /users 201](docs/screenshots/02_post_users_201.png)

**POST /users с тем же email → 409 Conflict**

![POST /users 409](docs/screenshots/03_post_users_409.png)

**GET /users/1 → 200 OK**

![GET /users/1 200](docs/screenshots/04_get_user_200.png)

**GET /users/999 → 404 Not Found**

![GET /users/999 404](docs/screenshots/05_get_user_404.png)

**POST /tasks → 201 Created**

![POST /tasks 201](docs/screenshots/06_post_task_201.png)

<details>
<summary>Вторая задача (POST /tasks → 201), нужна для проверки фильтров и удаления</summary>

![POST /tasks 201 вторая задача](docs/screenshots/07_post_task_201_second.png)

</details>

**POST /tasks с несуществующим владельцем → 404 Not Found**

![POST /tasks 404](docs/screenshots/08_post_task_404_owner.png)

**GET /tasks с фильтрами `done=false&owner_id=1&limit=10&offset=0` → 200 OK**

![GET /tasks 200](docs/screenshots/09_get_tasks_filters_200.png)

**GET /tasks/1 → 200 OK**

![GET /tasks/1 200](docs/screenshots/10_get_task_200.png)

**PATCH /tasks/1 `{"done": true}` → 200 OK**

![PATCH /tasks/1 200](docs/screenshots/11_patch_task_200.png)

**DELETE /tasks/2 → 204 No Content**

![DELETE /tasks/2 204](docs/screenshots/12_delete_task_204.png)

**GET /tasks/2 после удаления → 404 Not Found**

![GET /tasks/2 404](docs/screenshots/13_get_task_404.png)

## Таблицы в БД (`\dt`)

Таблицы `users` и `tasks` созданы миграцией Alembic, `alembic_version` — служебная таблица Alembic.

![psql \dt](docs/screenshots/14_psql_dt.png)

## Middleware

`ProcessTimeMiddleware` (наследник `starlette.middleware.base.BaseHTTPMiddleware`, файл `app/main.py`):

- добавляет в каждый ответ заголовок `X-Process-Time` (время обработки в секундах; виден на скриншотах выше в блоке *Response headers*);
- пишет в лог метод, путь, статус и время обработки запроса.

![Лог middleware](docs/screenshots/15_middleware_log.png)

## Автоматическая проверка и выкладка (CI)

Начиная с задания 7 сервер проверяется workflow [`.github/workflows/ci.yml`](../.github/workflows/ci.yml) (job-ы lint, test, build, deploy-ssh) — подробно в разделе [«Задание 7»](#задание-7-тестирование-контейнеризация-и-cicd). Последний job выкладывает код сервера по SSH собственным action [rsync-ssh-deploy](https://github.com/777werona-afk/rsync-ssh-deploy) (`@v1`): постоянного сервера нет, поэтому выкладка идёт на `sshd`, поднятый на раннере; для реального сервера достаточно подставить секреты `DEPLOY_HOST`, `DEPLOY_USER`, `DEPLOY_KEY`, `DEPLOY_KNOWN_HOSTS` и путь.

## Ответы на контрольные вопросы (задание 6)

**1. Чем FastAPI отличается от Starlette и какие компоненты Starlette он использует?**

Starlette — лёгкий ASGI-фреймворк: маршрутизация, запросы и ответы, middleware, WebSocket, фоновые задачи, статика, тестовый клиент. FastAPI построен поверх него (класс `FastAPI` наследуется от `Starlette`) и добавляет то, чего в Starlette нет: объявление параметров через аннотации типов, валидацию и сериализацию данных через Pydantic, систему зависимостей `Depends`, автоматическую генерацию OpenAPI-схемы и документацию Swagger UI / ReDoc. От Starlette FastAPI использует `Request` и `Response` (включая `JSONResponse`), маршрутизацию, middleware (в этой работе `BaseHTTPMiddleware`), исключения (`HTTPException` FastAPI наследуется от Starlette-версии), `BackgroundTasks`, WebSocket, `StaticFiles` и `TestClient`.

**2. Зачем разделять схемы Create, Read и Update?**

У каждой операции свой набор полей и свои правила. В `*Create` нет полей, которые назначает сервер (`id`, `created_at`), и есть обязательные поля. `*Read` описывает, что сервис отдаёт наружу: там есть `id` и `created_at`, и туда никогда не попадут служебные поля, которые нельзя показывать (например, хэш пароля). В `*Update` все поля необязательны, потому что `PATCH` меняет только то, что прислали. Одна общая схема заставила бы либо разрешать клиенту присылать `id`, либо делать обязательные поля необязательными везде. Кроме того, каждая схема отдельно и точно описана в OpenAPI.

**3. Что делает `from_attributes=True`?**

Разрешает Pydantic создавать модель из любого объекта, читая его атрибуты (`obj.id`, `obj.title`), а не только из словаря. Благодаря этому ORM-объект SQLAlchemy можно прямо вернуть из обработчика: FastAPI превратит его в `TaskRead` через `TaskRead.model_validate(task)`. В Pydantic v1 эта настройка называлась `orm_mode = True`.

**4. Почему сессия передаётся через `Depends`, а не создаётся глобально?**

Сессия SQLAlchemy — это единица работы с собственной транзакцией и кэшем объектов, и она не потокобезопасна. Одна глобальная сессия на все одновременные запросы приводила бы к смешиванию транзакций и данных разных пользователей. `Depends(get_session)` создаёт свою сессию на каждый запрос, а благодаря `yield` гарантированно закрывает её после ответа, даже если произошла ошибка. К тому же зависимость легко подменить в тестах (`app.dependency_overrides`), например на сессию к тестовой базе, а обработчик явно объявляет, что ему нужна БД.

**5. Чем `exclude_unset=True` отличается от `exclude_none=True`?**

`exclude_unset=True` исключает поля, которые клиент вообще не передал: остаются только явно заданные, даже если в них `null`. `exclude_none=True` исключает поля со значением `None`, неважно, переданы они явно или взялись из значения по умолчанию. Для `PATCH` правильно использовать `exclude_unset`: он отличает «поле не трогать» (его нет в запросе) от «очистить поле» (`"description": null`). С `exclude_none` очистить необязательное поле через `PATCH` было бы невозможно.

**6. Почему в production таблицы не создают через `create_all`?**

`Base.metadata.create_all()` умеет только создавать отсутствующие таблицы. Он не изменяет уже существующие (не добавит колонку, не поменяет тип, не удалит индекс), не хранит историю изменений схемы и не позволяет откатиться. В production в таблицах лежат данные, и схему нужно менять постепенно и воспроизводимо: на всех окружениях одинаково, с возможностью отката и с миграцией самих данных. Это делают миграции Alembic: каждая версия схемы — отдельный файл в репозитории, который проходит ревью, а `alembic upgrade head` / `alembic downgrade -1` применяют и откатывают изменения, отмечая текущую версию в таблице `alembic_version`.
