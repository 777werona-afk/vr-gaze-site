# Менеджер задач — REST API на FastAPI

Практическая работа № 2 (Задание 6) по курсу «Разработка на Python и инженерия данных».
**Выполнила:** Кожевяткина Марина

[![Server (FastAPI) — test and deploy](https://github.com/777werona-afk/vr-gaze-site/actions/workflows/server.yml/badge.svg)](https://github.com/777werona-afk/vr-gaze-site/actions/workflows/server.yml)

Сервер лежит в папке `server/` репозитория [vr-gaze-site](https://github.com/777werona-afk/vr-gaze-site) (основной проект — сайт с результатами по стабилизации взгляда в VR). Все команды ниже выполняются из папки `server/`.

Сервис хранит пользователей и их задачи и даёт REST API для работы с ними.
Стек: **FastAPI**, **PostgreSQL 16**, **SQLAlchemy 2.0** (async, `asyncpg`), **Pydantic v2**, **pydantic-settings**, **Alembic**, middleware на **Starlette**.

## Содержание

1. [Структура проекта](#структура-проекта)
2. [Инструкция по запуску](#инструкция-по-запуску)
3. [Эндпоинты](#эндпоинты)
4. [Скриншоты Swagger UI](#скриншоты-swagger-ui)
5. [Таблицы в БД](#таблицы-в-бд-dt)
6. [Middleware](#middleware)
7. [Автоматическая проверка и выкладка (CI)](#автоматическая-проверка-и-выкладка-ci)
8. [Ответы на контрольные вопросы](#ответы-на-контрольные-вопросы)

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
├── docs/screenshots/    # скриншоты для отчёта
├── scripts/smoke_test.py  # смоук-тест всех эндпоинтов (только стандартная библиотека)
├── alembic.ini
├── docker-compose.yml
├── requirements.txt
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

> В `requirements.txt` указан `pydantic[email]`, а не просто `pydantic`: тип `EmailStr` требует пакет `email-validator`, который ставится с этим extra.

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

Workflow [`.github/workflows/server.yml`](../.github/workflows/server.yml) запускается при изменениях в `server/`:

1. **test** — поднимает PostgreSQL 16 как сервис, ставит зависимости, применяет миграции (`alembic upgrade head`), выводит `\dt`, запускает `uvicorn` и прогоняет `scripts/smoke_test.py`: 22 проверки всех эндпоинтов и кодов ответа (201, 200, 204, 404, 409, 422) и наличие заголовка `X-Process-Time`.
2. **deploy-ssh** — выкладывает код сервера по SSH собственным action [rsync-ssh-deploy](https://github.com/777werona-afk/rsync-ssh-deploy) (`@v1`), так же как сайт в `deploy.yml`. Постоянного сервера нет, поэтому выкладка идёт на `sshd`, поднятый на раннере; для реального сервера достаточно подставить секреты `DEPLOY_HOST`, `DEPLOY_USER`, `DEPLOY_KEY`, `DEPLOY_KNOWN_HOSTS` и путь.

## Ответы на контрольные вопросы

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
