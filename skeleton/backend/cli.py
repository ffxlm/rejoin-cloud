"""
cli.py — จัดการแอดมินจากบรรทัดคำสั่ง (DB เป็นแหล่งความจริงของสิทธิ์)
------------------------------------------------------------------
ใช้เมื่อต้องการตั้ง/ถอดสิทธิ์แอดมินให้ผู้ใช้ที่ล็อกอินแล้ว (ผู้ใช้คนแรกเป็นแอดมินอัตโนมัติ)

ตัวอย่าง:
    python -m skeleton.backend.cli list
    python -m skeleton.backend.cli grant 123456789012345678
    python -m skeleton.backend.cli revoke 123456789012345678

ค่า DATABASE_URL อ่านจาก .env / environment เหมือนตัวเซิร์ฟเวอร์
"""
from __future__ import annotations

import argparse
import asyncio

from sqlalchemy import select

from .config import Settings
from .db import Base, build_engine, build_sessionmaker, ensure_schema
from .models import User


async def _with_db(fn):
    settings = Settings.from_env()
    engine = build_engine(settings.database_url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(ensure_schema)
    sm = build_sessionmaker(engine)
    try:
        async with sm() as db:
            return await fn(db)
    finally:
        await engine.dispose()


async def _list(db) -> int:
    users = (await db.execute(select(User).order_by(User.id))).scalars().all()
    if not users:
        print("ยังไม่มีผู้ใช้ในระบบ (ให้ล็อกอินก่อน แล้วค่อยใช้คำสั่ง grant)")
        return 0
    print(f"{'สิทธิ์':<8} {'id':<5} {'discord_id':<24} username")
    for u in users:
        mark = "★ admin" if u.is_admin else "  user"
        print(f"{mark:<8} {u.id:<5} {u.discord_id:<24} {u.username or ''}")
    return 0


async def _set_admin(db, discord_id: str, is_admin: bool) -> int:
    user = (
        await db.execute(select(User).where(User.discord_id == discord_id))
    ).scalar_one_or_none()
    if user is None:
        print(f"ไม่พบผู้ใช้ discord_id={discord_id} (ให้ผู้ใช้ล็อกอินอย่างน้อย 1 ครั้งก่อน)")
        return 1
    user.is_admin = is_admin
    await db.commit()
    action = "ตั้งเป็นแอดมินแล้ว" if is_admin else "ถอดสิทธิ์แอดมินแล้ว"
    print(f"{action}: {user.username or user.discord_id} (id={user.id})")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="python -m skeleton.backend.cli",
        description="จัดการแอดมินของ Rejoin (ระบบหลังบ้าน)",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list", help="แสดงผู้ใช้ทั้งหมด + สถานะแอดมิน")
    g = sub.add_parser("grant", help="ตั้งให้ผู้ใช้เป็นแอดมิน")
    g.add_argument("discord_id", help="Discord ID ของผู้ใช้")
    r = sub.add_parser("revoke", help="ถอดสิทธิ์แอดมิน")
    r.add_argument("discord_id", help="Discord ID ของผู้ใช้")
    args = parser.parse_args()

    if args.cmd == "list":
        return asyncio.run(_with_db(_list))
    if args.cmd == "grant":
        return asyncio.run(_with_db(lambda db: _set_admin(db, args.discord_id, True)))
    return asyncio.run(_with_db(lambda db: _set_admin(db, args.discord_id, False)))


if __name__ == "__main__":
    raise SystemExit(main())
