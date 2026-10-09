"""
routers/admin.py — ระบบหลังบ้าน (เฉพาะแอดมิน)
------------------------------------------------------------------
- GET /api/admin/overview   สรุปภาพรวมทั้งระบบ (ผู้ใช้/เครื่อง/ออนไลน์/กู้เกม)
- GET /api/admin/users      รายชื่อผู้ใช้ทั้งหมด + จำนวนเครื่อง
- GET /api/admin/devices    รายการเครื่องทั้งหมดในระบบ + สถานะ

ทุก endpoint บังคับสิทธิ์แอดมินผ่าน get_current_admin (403 ถ้าไม่ใช่)
หน้าเว็บ /admin อยู่ใน app.py และใช้ helper ในไฟล์นี้ตัวเดียวกัน
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import Settings
from ..deps import get_current_admin, get_db, get_settings, get_store
from ..models import Device, User
from ..redis_store import Store
from ..serializers import _discord_avatar_url, build_device_view

router = APIRouter()


async def build_overview(db: AsyncSession, store: Store, settings: Settings) -> dict:
    """สรุปภาพรวมทั้งระบบ (คำนวณสถานะเครื่องสด ๆ จาก heartbeat)"""
    total_users = (await db.execute(select(func.count(User.id)))).scalar_one()
    total_devices = (await db.execute(select(func.count(Device.id)))).scalar_one()
    total_rejoins = int(
        (await db.execute(select(func.coalesce(func.sum(Device.rejoin_total), 0)))).scalar_one()
    )
    devices = (await db.execute(select(Device).order_by(Device.id))).scalars().all()
    views = [
        await build_device_view(d, store, settings, rejoin_count=d.rejoin_total or 0)
        for d in devices
    ]
    online = sum(1 for v in views if v["status"] != "offline")
    armed = sum(1 for v in views if v["status"] == "armed")
    return {
        "users": total_users,
        "devices": total_devices,
        "online": online,
        "armed": armed,
        "rejoins": total_rejoins,
    }


async def build_user_rows(db: AsyncSession) -> list[dict]:
    """รายชื่อผู้ใช้ทั้งหมด พร้อมจำนวนเครื่อง (เรียงตาม id)"""
    import time as _time

    now = int(_time.time())
    users = (await db.execute(select(User).order_by(User.id))).scalars().all()
    counts = dict(
        (await db.execute(select(Device.user_id, func.count(Device.id)).group_by(Device.user_id))).all()
    )
    rows = []
    for u in users:
        created = int(u.created_at.timestamp()) if u.created_at else None
        rows.append(
            {
                "id": u.id,
                "discord_id": u.discord_id,
                "username": u.username,
                "avatar_url": _discord_avatar_url(u.discord_id, u.avatar),
                "is_admin": bool(u.is_admin),
                "device_count": int(counts.get(u.id, 0)),
                "created_at": created,
                "created_age_sec": (now - created) if created else None,
            }
        )
    return rows


async def build_device_rows(db: AsyncSession, store: Store, settings: Settings) -> list[dict]:
    """เครื่องทั้งหมดในระบบ พร้อมชื่อเจ้าของและสถานะปัจจุบัน"""
    devices = (await db.execute(select(Device).order_by(Device.id))).scalars().all()
    owners = dict((await db.execute(select(User.id, User.username))).all())
    rows = []
    for d in devices:
        view = await build_device_view(d, store, settings, rejoin_count=d.rejoin_total or 0)
        rows.append(
            {
                **view,
                "owner_id": d.user_id,
                "owner": owners.get(d.user_id) or f"user#{d.user_id}",
            }
        )
    return rows


@router.get("/api/admin/overview")
async def admin_overview(
    _admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
    store: Store = Depends(get_store),
    settings: Settings = Depends(get_settings),
):
    return await build_overview(db, store, settings)


@router.get("/api/admin/users")
async def admin_users(
    _admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    return {"users": await build_user_rows(db)}


@router.get("/api/admin/devices")
async def admin_devices(
    _admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
    store: Store = Depends(get_store),
    settings: Settings = Depends(get_settings),
):
    return {"devices": await build_device_rows(db, store, settings)}
