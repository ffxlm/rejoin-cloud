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


def ensure_schema(conn) -> None:
    """เพิ่มคอลัมน์ใหม่ให้ DB เดิม (create_all ไม่ alter ตารางที่มีอยู่แล้ว)

    เรียกผ่าน engine.run_sync(...) ตอน startup — ทำงานแบบ idempotent
    """
    from sqlalchemy import inspect, text

    insp = inspect(conn)
    tables = insp.get_table_names()

    # เอาระบบแคปภาพหน้าจอ (screenshot) ออกแล้ว — ลบตารางที่ค้างใน DB เดิม
    if "screenshots" in tables:
        conn.execute(text("DROP TABLE screenshots"))

    if "devices" not in tables:
        return
    cols = {c["name"] for c in insp.get_columns("devices")}
    if "rejoin_total" not in cols:
        conn.execute(
            text("ALTER TABLE devices ADD COLUMN rejoin_total INTEGER NOT NULL DEFAULT 0")
        )
        # backfill ยอดสะสมจาก events ที่มีอยู่ก่อนหน้า
        conn.execute(
            text(
                "UPDATE devices SET rejoin_total = ("
                " SELECT COUNT(*) FROM events e"
                " WHERE e.device_id = devices.id AND e.type = 'rejoin'"
                ")"
            )
        )
