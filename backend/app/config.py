from __future__ import annotations

from functools import cached_property
from typing import Literal

from pydantic import computed_field
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    postgres_db: str
    postgres_user: str
    postgres_password: str
    postgres_host: str
    postgres_port: int
    database_url: str
    redis_url: str
    secret_key: str
    algorithm: str
    access_token_expire_minutes: int
    refresh_token_expire_days: int
    default_admin_password: str | None = None
    environment: Literal["development", "staging", "production", "test"]
    cors_origins: list[str]
    app_name: str
    app_version: str
    celery_broker_url: str
    celery_result_backend: str
    upload_dir: str = "./uploads"
    max_file_size_mb: int = 5
    allowed_image_types: list[str] = Field(
        default_factory=lambda: ["image/jpeg", "image/png", "image/webp"]
    )

    model_config = SettingsConfigDict(
        env_file=(".env", "../.env", "../../.env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    @computed_field  # type: ignore[prop-decorator]
    @property
    def database_url_sync(self) -> str:
        return self.database_url.replace("postgresql+asyncpg://", "postgresql+psycopg2://")

    @cached_property
    def is_production(self) -> bool:
        return self.environment == "production"


settings = Settings()
