"""Alembic environment. Uses DATABASE_URL so migrations run on SQLite and Postgres.

Works from any working directory: alembic.ini finds the scripts through %(here)s and this file
puts the repo root on sys.path. In-process callers (app startup, tests) pass `database_url` and
`configure_logger=False` in config.attributes; the alembic CLI uses DATABASE_URL.
"""
from __future__ import annotations

import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import create_engine, pool

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.backend.db.session import get_database_url  # noqa: E402
from app.backend.models import Base  # noqa: E402

config = context.config
# Only the CLI configures logging. In-process, fileConfig would replace the caller's handlers.
if config.config_file_name is not None and config.attributes.get("configure_logger", True):
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata


def database_url() -> str:
    """The caller's URL, else DATABASE_URL. Kept out of the ini parser, where '%' breaks."""
    url: str | None = config.attributes.get("database_url")
    return url or get_database_url()


def run_migrations_offline() -> None:
    context.configure(
        url=database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = create_engine(database_url(), poolclass=pool.NullPool)
    try:
        with connectable.connect() as connection:
            context.configure(
                connection=connection, target_metadata=target_metadata, render_as_batch=True
            )
            with context.begin_transaction():
                context.run_migrations()
    finally:
        connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
