from __future__ import annotations

from functools import cached_property
from typing import Literal

from pydantic import computed_field
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def effective_database_url(explicit_url: str | None, legacy_url: str) -> str:
    return explicit_url or legacy_url


class Settings(BaseSettings):
    postgres_db: str
    postgres_user: str
    postgres_password: str
    postgres_host: str
    postgres_port: int
    database_url: str
    platform_database_url: str | None = None
    restaurant_database_url: str | None = None
    identity_database: Literal["legacy", "platform_core"] = "legacy"
    restaurant_service_database: Literal["legacy", "restaurant"] = "legacy"
    reference_projector_enabled: bool = False
    reference_projector_poll_seconds: float = Field(default=1.0, ge=0.1, le=60.0)
    reference_projector_batch_size: int = Field(default=100, ge=1, le=1000)
    redis_url: str
    secret_key: str
    algorithm: str
    access_token_expire_minutes: int
    refresh_token_expire_days: int
    approval_token_expire_seconds: int = Field(default=120, ge=30, le=300)
    manager_pin_max_failed_attempts: int = Field(default=5, ge=3, le=10)
    manager_pin_lock_minutes: int = Field(default=15, ge=1, le=60)
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
        # The repository-level env file is shared with PostgreSQL, Redis and
        # Compose. Service-specific bootstrap variables are not app settings.
        extra="ignore",
    )

    @computed_field  # type: ignore[prop-decorator]
    @property
    def database_url_sync(self) -> str:
        return self.database_url.replace("postgresql+asyncpg://", "postgresql+psycopg2://")

    @computed_field  # type: ignore[prop-decorator]
    @property
    def platform_database_url_effective(self) -> str:
        return effective_database_url(self.platform_database_url, self.database_url)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def restaurant_database_url_effective(self) -> str:
        return effective_database_url(self.restaurant_database_url, self.database_url)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def platform_database_url_sync(self) -> str:
        return self.platform_database_url_effective.replace(
            "postgresql+asyncpg://",
            "postgresql+psycopg2://",
        )

    @computed_field  # type: ignore[prop-decorator]
    @property
    def restaurant_database_url_sync(self) -> str:
        return self.restaurant_database_url_effective.replace(
            "postgresql+asyncpg://",
            "postgresql+psycopg2://",
        )

    @cached_property
    def is_production(self) -> bool:
        return self.environment == "production"


settings = Settings()
