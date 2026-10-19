"""Temporary probe for task 11.1 (deleted after use): import cost of alembic.command."""
import time

import sqlalchemy  # noqa: F401  (the app imports it anyway)
import fastapi  # noqa: F401

t0 = time.perf_counter()
import alembic.command  # noqa: E402,F401
import alembic.config  # noqa: E402,F401
t1 = time.perf_counter()
print(f"alembic.command import: {(t1 - t0) * 1000:.0f} ms")
