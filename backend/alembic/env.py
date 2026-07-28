"""
Alembic Migration Environment.

Reads DATABASE_URL from app settings so there is a single source of truth.
Supports both online (live DB) and offline (SQL script) modes.
"""

from logging.config import fileConfig
from sqlalchemy import engine_from_config, pool
from alembic import context

from app.core.config import get_settings
from app.database.session import Base

# Import ALL models so Base.metadata is fully populated for autogenerate
import app.models  # noqa: F401

# ── Alembic config ────────────────────────────────────────────
config = context.config

# Inject DB URL from app settings (overrides alembic.ini placeholder)
settings = get_settings()
db_url = settings.DATABASE_URL

# psycopg3 (postgresql+psycopg) works fine for both app and Alembic.
# Escape '%' → '%%' so configparser doesn't misinterpret URL-encoded chars.
db_url = settings.DATABASE_URL.replace("%", "%%")
config.set_main_option("sqlalchemy.url", db_url)

# Logging setup
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Offline mode — generate SQL script without connecting."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Online mode — connect and apply migrations directly."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
