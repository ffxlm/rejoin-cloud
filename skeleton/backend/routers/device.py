"""
routers/device.py — คำสั่งจากเว็บไป APK + APK poll คำสั่ง
------------------------------------------------------------------
เว็บ (ต้องล็อกอิน + เป็นเจ้าของเครื่อง):
  POST /api/device/{id}/arm
  POST /api/device/{id}/disarm
  POST /api/device/{id}/rejoin_now
APK (Bearer device_token):
  GET  /api/device/command      poll คำสั่ง
"""
from __future__ import annotations

import time
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ..deps import (
    get_current_device,
    get_current_user,
    get_db,
    get_store,
    resolve_owned_device,
)
from ..models import Device, Event, User
from ..redis_store import Store
from ..schemas import CommandOut

router = APIRouter()


async def _queue_command(
    db: AsyncSession, store: Store, device: Device, command: str
) -> None:
    db.add(Event(device_id=device.id, type=command, detail={}))
    await db.commit()
    await store.push_command(device.id, {"command": command, "id": f"cmd_{int(time.time())}"})


@router.post("/api/device/{device_id}/arm")
async def arm(
    device_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    store: Store = Depends(get_store),
):
    device = await resolve_owned_device(db, user, device_id)
    device.armed = True
    device.armed_at = datetime.now(timezone.utc)
    await _queue_command(db, store, device, "arm")
    return {"ok": True, "queued": "arm"}


@router.post("/api/device/{device_id}/disarm")
async def disarm(
    device_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    store: Store = Depends(get_store),
):
    device = await resolve_owned_device(db, user, device_id)
    device.armed = False
    device.armed_at = None
    await _queue_command(db, store, device, "disarm")
    return {"ok": True, "queued": "disarm"}


@router.post("/api/device/{device_id}/rejoin_now")
async def rejoin_now(
    device_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    store: Store = Depends(get_store),
):
    device = await resolve_owned_device(db, user, device_id)
    await _queue_command(db, store, device, "rejoin_now")
    return {"ok": True, "queued": "rejoin_now"}


@router.get("/api/device/command", response_model=CommandOut)
async def poll_command(
    device: Device = Depends(get_current_device),
    store: Store = Depends(get_store),
):
    cmd = await store.pop_command(device.id)
    if not cmd:
        return CommandOut()
    return CommandOut(command=cmd.get("command"), id=cmd.get("id"))
