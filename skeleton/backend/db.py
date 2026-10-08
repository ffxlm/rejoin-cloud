"""
db.py — สร้าง async engine + session factory (Postgres-first, dev = SQLite)
------------------------------------------------------------------
- ใช้ SQLAlchemy 2.0 async
- ถ้า DATABASE_URL เป็น sqlite + in-memory → ใช้ StaticPool (กันคนละ connection คนละ DB)
"""
from __future__ import annotations

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import StaticPool


class Base(DeclarativeBase):
    """Base ของทุก model"""


def build_engine(url: str) -> AsyncEngine:
    kwargs: dict = {"future": True}
    if url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
        # in-memory: ต้องใช้ connection เดียวกันตลอด
        if ":memory:" in url or url.endswith("://"):
            kwargs["poolclass"] = StaticPool
    return create_async_engine(url, **kwargs)


def build_sessionmaker(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
