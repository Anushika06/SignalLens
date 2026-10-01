"""Async engine and session factory."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine


def make_engine(database_url: str, *, pool_size: int = 10) -> AsyncEngine:
    return create_async_engine(database_url, pool_size=pool_size, max_overflow=10, pool_pre_ping=True)


def make_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


@asynccontextmanager
async def transaction(factory: async_sessionmaker[AsyncSession]) -> AsyncIterator[AsyncSession]:
    """Short unit of work: commit on success, roll back on error.

    Agent runs can take minutes, so pipeline code opens many short transactions instead of
    holding one open for the whole run.
    """
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except BaseException:
            await session.rollback()
            raise
