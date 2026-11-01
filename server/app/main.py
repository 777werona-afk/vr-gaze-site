"""Точка входа: создание приложения, middleware и подключение роутеров."""

import logging
import time
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.base import BaseHTTPMiddleware

from app.routers import analytics, exhibits, groups, participants, sessions, tasks, users
from app.services.errors import DomainError

STATIC_DIR = Path(__file__).parent / "static"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("app.requests")


class ProcessTimeMiddleware(BaseHTTPMiddleware):
    """Starlette-middleware: заголовок X-Process-Time и строка в логе на каждый запрос."""

    async def dispatch(self, request: Request, call_next):
        start = time.perf_counter()
        response = await call_next(request)
        elapsed = time.perf_counter() - start
        response.headers["X-Process-Time"] = f"{elapsed:.4f}"
        logger.info(
            "%s %s -> %s (%.1f ms)",
            request.method,
            request.url.path,
            response.status_code,
            elapsed * 1000,
        )
        return response


app = FastAPI(
    title="VR-музей: стабилизация взгляда",
    description=(
        "Информационная система для сбора и анализа записей взгляда в виртуальном музее. "
        "Итоговый показатель по сессии: **есть дестабилизация взгляда — да или нет** "
        "(RMS колебаний в полосе тремора 4-12 Гц выше порога). "
        "Ошибки приходят в едином формате: поля `detail` (описание) и `code` (код ошибки). "
        "Эндпоинты `/users` и `/tasks` остались от учебных заданий 6-7."
    ),
    version="2.0.0",
)
app.add_middleware(ProcessTimeMiddleware)


# ---------- единый формат ошибок: {"detail": ..., "code": ...} ----------
# Ключ detail сохранён для совместимости с FastAPI и старыми тестами, code — машинный код.


def error_response(status_code: int, detail, code: str, headers: dict | None = None):
    return JSONResponse(
        status_code=status_code, content={"detail": detail, "code": code}, headers=headers
    )


@app.exception_handler(DomainError)
async def handle_domain_error(request: Request, exc: DomainError):
    return error_response(exc.status_code, exc.message, exc.code)


@app.exception_handler(StarletteHTTPException)
async def handle_http_error(request: Request, exc: StarletteHTTPException):
    return error_response(exc.status_code, exc.detail, f"http_{exc.status_code}", exc.headers)


@app.exception_handler(RequestValidationError)
async def handle_validation_error(request: Request, exc: RequestValidationError):
    return error_response(422, jsonable_encoder(exc.errors()), "validation_error")


# ---------- роутеры ----------
app.include_router(groups.router)
app.include_router(participants.router)
app.include_router(exhibits.router)
app.include_router(sessions.router)
app.include_router(analytics.router)
app.include_router(users.router)
app.include_router(tasks.router)


@app.get("/", include_in_schema=False)
async def root():
    return RedirectResponse("/ui/")


# простой веб-интерфейс на HTML/JS поверх этого же API
app.mount("/ui", StaticFiles(directory=STATIC_DIR, html=True), name="ui")
