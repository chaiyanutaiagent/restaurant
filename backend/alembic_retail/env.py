from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.config import settings
from app.database import Base
import app.models  # noqa: F401 - populate the shared metadata for Retail filtering


RETAIL_SCHEMA_TABLES = {
    "companies",
    "branches",
    "brands",
    "brand_branches",
    "users",
    "units",
    "categories",
    "products",
    "product_variants",
    "product_images",
    "price_lists",
    "price_list_items",
    "price_calculations",
    "price_override_audits",
    "pos_hold_drafts",
    "pos_hold_draft_audits",
    "refund_quotes",
    "refund_operations",
    "refund_operation_items",
    "refund_payment_legs",
    "refund_tax_links",
    "refund_operation_audits",
    "stock_locations",
    "stock_balances",
    "stock_movements",
    "stock_count_sessions",
    "stock_count_items",
    "branch_settings",
    "cashier_shifts",
    "sale_orders",
    "sale_order_items",
    "payments",
    "approval_grant_usages",
    "audit_logs",
    "operational_outbox_events",
}


config = context.config
if settings.retail_database_url_sync is None:
    raise RuntimeError("RETAIL_DATABASE_URL is required for Retail migrations")
config.set_main_option("sqlalchemy.url", settings.retail_database_url_sync)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def include_object(object_, name: str, type_: str, reflected: bool, compare_to) -> bool:
    if type_ == "table":
        return name in RETAIL_SCHEMA_TABLES
    table = getattr(object_, "table", None)
    if table is not None:
        return table.name in RETAIL_SCHEMA_TABLES
    return True


def run_migrations_offline() -> None:
    context.configure(
        url=settings.retail_database_url_sync,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_object=include_object,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = settings.retail_database_url_sync
    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_object=include_object,
        )
        with context.begin_transaction():
            context.run_migrations()
    connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
