from __future__ import annotations

from functools import cached_property
from typing import Literal

from pydantic import computed_field
from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def effective_database_url(explicit_url: str | None, legacy_url: str) -> str:
    return explicit_url or legacy_url


def resolve_api_docs_enabled(environment: str, configured: bool | None) -> bool:
    """Keep local docs convenient while defaulting internet production to closed."""
    if configured is not None:
        return configured
    return environment != "production"


def validate_saas_email_delivery_config(
    *,
    environment: str,
    mode: str,
    public_base_url: str,
    smtp_host: str | None,
    smtp_from_email: str | None,
) -> None:
    if mode == "smtp" and (not smtp_host or not smtp_from_email):
        raise ValueError("SaaS SMTP mode requires host and from email")
    if environment == "production":
        if mode != "smtp":
            raise ValueError("Production SaaS account email delivery must use SMTP")
        if not public_base_url.startswith("https://"):
            raise ValueError("Production SaaS public base URL must use HTTPS")


def validate_saas_billing_config(*, provider: str, live_charging_enabled: bool) -> None:
    normalized = provider.strip().lower()
    if not normalized:
        raise ValueError("SaaS billing provider decision must not be empty")
    if live_charging_enabled:
        raise ValueError(
            "Live SaaS charging is unavailable until a provider adapter Scope is approved"
        )


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
    platform_login_max_failed_attempts: int = Field(default=5, ge=3, le=10)
    platform_login_lock_minutes: int = Field(default=15, ge=1, le=60)
    device_pairing_pin_expire_minutes: int = Field(default=10, ge=2, le=60)
    device_pairing_max_failed_attempts: int = Field(default=5, ge=3, le=10)
    device_pairing_lock_minutes: int = Field(default=15, ge=1, le=60)
    device_access_token_expire_days: int = Field(default=30, ge=1, le=90)
    device_last_seen_write_interval_seconds: int = Field(default=60, ge=10, le=300)
    offline_sale_authorization_expire_hours: int = Field(default=12, ge=1, le=24)
    default_admin_password: str | None = None
    environment: Literal["development", "staging", "production", "test"]
    cors_origins: list[str]
    app_name: str
    app_version: str
    enable_api_docs: bool | None = None
    celery_broker_url: str
    celery_result_backend: str
    upload_dir: str = "./uploads"
    max_file_size_mb: int = 5
    allowed_image_types: list[str] = Field(
        default_factory=lambda: ["image/jpeg", "image/png", "image/webp"]
    )
    saas_public_base_url: str = "http://localhost:4173"
    saas_email_delivery_mode: Literal["console", "smtp"] = "console"
    saas_smtp_host: str | None = None
    saas_smtp_port: int = Field(default=587, ge=1, le=65535)
    saas_smtp_username: str | None = None
    saas_smtp_password: str | None = None
    saas_smtp_from_email: str | None = None
    saas_smtp_from_name: str = "Restaurant SaaS"
    saas_smtp_use_tls: bool = False
    saas_smtp_start_tls: bool = True
    saas_verification_expire_hours: int = Field(default=24, ge=1, le=72)
    saas_password_reset_expire_minutes: int = Field(default=30, ge=10, le=120)
    saas_trial_days: int = Field(default=14, ge=1, le=90)
    saas_billing_provider: str = "unconfigured"
    saas_billing_live_charging_enabled: bool = False

    model_config = SettingsConfigDict(
        env_file=(".env", "../.env", "../../.env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        # The repository-level env file is shared with PostgreSQL, Redis and
        # Compose. Service-specific bootstrap variables are not app settings.
        extra="ignore",
    )

    @model_validator(mode="after")
    def validate_saas_delivery(self) -> "Settings":
        validate_saas_email_delivery_config(
            environment=self.environment,
            mode=self.saas_email_delivery_mode,
            public_base_url=self.saas_public_base_url,
            smtp_host=self.saas_smtp_host,
            smtp_from_email=self.saas_smtp_from_email,
        )
        validate_saas_billing_config(
            provider=self.saas_billing_provider,
            live_charging_enabled=self.saas_billing_live_charging_enabled,
        )
        self.saas_public_base_url = self.saas_public_base_url.rstrip("/")
        self.saas_billing_provider = self.saas_billing_provider.strip().lower()
        return self

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

    @cached_property
    def api_docs_enabled(self) -> bool:
        return resolve_api_docs_enabled(self.environment, self.enable_api_docs)


settings = Settings()
