"""Database connection helpers using asyncpg + pgvector."""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import asyncpg
from pgvector.asyncpg import register_vector

_pool: asyncpg.Pool | None = None


async def _init_conn(c: asyncpg.Connection) -> None:
    await register_vector(c)


async def get_pool() -> asyncpg.Pool:
    """Return a singleton asyncpg pool with pgvector registered on each connection."""
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(
            dsn=os.environ["DATABASE_URL"],
            min_size=1,
            max_size=4,
            init=_init_conn,
        )
    return _pool


@asynccontextmanager
async def conn() -> AsyncIterator[asyncpg.Connection]:
    """Yield a pooled connection."""
    pool = await get_pool()
    async with pool.acquire() as c:
        yield c
