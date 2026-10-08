"""
routers/agent.py — endpoints ที่ APK เรียก (ยืนยันด้วย Bearer device_token)
------------------------------------------------------------------
- POST /api/agent/register     แลก device_code → device_token (ครั้งแรก)
- POST /api/agent/heartbeat    ส่งสถานะ → คืนคำสั่ง (ถ้ามี)
- POST /api/agent/event        บันทึก event (rejoin/alert/...)
- POST /api/agent/screenshot   อัปโหลดภาพหน้าจอ (เก็บไฟล์ + ลง DB)
"""
from __future__ import annotations

import os
import secrets
import time
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import Settings
from ..deps import get_current_device, get_db, get_settings, get_store
from ..models import Device, DeviceState, DeviceToken, Event, Screenshot
from ..redis_store import Store
from ..schemas import EventIn, HeartbeatIn, HeartbeatOut, RegisterIn, RegisterOut
from ..screenshots import cleanup_old_screenshots, url_for
from ..security import generate_token, hash_secret, lookup_key, verify_secret

router = APIRouter()


def _utc(ts: int | None) -> datetime | None:
    return datetime.fromtimestamp(ts, tz=timezone.utc) if ts else None


@router.post("/api/agent/register", response_model=RegisterOut)
async def register(
    body: RegisterIn,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    code = body.device_code.strip()
    key = lookup_key(code)
    row = (
        await db.execute(
            select(DeviceToken).where(
                DeviceToken.lookup == key,
                DeviceToken.label == "code",
                DeviceToken.revoked_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if row is None or not verify_secret(row.token_hash, code):
        raise HTTPException(status_code=401, detail="รหัสเครื่องไม่ถูกต้อง")

    device = await db.get(Device, row.device_id)
    if device is None:
        raise HTTPException(status_code=401, detail="ไม่พบเครื่อง")
    if body.apk_version:
        device.apk_version = body.apk_version

    token = generate_token()
    db.add(
        DeviceToken(
            device_id=device.id,
            token_hash=hash_secret(token),
            lookup=lookup_key(token),
            label="token",
        )
    )
    await db.commit()
    return RegisterOut(
        device_token=token,
        device_id=str(device.id),
        interval_sec=settings.heartbeat_interval_sec,
    )


@router.post("/api/agent/heartbeat", response_model=HeartbeatOut)
async def heartbeat(
    body: HeartbeatIn,
    device: Device = Depends(get_current_device),
    db: AsyncSession = Depends(get_db),
    store: Store = Depends(get_store),
    settings: Settings = Depends(get_settings),
):
    now = int(time.time())
    device.last_seen = datetime.fromtimestamp(now, tz=timezone.utc)
    device.status = body.state or "connected"
    if body.armed is not None:
        device.armed = body.armed
    if body.session_start:
        device.session_start = _utc(body.session_start)

    # state จาก Lua (denormalized, เพื่อโชว์ค่า "ล่าสุด" — ไม่อัปเดตทับด้วย None)
    state = await db.get(DeviceState, device.id)
    if state is None:
        state = DeviceState(device_id=device.id)
        db.add(state)
    if body.avatar is not None:
        state.avatar = body.avatar
    if body.character is not None:
        state.character = body.character
    if body.map is not None:
        state.map = body.map
    if body.place_id is not None:
        state.place_id = body.place_id
    if body.job_id is not None:
        state.job_id = body.job_id
    if body.lua_state is not None:
        state.lua_state = body.lua_state
    if body.lua_age_sec is not None:
        state.lua_age_sec = body.lua_age_sec
    state.updated_at = datetime.fromtimestamp(now, tz=timezone.utc)

    await db.commit()

    # สถานะสดลง Redis (TTL) + last_seen
    await store.set_last_seen(device.id, now)
    await store.set_json(
        f"hb:{device.id}",
        {
            "state": body.state,
            "game_running": body.game_running,
            "lua_active": body.lua_active,
            "lua_age_sec": body.lua_age_sec,
            "lua_state": body.lua_state,
            "ts": now,
        },
        ttl=settings.last_seen_ttl_sec,
    )

    cmd = await store.pop_command(device.id)
    return HeartbeatOut(ok=True, command=(cmd or {}).get("command"))


@router.post("/api/agent/event")
async def agent_event(
    body: EventIn,
    device: Device = Depends(get_current_device),
    db: AsyncSession = Depends(get_db),
):
    db.add(Event(device_id=device.id, type=body.type, detail=body.detail or {}))
    await db.commit()
    return {"ok": True}


@router.post("/api/agent/screenshot")
async def screenshot(
    file: UploadFile = File(...),
    device: Device = Depends(get_current_device),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    """รับภาพหน้าจอจาก APK (multipart) → เก็บไฟล์ + ลง DB + ลบของเก่าตาม retention"""
    content_type = (file.content_type or "").lower()
    ext = ".png" if "png" in content_type else ".jpg"
    name = f"dev{device.id}_{int(time.time())}_{secrets.token_hex(3)}{ext}"
    os.makedirs(settings.screenshot_dir, exist_ok=True)
    path = os.path.join(settings.screenshot_dir, name)

    # อ่านเป็น chunk กันไฟล์ยักษ์กลืน RAM
    size = 0
    try:
        with open(path, "wb") as f:
            while chunk := await file.read(64 * 1024):
                size += len(chunk)
                if size > settings.screenshot_max_bytes:
                    raise HTTPException(status_code=413, detail="ไฟล์ใหญ่เกินกำหนด")
                f.write(chunk)
    except HTTPException:
        _safe_remove(path)
        raise
    except Exception:
        _safe_remove(path)
        raise HTTPException(status_code=400, detail="รับไฟล์ไม่สำเร็จ")

    if size == 0:
        _safe_remove(path)
        raise HTTPException(status_code=400, detail="ไฟล์ว่าง")

    url = url_for(name)
    row = Screenshot(device_id=device.id, url=url)
    db.add(row)
    await db.commit()
    await db.refresh(row)

    # ลบภาพที่เก่ากว่า retention (best-effort — ไม่ให้ล้มทั้ง request)
    try:
        await cleanup_old_screenshots(db, settings)
    except Exception:
        pass

    return {"ok": True, "id": row.id, "url": url, "ts": int(row.ts.timestamp())}


def _safe_remove(path: str) -> None:
    try:
        if os.path.isfile(path):
            os.remove(path)
    except OSError:
        pass
