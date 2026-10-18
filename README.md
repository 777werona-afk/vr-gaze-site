# Стабилизация взгляда в VR — сайт с результатами и сервер

[![Build and deploy docs](https://github.com/777werona-afk/vr-gaze-site/actions/workflows/deploy.yml/badge.svg)](https://github.com/777werona-afk/vr-gaze-site/actions/workflows/deploy.yml)
[![Server (FastAPI) — test and deploy](https://github.com/777werona-afk/vr-gaze-site/actions/workflows/server.yml/badge.svg)](https://github.com/777werona-afk/vr-gaze-site/actions/workflows/server.yml)

Репозиторий проекта по курсу «Разработка на Python и инженерия данных». В нём две части:

| Часть | Что это | Задание |
|---|---|---|
| Сайт (корень репозитория) | статический сайт на MkDocs (тема Material) с результатами обработки записи взгляда в VR | Задание 3: «Генераторы статических сайтов для публикации результатов исследований» |
| [`server/`](server/) | REST API «Менеджер задач» на FastAPI + PostgreSQL + SQLAlchemy 2.0 + Pydantic v2, миграции Alembic | Задание 6: «Разработка REST API на FastAPI с использованием PostgreSQL, SQLAlchemy и Pydantic» → **[отчёт: server/README.md](server/README.md)** |

- Сайт: https://777werona-afk.github.io/vr-gaze-site/
- Выкладка по SSH: собственный GitHub Action [rsync-ssh-deploy](https://github.com/777werona-afk/rsync-ssh-deploy) (подключён как `777werona-afk/rsync-ssh-deploy@v1` и для сайта, и для сервера)
- Автор: Кожевяткина Марина Алексеевна

## Сайт: быстрый старт

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
make serve      # расчёт по data/raw + предпросмотр сайта
make strict     # строгая сборка, как в CI
```

Данные: положите CSV-логи взгляда (`timestamp, gaze_x, gaze_y, gaze_z, pupil, openness`) в `data/raw/`.
Если папка пуста, скрипт использует синтетические демо-данные, и сайт показывает баннер «ДЕМО-ДАННЫЕ».
Версию набора данных можно указать в файле `data/DATASET_VERSION`.

## Сервер: быстрый старт

Подробная инструкция, скриншоты Swagger UI и `\dt`, ответы на контрольные вопросы — в [server/README.md](server/README.md).

```bash
cd server
docker compose up -d db                 # PostgreSQL 16
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env                    # DATABASE_URL для подключения к БД
alembic upgrade head                    # таблицы создаются миграцией
uvicorn app.main:app --reload           # Swagger UI: http://127.0.0.1:8000/docs
```

## Структура

| Путь | Назначение |
|---|---|
| `docs/` | страницы сайта |
| `scripts/analyze.py` | расчёт, таблицы, графики, метка версии, кэш |
| `scripts/make_demo_data.py` | генератор синтетических демо-данных |
| `data/raw/` | CSV-логи записи взгляда |
| `generated/` | таблица и метка версии (создаются скриптом, не коммитятся) |
| `listings/` | листинги action `rsync-ssh-deploy` (`action.yml`, тестовый и релизный workflow) для отчёта |
| `server/` | REST API «Менеджер задач»: `app/` (FastAPI, модели, схемы, роутеры), `migrations/` (Alembic), `tests/`, `docker-compose.yml` |
| `.github/workflows/deploy.yml` | сайт: lint → build → deploy (GitHub Pages, Cloudflare Pages, SSH через `rsync-ssh-deploy`) |
| `.github/workflows/server.yml` | сервер: PostgreSQL 16 → миграции → смоук-тест API → выкладка по SSH через `rsync-ssh-deploy` |

## CI/CD

- **`deploy.yml`** запускается при изменениях сайта (изменения только в `server/` его не трогают): расчёт по данным, строгая сборка MkDocs, выкладка на GitHub Pages и Cloudflare Pages, выкладка по SSH собственным action с проверкой результата.
- **`server.yml`** запускается при изменениях в `server/`: поднимает PostgreSQL 16 как сервис, применяет миграции Alembic, запускает API и прогоняет `server/tests/smoke_test.py` (все эндпоинты и коды ответа), затем выкладывает код сервера по SSH тем же action `rsync-ssh-deploy`.

Для выкладки на реальный сервер (например, Helios) в обоих workflow достаточно заменить `host`, `user`, `path` и ключ на секреты репозитория (`DEPLOY_HOST`, `DEPLOY_USER`, `DEPLOY_KEY`, `DEPLOY_KNOWN_HOSTS`).

## Лицензии

Контент — CC BY 4.0 (`LICENSE-CONTENT.md`), код — MIT (`LICENSE`).
