from __future__ import annotations

from collections.abc import AsyncGenerator
from datetime import datetime

from sqlalchemy import DateTime, MetaData, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, declared_attr, mapped_column

from app.config import settings

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class TimestampTenantMixin:
    @declared_attr.directive
    def id(cls) -> Mapped[str]:
        import uuid

        return mapped_column(
            UUID(as_uuid=False),
            primary_key=True,
            default=lambda: str(uuid.uuid4()),
        )

    tenant_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False), nullable=True)
    company_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


def _create_engine(database_url: str) -> AsyncEngine:
    return create_async_engine(database_url, echo=False, future=True)


engine = _create_engine(settings.database_url)
platform_engine = (
    engine
    if settings.platform_database_url_effective == settings.database_url
    else _create_engine(settings.platform_database_url_effective)
)
restaurant_engine = (
    engine
    if settings.restaurant_database_url_effective == settings.database_url
    else _create_engine(settings.restaurant_database_url_effective)
)

AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
PlatformSessionLocal = async_sessionmaker(
    platform_engine,
    expire_on_commit=False,
    class_=AsyncSession,
)
RestaurantSessionLocal = async_sessionmaker(
    restaurant_engine,
    expire_on_commit=False,
    class_=AsyncSession,
)

TARGET_DATABASE_SESSION_FACTORIES = {
    "platform_core": PlatformSessionLocal,
    "restaurant": RestaurantSessionLocal,
}

IDENTITY_DATABASE_SESSION_FACTORIES = {
    "legacy": AsyncSessionLocal,
    "platform_core": PlatformSessionLocal,
}

RESTAURANT_SERVICE_SESSION_FACTORIES = {
    "legacy": AsyncSessionLocal,
    "restaurant": RestaurantSessionLocal,
}


def session_factory_for(
    target_database: str,
) -> async_sessionmaker[AsyncSession]:
    try:
        return TARGET_DATABASE_SESSION_FACTORIES[target_database]
    except KeyError as exc:
        raise ValueError(f"Unsupported target database: {target_database}") from exc


def identity_session_factory_for(
    identity_database: str,
) -> async_sessionmaker[AsyncSession]:
    try:
        return IDENTITY_DATABASE_SESSION_FACTORIES[identity_database]
    except KeyError as exc:
        raise ValueError(f"Unsupported identity database: {identity_database}") from exc


def active_identity_session_factory() -> async_sessionmaker[AsyncSession]:
    return identity_session_factory_for(settings.identity_database)


def restaurant_service_session_factory_for(
    restaurant_service_database: str,
) -> async_sessionmaker[AsyncSession]:
    try:
        return RESTAURANT_SERVICE_SESSION_FACTORIES[restaurant_service_database]
    except KeyError as exc:
        raise ValueError(
            f"Unsupported Restaurant service database: {restaurant_service_database}"
        ) from exc


def active_restaurant_service_session_factory() -> async_sessionmaker[AsyncSession]:
    return restaurant_service_session_factory_for(settings.restaurant_service_database)


def validate_runtime_database_names(
    *,
    identity_database: str,
    restaurant_service_database: str = "legacy",
    reference_projector_enabled: bool,
    legacy_database_name: str,
    platform_database_name: str,
    restaurant_database_name: str,
) -> None:
    if (
        restaurant_service_database == "restaurant"
        and identity_database != "platform_core"
    ):
        raise RuntimeError(
            "Restaurant service cutover requires IDENTITY_DATABASE=platform_core"
        )
    if identity_database == "platform_core" and not reference_projector_enabled:
        raise RuntimeError(
            "Platform identity cutover requires REFERENCE_PROJECTOR_ENABLED=true"
        )
    if (
        identity_database != "platform_core"
        and restaurant_service_database != "restaurant"
        and not reference_projector_enabled
    ):
        return
    if len(
        {
            legacy_database_name,
            platform_database_name,
            restaurant_database_name,
        }
    ) != 3:
        raise RuntimeError(
            "Runtime cutover requires distinct legacy, Platform and Restaurant databases"
        )


async def current_database_name(
    session_factory: async_sessionmaker[AsyncSession],
) -> str:
    async with session_factory() as session:
        value = await session.scalar(func.current_database())
    if not value:
        raise RuntimeError("Could not resolve current PostgreSQL database name")
    return str(value)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session


async def get_platform_db() -> AsyncGenerator[AsyncSession, None]:
    async with PlatformSessionLocal() as session:
        yield session


async def get_restaurant_db() -> AsyncGenerator[AsyncSession, None]:
    async with RestaurantSessionLocal() as session:
        yield session


async def get_identity_db() -> AsyncGenerator[AsyncSession, None]:
    session_factory = active_identity_session_factory()
    async with session_factory() as session:
        yield session


async def get_restaurant_service_db() -> AsyncGenerator[AsyncSession, None]:
    session_factory = active_restaurant_service_session_factory()
    async with session_factory() as session:
        yield session


async def init_db() -> None:
    checked_engine_ids: set[int] = set()
    for candidate in (engine, platform_engine, restaurant_engine):
        if id(candidate) in checked_engine_ids:
            continue
        async with candidate.begin() as connection:
            await connection.run_sync(lambda _: None)
        checked_engine_ids.add(id(candidate))
