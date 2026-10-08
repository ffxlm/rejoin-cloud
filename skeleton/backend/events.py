"""
events.py — retention ของตาราง events (ประวัติเหตุการณ์)
------------------------------------------------------------------
ประวัติ (arm/disarm/rejoin/alert/...) โตได้เรื่อย ๆ ทุกครั้ง
ที่ผู้ใช้สั่งงานหรือ APK รายงาน จึงต้องมีตัวลบเพื่อไม่ให้ DB และหน้าเว็บบวม:
  - ลบเหตุการณ์ที่เก่ากว่า settings.event_retention_days
  - เก็บต่อเครื่องไว้ไม่เกิน settings.event_max_per_device แถวล่าสุด

หมายเหตุ: `rejoin_count` บนแดชบอร์ดนับจากตารางนี้ → ถ้าเปิด retention ไว้
ตัวเลขจะนับเฉพาะช่วงที่ยังเก็บอยู่ (ตามที่ตกลงกันเรื่อง "ไม่ให้ยาวมหาศาล")
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from .config import Settings
from .models import Event


def _as_aware(dt: Optional[datetime]) -> Optional[datetime]:
    """SQLite คืน datetime แบบ naive — ตีความเป็น UTC ให้เทียบกับ cutoff ได้"""
    if dt is None:
        return None
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


async def cleanup_old_events(
    db: AsyncSession, settings: Settings, now: Optional[datetime] = None
) -> int:
    """ลบเหตุการณ์เก่า/เกินเพดานต่อเครื่อง — คืนจำนวนที่ลบ

    กรองฝั่ง Python เพื่อให้ทำงานเหมือนกันทั้ง SQLite และ PostgreSQL
    (คอลัมน์ ts เป็น timezone-aware ต่างกันสอง dialect) — จำนวน event ต่อ
    ผู้ใช้มีจำกัดหลังลบรอบแรก จึงไม่กระทบ performance
    """
    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(days=settings.event_retention_days)
    keep = max(1, settings.event_max_per_device)

    rows = (await db.execute(select(Event.id, Event.device_id, Event.ts))).all()

    to_delete: set[int] = set()
    survivors: dict[int, list[tuple[datetime, int]]] = {}
    for r in rows:
        ts = _as_aware(r.ts)
        if ts is None or ts < cutoff:
            to_delete.add(r.id)
            continue
        survivors.setdefault(r.device_id, []).append((ts, r.id))

    # เกินเพดานต่อเครื่อง → เก็บใหม่สุดไว้ keep แถว
    for items in survivors.values():
        items.sort(key=lambda t: (t[0], t[1]), reverse=True)
        for _, event_id in items[keep:]:
            to_delete.add(event_id)

    if not to_delete:
        return 0

    await db.execute(delete(Event).where(Event.id.in_(list(to_delete))))
    await db.commit()
    return len(to_delete)
