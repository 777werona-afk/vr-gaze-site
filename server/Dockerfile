# syntax=docker/dockerfile:1
# Многоэтапная сборка образа REST API «Менеджер задач».
#   builder — ставит зависимости в виртуальное окружение (компиляторы и кэш pip в итоговый образ не попадают)
#   test    — то же окружение + dev-зависимости и тесты (docker compose --profile test run --rm tests)
#   runtime — итоговый образ: только venv и код, запуск от непривилегированного пользователя

ARG PYTHON_VERSION=3.12

# ---------------------------------------------------------------- base
FROM python:${PYTHON_VERSION}-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    VIRTUAL_ENV=/opt/venv \
    PATH="/opt/venv/bin:$PATH"
# системный пользователь без пароля и без логин-оболочки
RUN groupadd --system --gid 10001 app \
 && useradd --system --uid 10001 --gid app --home-dir /app --shell /usr/sbin/nologin app \
 && mkdir /app && chown app:app /app
WORKDIR /app

# ---------------------------------------------------------------- builder
FROM base AS builder
RUN python -m venv "$VIRTUAL_ENV"
COPY requirements.txt .
RUN pip install -r requirements.txt

# ---------------------------------------------------------------- test
FROM base AS test
COPY --from=builder /opt/venv /opt/venv
COPY requirements.txt requirements-dev.txt ./
RUN pip install -r requirements-dev.txt
COPY --chown=app:app . .
USER app
CMD ["pytest", "-v"]

# ---------------------------------------------------------------- runtime (итоговый образ)
FROM base AS runtime
LABEL org.opencontainers.image.title="task-manager-api" \
      org.opencontainers.image.description="REST API «Менеджер задач»: FastAPI + PostgreSQL + SQLAlchemy 2.0 + Pydantic v2" \
      org.opencontainers.image.source="https://github.com/777werona-afk/vr-gaze-site" \
      org.opencontainers.image.authors="Кожевяткина Марина" \
      org.opencontainers.image.licenses="MIT"
COPY --from=builder /opt/venv /opt/venv
COPY --chown=app:app app ./app
COPY --chown=app:app migrations ./migrations
COPY --chown=app:app alembic.ini ./
USER app
EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=3s --start-period=10s --retries=5 \
  CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/openapi.json', timeout=2)"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
