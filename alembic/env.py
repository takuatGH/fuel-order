"""alembic environment configuration for async sqlalchemy.

this file is used by alembic to:
- connect to the database
- detect model changes for autogenerate
- run migrations online or offline
"""
import asyncio
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context

# import all models so autogenerate can detect them
from src.models.base import Base
from src.models.shop import ShopProfile
from src.models.depot import Depot
from src.models.driver import Driver
from src.models.order import Order, DeliveryAssignment
from src.config import get_settings


# alembic Config object
config = context.config

# set sqlalchemy url from app settings
settings = get_settings()
config.set_main_option("sqlalchemy.url", settings.database_url)

# setup logging from alembic.ini
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# metadata for autogenerate
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """run migrations in 'offline' mode.
    
    generates sql script without connecting to database.
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    """run migrations with given connection."""
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,  # detect column type changes
        render_as_batch=True,  # sqlite compatibility
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """run migrations in 'online' mode with async engine."""
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """run migrations in 'online' mode."""
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
