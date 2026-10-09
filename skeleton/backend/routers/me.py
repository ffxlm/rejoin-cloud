"""
routers/me.py — แดชบอร์ดของผู้ใช้ (ต้องล็อกอิน)
------------------------------------------------------------------
- GET    /api/me/devices            รายการเครื่อง + สถานะ
- POST   /api/me/devices            เพิ่มเครื่อง → คืน device_code (ครั้งเดียว)
- DELETE /api/me/devices/{id}       ลบเครื่อง + revoke รหัสทั้งหมด
- GET    /api/me/events             ประวัติเหตุการณ์ล่าสุด
- GET    /api/download/lua          ดาวน์โหลด Lua
- GET    /api/download/apk          ดาวน์โหลด APK (ถ้ามี)
"""
from __future__ import annotations

import os

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import Settings
from ..deps import (
    get_current_user,
    get_db,
    get_settings,
    get_store,
    resolve_owned_device,
)
from ..models import Device, DeviceToken, Event, User
from ..redis_store import Store
from ..schemas import DeviceCreateIn, DeviceCreateOut
from ..security import generate_device_code, hash_secret, lookup_key
from ..serializers import build_device_view

router = APIRouter()


async def _owned_device(db: AsyncSession, user: User, device_id: str) -> Device:
    return await resolve_owned_device(db, user, device_id)


@router.get("/api/me/devices")
async def list_devices(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    store: Store = Depends(get_store),
    settings: Settings = Depends(get_settings),
):
    devices = (
        await db.execute(
            select(Device).where(Device.user_id == user.id).order_by(Device.id)
        )
    ).scalars().all()
    out = [
        await build_device_view(d, store, settings, rejoin_count=d.rejoin_total or 0)
        for d in devices
    ]
    return {"devices": out}


@router.post("/api/me/devices", response_model=DeviceCreateOut)
async def create_device(
    body: DeviceCreateIn,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    name = (body.name or "").strip() or "เครื่องใหม่"
    device = Device(
        user_id=user.id,
        name=name,
        game_pkg=body.game_pkg or "com.roblox.client",
        status="offline",
    )
    db.add(device)
    await db.flush()

    code = generate_device_code()
    db.add(
        DeviceToken(
            device_id=device.id,
            token_hash=hash_secret(code),
            lookup=lookup_key(code),
            label="code",
        )
    )
    await db.commit()
    await db.refresh(device)
    # device_code โชว์ครั้งเดียว — ไม่เก็บ plaintext
    return DeviceCreateOut(device_id=str(device.id), name=device.name, device_code=code)


@router.delete("/api/me/devices/{device_id}")
async def delete_device(
    device_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    store: Store = Depends(get_store),
):
    device = await _owned_device(db, user, device_id)
    await store.clear_last_seen(device.id)
    await db.delete(device)
    await db.commit()
    return {"ok": True}


@router.get("/api/me/events")
async def list_events(
    limit: int = 30,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    limit = max(1, min(limit, 200))
    device_ids = (
        await db.execute(select(Device.id).where(Device.user_id == user.id))
    ).scalars().all()
    if not device_ids:
        return {"events": []}
    rows = (
        await db.execute(
            select(Event)
            .where(Event.device_id.in_(device_ids))
            .order_by(Event.ts.desc())
            .limit(limit)
        )
    ).scalars().all()
    return {
        "events": [
            {
                "id": e.id,
                "device_id": str(e.device_id),
                "type": e.type,
                "detail": e.detail or {},
                "ts": int(e.ts.timestamp()),
            }
            for e in rows
        ]
    }


@router.get("/api/download/lua")
async def download_lua(settings: Settings = Depends(get_settings)):
    path = os.path.join(settings.lua_dir, "rejoin_agent.lua")
    if not os.path.isfile(path):
        raise HTTPException(status_code=404, detail="ไม่พบไฟล์ Lua")
    return FileResponse(path, media_type="text/plain", filename="rejoin_agent.lua")


@router.get("/api/download/apk")
async def download_apk(settings: Settings = Depends(get_settings)):
    path = settings.resolve_apk_path()
    if not path:
        raise HTTPException(status_code=404, detail="ยังไม่มี APK")
    return FileResponse(path, media_type="application/vnd.android.package-archive",
                        filename=os.path.basename(path))
