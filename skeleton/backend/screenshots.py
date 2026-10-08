"""
screenshots.py — เก็บ/เสิร์ฟ/ลบไฟล์ภาพหน้าจอ
------------------------------------------------------------------
- ไฟล์จริงอยู่ที่ settings.screenshot_dir และเสิร์ฟผ่าน static mount `/screenshots`
- DB เก็บแค่ url (`/screenshots/<name>`) — ตาม CONTRACT.md §5
- retention: ลบทั้งไฟล์และแถว DB ที่เก่ากว่า settings.screenshot_retention_days
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from .config import Settings
from .models import Screenshot

# URL ที่ mount ไว้ใน app.py (คงที่ ไม่ขึ้นกับ path จริงของโฟลเดอร์)
URL_PREFIX = "/screenshots"


def url_for(name: str) -> str:
    """ชื่อไฟล์ → URL สาธารณะที่ static mount เสิร์ฟ"""
    return f"{URL_PREFIX}/{name}"


def file_path(settings: Settings, url: str) -> str:
    """URL → path ไฟล์จริงบนดิสก์"""
    return os.path.join(settings.screenshot_dir, os.path.basename(url))


def _as_aware(dt: Optional[datetime]) -> Optional[datetime]:
    """SQLite คืน datetime แบบ naive — ตีความเป็น UTC ให้เทียบกับ cutoff ได้"""
    if dt is None:
        return None
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


async def cleanup_old_screenshots(
    db: AsyncSession, settings: Settings, now: Optional[datetime] = None
) -> int:
    """ลบภาพที่เก่ากว่า retention (ไฟล์ + แถว DB) — คืนจำนวนที่ลบ

    ทำการกรองฝั่ง Python เพื่อให้ทำงานเหมือนกันทั้ง SQLite และ PostgreSQL
    (จำนวนภาพต่อผู้ใช้มีจำกัด — ไม่กระทบ performance)
    """
    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(days=settings.screenshot_retention_days)

    rows = (await db.execute(select(Screenshot.id, Screenshot.ts, Screenshot.url))).all()
    old = [
        (r.id, r.url)
        for r in rows
        if (ts := _as_aware(r.ts)) is not None and ts < cutoff
    ]
    if not old:
        return 0

    for _, url in old:
        path = file_path(settings, url)
        try:
            if os.path.isfile(path):
                os.remove(path)
        except OSError:
            pass

    await db.execute(delete(Screenshot).where(Screenshot.id.in_([i for i, _ in old])))
    await db.commit()
    return len(old)
