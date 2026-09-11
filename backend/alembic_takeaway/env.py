from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import MetaData, engine_from_config, pool

from app.config import settings
from app.database import Base, NAMING_CONVENTION
import app.models.takeaway  # noqa: F401


config = context.config
if settings.takeaway_database_url_sync is None:
    raise RuntimeError("TAKEAWAY_DATABASE_URL is required for Takeaway migrations")
config.set_main_option("sqlalchemy.url", settings.takeaway_database_url_sync)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = MetaData(naming_convention=NAMING_CONVENTION)
for table_name, table in Base.metadata.tables.items():
    if table_name.startswith("takeaway_"):
        table.to_metadata(target_metadata)


def include_object(object_, name: str | None, type_: str, reflected: bool, compare_to):
    if type_ == "table":
        return bool(name and name.startswith("takeaway_"))
    table = getattr(object_, "table", None)
    return bool(table is None or table.name.startswith("takeaway_"))


def run_migrations_offline() -> None:
    context.configure(
        url=settings.takeaway_database_url_sync,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_object=include_object,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = settings.takeaway_database_url_sync
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
