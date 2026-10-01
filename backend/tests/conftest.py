"""Shared fixtures. Database tests run against SL_TEST_DATABASE_URL (a disposable database).

The schema is created by running the real Alembic migrations, so the migration itself is
tested on every run.
"""

from __future__ import annotations

import os

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

TEST_DB = os.environ.get(
    "SL_TEST_DATABASE_URL", "postgresql+asyncpg://signallens:signallens@127.0.0.1:5432/signallens_test"
)


def _migrate(url: str) -> None:
    from alembic import command
    from alembic.config import Config

    from signallens.config import BACKEND_DIR

    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "migrations"))
    cfg.cmd_opts = type("Opts", (), {"x": [f"db_url={url}"]})()
    command.upgrade(cfg, "head")


@pytest.fixture(scope="session")
async def db_engine():
    engine = create_async_engine(TEST_DB, pool_size=5)
    try:
        async with engine.begin() as conn:
            await conn.execute(text("DROP SCHEMA public CASCADE"))
            await conn.execute(text("CREATE SCHEMA public"))
    except Exception as e:  # pragma: no cover - environment without Postgres
        await engine.dispose()
        pytest.skip(f"test database unavailable: {e}")
    # Alembic's env.py uses asyncio.run, so run it in a worker thread with its own loop.
    import asyncio

    await asyncio.to_thread(_migrate, TEST_DB)
    yield engine
    await engine.dispose()


@pytest.fixture
async def session_factory(db_engine):
    from signallens.db.base import Base
    from signallens.db.session import make_session_factory

    tables = ", ".join(f'"{t.name}"' for t in Base.metadata.sorted_tables)
    async with db_engine.begin() as conn:
        await conn.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
    return make_session_factory(db_engine)
