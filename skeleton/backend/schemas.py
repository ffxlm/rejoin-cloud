"""
schemas.py — Pydantic request/response ตาม CONTRACT.md
"""
from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


class RegisterIn(BaseModel):
    device_code: str
    apk_version: Optional[str] = None
    android_id: Optional[str] = None


class RegisterOut(BaseModel):
    device_token: str
    device_id: str
    interval_sec: int


class HeartbeatIn(BaseModel):
    v: int = 1
    state: str = "connected"
    armed: Optional[bool] = None
    game_running: bool = False
    lua_active: bool = False
    lua_age_sec: Optional[int] = None
    lua_state: Optional[str] = None
    avatar: Optional[str] = None
    character: Optional[str] = None
    map: Optional[str] = None
    place_id: Optional[int] = None
    job_id: Optional[str] = None
    rejoin_count: int = 0
    session_start: Optional[int] = None
    ts: Optional[int] = None


class HeartbeatOut(BaseModel):
    ok: bool = True
    command: Optional[str] = None


class EventIn(BaseModel):
    type: str
    detail: Optional[dict[str, Any]] = None


class DeviceCreateIn(BaseModel):
    name: Optional[str] = None
    game_pkg: Optional[str] = None


class DeviceCreateOut(BaseModel):
    device_id: str
    name: str
    device_code: str  # โชว์ให้ผู้ใช้พิมพ์ใน APK ครั้งเดียว


class CommandOut(BaseModel):
    command: Optional[str] = None
    id: Optional[str] = None
