"""Настройки приложения: читаются из переменных окружения и файла .env."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Строка подключения задаётся только через переменную окружения DATABASE_URL,
    # в коде её нет. Пример: postgresql+asyncpg://app:app@localhost:5432/tasks
    database_url: str
    sql_echo: bool = False


settings = Settings()
