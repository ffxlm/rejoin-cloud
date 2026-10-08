"""
deps.py — dependency ที่ใช้ร่วมกัน (DB session, store, current user/device)
"""
from __future__ import annotations

from typing import Optional

from fastapi import Depends, Header, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .config import Settings
from .models import Device, DeviceToken, User
from .redis_store import Store
from .security import lookup_key, verify_secret


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


async def get_db(request: Request) -> AsyncSession:
    sm = request.app.state.sessionmaker
    async with sm() as session:
        yield session


def get_store(request: Request) -> Store:
    return request.app.state.store


async def get_current_user(
    request: Request, db: AsyncSession = Depends(get_db)
) -> User:
    uid = request.session.get("user_id")
    if not uid:
        raise HTTPException(status_code=401, detail="not logged in")
    user = await db.get(User, uid)
    if user is None:
        raise HTTPException(status_code=401, detail="user not found")
    return user


async def get_current_device(
    request: Request,
    db: AsyncSession = Depends(get_db),
    authorization: Optional[str] = Header(None),
) -> Device:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="missing bearer token")
    token = authorization.split(" ", 1)[1].strip()
    key = lookup_key(token)
    row = (
        await db.execute(
            select(DeviceToken).where(
                DeviceToken.lookup == key,
                DeviceToken.label == "token",
                DeviceToken.revoked_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if row is None or not verify_secret(row.token_hash, token):
        raise HTTPException(status_code=401, detail="invalid token")
    device = await db.get(Device, row.device_id)
    if device is None:
        raise HTTPException(status_code=401, detail="device not found")
    return device


async def resolve_owned_device(db: AsyncSession, user: User, device_id: str) -> Device:
    """ดึงเครื่องที่ผู้ใช้เป็นเจ้าของ (404 ถ้าไม่ใช่/ไม่พบ)"""
    try:
        did = int(device_id)
    except (TypeError, ValueError):
        raise HTTPException(status_code=404, detail="ไม่พบเครื่อง")
    device = await db.get(Device, did)
    if device is None or device.user_id != user.id:
        raise HTTPException(status_code=404, detail="ไม่พบเครื่อง")
    return device
