"""
serializers.py — แปลง model → dict สำหรับ API/แดชบอร์ด
------------------------------------------------------------------
สถานะ (status) คำนวณฝั่งเว็บแบบ dead-man's switch:
  last_seen เก่ากว่า offline_after_sec → offline
  ไม่งั้นใช้ state ที่ APK รายงานล่าสุด (armed/lua_active/game_running/...)
"""
from __future__ import annotations

import time
from typing import Optional

from .config import Settings
from .models import Device, User
from .redis_store import Store


def _ts(dt) -> Optional[int]:
    return int(dt.timestamp()) if dt else None


async def build_device_view(
    device: Device,
    store: Store,
    settings: Settings,
    rejoin_count: int = 0,
    now: Optional[int] = None,
) -> dict:
    now = now or int(time.time())
    ls = await store.get_last_seen(device.id)
    last_seen = ls or _ts(device.last_seen) or 0
    stale = (last_seen == 0) or (now - last_seen > settings.offline_after_sec)
    status = "offline" if stale else (device.status or "connected")

    hb = await store.get_json(f"hb:{device.id}") or {}
    state = device.state
    # liveness ใช้ค่าจาก heartbeat ปัจจุบันเท่านั้น (ห้าม fallback ค่าเก่าใน device_state
    # ไม่งั้นตอน Lua เงียบจะโชว์ lua_active ผิด) — device_state ใช้แค่โชว์ค่าล่าสุด
    hb_age = hb.get("lua_age_sec")
    lua_active = bool(hb.get("lua_active"))
    if hb_age is not None:
        lua_active = lua_active and hb_age <= settings.silence_sec
    display_age = hb_age if hb_age is not None else (state.lua_age_sec if state else None)

    return {
        "device_id": str(device.id),
        "name": device.name,
        "game_pkg": device.game_pkg,
        "status": status,
        "armed": bool(device.armed),
        "last_seen": last_seen,
        "last_seen_age_sec": (now - last_seen) if last_seen else None,
        "game_running": bool(hb.get("game_running")),
        "lua_active": lua_active,
        "lua_state": hb.get("lua_state") or (state.lua_state if state else None),
        "lua_age_sec": display_age,
        "avatar": (state.avatar if state else None),
        "character": (state.character if state else None),
        "map": (state.map if state else None),
        "place_id": (state.place_id if state else None),
        "job_id": (state.job_id if state else None),
        "session_start": _ts(device.session_start),
        "rejoin_count": rejoin_count,
        "apk_version": device.apk_version,
        "created_at": _ts(device.created_at),
    }


def user_public(user: User) -> dict:
    return {
        "id": user.id,
        "discord_id": user.discord_id,
        "username": user.username,
        "avatar": user.avatar,
    }
