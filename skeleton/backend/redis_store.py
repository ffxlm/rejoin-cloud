"""
redis_store.py — Redis สำหรับ last_seen (TTL) + คิวคำสั่ง
------------------------------------------------------------------
- REDIS_URL ว่าง → ใช้ fakeredis (dev/test)
- last_seen: key `ls:<device_id>` = unix ts, TTL = last_seen_ttl_sec
- คำสั่ง:    list `cmd:<device_id>` (rpush/lpop)
"""
from __future__ import annotations

import json
from typing import Optional


class Store:
    def __init__(self, client, last_seen_ttl: int = 120) -> None:
        self.r = client
        self.last_seen_ttl = last_seen_ttl

    async def ping(self) -> bool:
        try:
            return bool(await self.r.ping())
        except Exception:
            return False

    # ---- last_seen ----
    async def set_last_seen(self, device_id: int, ts: int) -> None:
        await self.r.set(f"ls:{device_id}", ts, ex=self.last_seen_ttl)

    async def get_last_seen(self, device_id: int) -> Optional[int]:
        v = await self.r.get(f"ls:{device_id}")
        return int(v) if v is not None else None

    async def clear_last_seen(self, device_id: int) -> None:
        await self.r.delete(f"ls:{device_id}")

    # ---- heartbeat snapshot (สถานะสด ไม่ต้องเก็บลง DB) ----
    async def set_json(self, key: str, obj: dict, ttl: Optional[int] = None) -> None:
        await self.r.set(key, json.dumps(obj), ex=ttl)

    async def get_json(self, key: str) -> Optional[dict]:
        v = await self.r.get(key)
        if v is None:
            return None
        if isinstance(v, bytes):
            v = v.decode()
        try:
            return json.loads(v)
        except Exception:
            return None

    # ---- command queue ----
    async def push_command(self, device_id: int, command: dict) -> None:
        await self.r.rpush(f"cmd:{device_id}", json.dumps(command))

    async def pop_command(self, device_id: int) -> Optional[dict]:
        v = await self.r.lpop(f"cmd:{device_id}")
        if v is None:
            return None
        if isinstance(v, bytes):
            v = v.decode()
        try:
            return json.loads(v)
        except Exception:
            return None

    async def queue_len(self, device_id: int) -> int:
        return int(await self.r.llen(f"cmd:{device_id}"))

    async def close(self) -> None:
        try:
            await self.r.aclose()
        except Exception:
            pass


def build_store(url: str, last_seen_ttl: int) -> Store:
    if url:
        import redis.asyncio as aioredis

        client = aioredis.from_url(url, decode_responses=True)
    else:
        import fakeredis.aioredis

        client = fakeredis.aioredis.FakeRedis(decode_responses=True)
    return Store(client, last_seen_ttl=last_seen_ttl)
