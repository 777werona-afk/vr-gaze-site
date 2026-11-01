"""Настройки приложения: читаются из переменных окружения и файла .env."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Строка подключения задаётся только через переменную окружения DATABASE_URL,
    # в коде её нет. Пример: postgresql+asyncpg://app:app@localhost:5432/tasks
    database_url: str
    sql_echo: bool = False

    # Итоговый проект «VR-музей: стабилизация взгляда».
    # Сессия считается «дестабилизированной», если RMS колебаний взгляда в полосе
    # тремора 4-12 Гц не меньше этого порога (в градусах). Порог пилотный: его можно
    # пересмотреть, когда появятся данные контрольной группы.
    tremor_threshold_deg: float = 0.25
    # Если доля валидных отсчётов ниже этого процента, сессия получает статус «брак».
    min_valid_pct: float = 90.0


settings = Settings()
