from __future__ import annotations

from collections.abc import AsyncGenerator
from datetime import datetime

from sqlalchemy import DateTime, MetaData, func, text
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
takeaway_engine = (
    _create_engine(settings.takeaway_database_url)
    if settings.takeaway_database_url
    else None
)
retail_engine = (
    _create_engine(settings.retail_database_url)
    if settings.retail_database_url
    else None
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
TakeawaySessionLocal = (
    async_sessionmaker(takeaway_engine, expire_on_commit=False, class_=AsyncSession)
    if takeaway_engine is not None
    else None
)
RetailSessionLocal = (
    async_sessionmaker(retail_engine, expire_on_commit=False, class_=AsyncSession)
    if retail_engine is not None
    else None
)

TARGET_DATABASE_SESSION_FACTORIES = {
    "platform_core": PlatformSessionLocal,
    "restaurant": RestaurantSessionLocal,
}
if RetailSessionLocal is not None:
    TARGET_DATABASE_SESSION_FACTORIES["retail_pos"] = RetailSessionLocal
IDENTITY_DATABASE_SESSION_FACTORIES = {
    "legacy": AsyncSessionLocal,
    "platform_core": PlatformSessionLocal,
}

RESTAURANT_SERVICE_SESSION_FACTORIES = {
    "legacy": AsyncSessionLocal,
    "restaurant": RestaurantSessionLocal,
}
RETAIL_SERVICE_SESSION_FACTORIES = {"legacy": AsyncSessionLocal}
if RetailSessionLocal is not None:
    RETAIL_SERVICE_SESSION_FACTORIES["retail"] = RetailSessionLocal


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


def retail_service_session_factory_for(
    retail_service_database: str,
) -> async_sessionmaker[AsyncSession]:
    try:
        return RETAIL_SERVICE_SESSION_FACTORIES[retail_service_database]
    except KeyError as exc:
        raise ValueError(
            f"Unsupported Retail service database: {retail_service_database}"
        ) from exc


def active_retail_service_session_factory() -> async_sessionmaker[AsyncSession]:
    return retail_service_session_factory_for(settings.retail_service_database)


def takeaway_service_session_factory_for(
    takeaway_service_database: str,
) -> async_sessionmaker[AsyncSession]:
    if takeaway_service_database != "takeaway" or TakeawaySessionLocal is None:
        raise ValueError("Takeaway operational service is not available")
    return TakeawaySessionLocal


def active_takeaway_service_session_factory() -> async_sessionmaker[AsyncSession]:
    if not settings.takeaway_feature_enabled:
        raise ValueError("Takeaway operational service is not enabled")
    return takeaway_service_session_factory_for(settings.takeaway_service_database)


def validate_runtime_database_names(
    *,
    identity_database: str,
    restaurant_service_database: str = "legacy",
    reference_projector_enabled: bool,
    legacy_database_name: str,
    platform_database_name: str,
    restaurant_database_name: str,
    retail_service_database: str = "legacy",
    retail_database_name: str | None = None,
    retail_reference_projector_enabled: bool = False,
    takeaway_service_database: str = "disabled",
    takeaway_feature_enabled: bool = False,
    takeaway_database_name: str | None = None,
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
    if retail_service_database == "retail":
        if identity_database != "platform_core":
            raise RuntimeError(
                "Retail service cutover requires IDENTITY_DATABASE=platform_core"
            )
        if not reference_projector_enabled:
            raise RuntimeError(
                "Retail service cutover requires REFERENCE_PROJECTOR_ENABLED=true"
            )
        if not retail_reference_projector_enabled:
            raise RuntimeError(
                "Retail service cutover requires RETAIL_REFERENCE_PROJECTOR_ENABLED=true"
            )
        if retail_database_name is None:
            raise RuntimeError("Retail service cutover requires a physical Retail database")
    if takeaway_feature_enabled:
        if takeaway_service_database != "takeaway":
            raise RuntimeError(
                "Takeaway feature requires TAKEAWAY_SERVICE_DATABASE=takeaway"
            )
        if identity_database != "platform_core":
            raise RuntimeError(
                "Takeaway service cutover requires IDENTITY_DATABASE=platform_core"
            )
        if not reference_projector_enabled:
            raise RuntimeError(
                "Takeaway service cutover requires REFERENCE_PROJECTOR_ENABLED=true"
            )
        if takeaway_database_name is None:
            raise RuntimeError("Takeaway feature requires a physical Takeaway database")
    if (
        identity_database != "platform_core"
        and restaurant_service_database != "restaurant"
        and retail_service_database != "retail"
        and not reference_projector_enabled
    ):
        return
    required_names = {
        legacy_database_name,
        platform_database_name,
        restaurant_database_name,
    }
    expected_count = 3
    if retail_service_database == "retail" and retail_database_name is not None:
        required_names.add(retail_database_name)
        expected_count += 1
    if takeaway_feature_enabled and takeaway_database_name is not None:
        required_names.add(takeaway_database_name)
        expected_count += 1
    if len(required_names) != expected_count:
        raise RuntimeError(
            "Runtime cutover requires distinct legacy, Platform, Restaurant and enabled service databases"
        )


RETAIL_RUNTIME_REQUIRED_TABLES = {
    "companies",
    "brands",
    "branches",
    "brand_branches",
    "users",
    "units",
    "categories",
    "products",
    "product_variants",
    "product_images",
    "price_lists",
    "price_list_items",
    "stock_locations",
    "stock_balances",
    "stock_movements",
    "stock_count_sessions",
    "stock_count_items",
    "cashier_shifts",
    "pos_cash_movements",
    "sale_orders",
    "sale_order_items",
    "payments",
    "audit_logs",
    "branch_settings",
    "approval_grant_usages",
    "operational_outbox_events",
    "retail_reference_projection_receipts",
    "retail_migration_runs",
}


async def validate_retail_schema_readiness(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Prevent routing Retail traffic to a new but still empty boundary."""
    async with session_factory() as session:
        rows = await session.scalars(
            text(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = 'public'"
            )
        )
        table_names = {str(value) for value in rows}
        boundary_row = None
        if "database_boundary_metadata" in table_names:
            boundary_row = (
                await session.execute(
                    text(
                        "SELECT boundary_name, schema_contract_version "
                        "FROM database_boundary_metadata "
                        "WHERE boundary_name = 'retail'"
                    )
                )
            ).one_or_none()
    missing = sorted(RETAIL_RUNTIME_REQUIRED_TABLES - table_names)
    boundary_ready = (
        boundary_row is not None
        and boundary_row[0] == "retail"
        and int(boundary_row[1]) >= 2
    )
    if not boundary_ready or missing:
        detail = ", ".join(missing[:5])
        suffix = f": {detail}" if detail else ""
        raise RuntimeError(f"Retail database schema is not cutover-ready{suffix}")


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


async def get_takeaway_db() -> AsyncGenerator[AsyncSession, None]:
    if TakeawaySessionLocal is None:
        raise RuntimeError("Takeaway database is not configured")
    async with TakeawaySessionLocal() as session:
        yield session


async def get_retail_db() -> AsyncGenerator[AsyncSession, None]:
    if RetailSessionLocal is None:
        raise RuntimeError("Retail database is not configured")
    async with RetailSessionLocal() as session:
        yield session


async def get_identity_db() -> AsyncGenerator[AsyncSession, None]:
    session_factory = active_identity_session_factory()
    async with session_factory() as session:
        yield session


async def get_restaurant_service_db() -> AsyncGenerator[AsyncSession, None]:
    session_factory = active_restaurant_service_session_factory()
    async with session_factory() as session:
        yield session


async def get_takeaway_service_db() -> AsyncGenerator[AsyncSession, None]:
    session_factory = active_takeaway_service_session_factory()
    async with session_factory() as session:
        yield session


async def init_db() -> None:
    checked_engine_ids: set[int] = set()
    candidates = [engine, platform_engine, restaurant_engine]
    if retail_engine is not None:
        candidates.append(retail_engine)
    if takeaway_engine is not None:
        candidates.append(takeaway_engine)
    for candidate in candidates:
        if id(candidate) in checked_engine_ids:
            continue
        async with candidate.begin() as connection:
            await connection.run_sync(lambda _: None)
        checked_engine_ids.add(id(candidate))
