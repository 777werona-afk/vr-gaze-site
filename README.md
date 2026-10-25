# Стабилизация взгляда в VR — сайт с результатами и сервер

[![Build and deploy docs](https://github.com/777werona-afk/vr-gaze-site/actions/workflows/deploy.yml/badge.svg)](https://github.com/777werona-afk/vr-gaze-site/actions/workflows/deploy.yml)
[![CI](https://github.com/777werona-afk/vr-gaze-site/actions/workflows/ci.yml/badge.svg)](https://github.com/777werona-afk/vr-gaze-site/actions/workflows/ci.yml)

Репозиторий проекта по курсу «Разработка на Python и инженерия данных». В нём две части:

| Часть | Что это | Задание |
|---|---|---|
| Сайт (корень репозитория) | статический сайт на MkDocs (тема Material) с результатами обработки записи взгляда в VR | Задание 3: «Генераторы статических сайтов для публикации результатов исследований» |
| [`server/`](server/) | REST API «Менеджер задач» на FastAPI + PostgreSQL + SQLAlchemy 2.0 + Pydantic v2, миграции Alembic | Задание 6: «Разработка REST API на FastAPI с использованием PostgreSQL, SQLAlchemy и Pydantic» → **[отчёт: server/README.md](server/README.md)** |
| [`server/`](server/) + `ci.yml` | тесты на PostgreSQL, Docker-образ, docker-compose, CI/CD с публикацией образа в GHCR и Docker Hub | Задание 7: «Тестирование, контейнеризация и CI/CD для FastAPI-приложения» → **[отчёт: server/README.md#задание-7](server/README.md#задание-7-тестирование-контейнеризация-и-cicd)** |

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
docker compose up -d --build            # PostgreSQL 16 -> миграции -> API
# Swagger UI: http://127.0.0.1:8000/docs
docker compose --profile test run --rm tests   # тесты в контейнере
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
| `server/` | REST API «Менеджер задач»: `app/` (FastAPI, модели, схемы, роутеры), `migrations/` (Alembic), `tests/` (pytest), `Dockerfile`, `docker-compose.yml` |
| `.github/workflows/deploy.yml` | сайт: lint → build → deploy (GitHub Pages, Cloudflare Pages, SSH через `rsync-ssh-deploy`) |
| `.github/workflows/ci.yml` | сервер: lint → test (PostgreSQL 16) → build (docker compose, публикация образа в GHCR и Docker Hub) → выкладка по SSH через `rsync-ssh-deploy` |

## CI/CD

- **`deploy.yml`** запускается при изменениях сайта (изменения только в `server/` его не трогают): расчёт по данным, строгая сборка MkDocs, выкладка на GitHub Pages и Cloudflare Pages, выкладка по SSH собственным action с проверкой результата.
- **`ci.yml`** запускается на каждый push и pull request: `lint` (ruff) и `test` (pytest на PostgreSQL 16), затем `build` — весь стек через docker compose, тесты внутри контейнера, сборка образа; при push в `main` образ публикуется в GHCR и Docker Hub, после чего `deploy-ssh` выкладывает код сервера тем же action `rsync-ssh-deploy`.

Для выкладки на реальный сервер (например, Helios) в обоих workflow достаточно заменить `host`, `user`, `path` и ключ на секреты репозитория (`DEPLOY_HOST`, `DEPLOY_USER`, `DEPLOY_KEY`, `DEPLOY_KNOWN_HOSTS`).

## Лицензии

Контент — CC BY 4.0 (`LICENSE-CONTENT.md`), код — MIT (`LICENSE`).
