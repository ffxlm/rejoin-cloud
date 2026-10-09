"""
config.py — การตั้งค่าทั้งหมดอ่านจาก environment (12-factor)
------------------------------------------------------------------
ค่า default ออกแบบให้ "รันได้ทันที" บนเครื่อง dev:
  - DB = SQLite (ไฟล์ ./rejoin.db)  → production ใช้ PostgreSQL ผ่าน DATABASE_URL
  - Redis ว่าง → ใช้ fakeredis (in-process)  → production ใส่ REDIS_URL
  - ไม่มี Discord creds → เปิด /auth/dev สำหรับล็อกอินจำลอง

ตัวอย่าง production (.env):
  DATABASE_URL=postgresql+asyncpg://rejoin:pass@localhost:5432/rejoin
  REDIS_URL=redis://localhost:6379/0
  SESSION_SECRET=<สุ่มยาวๆ>
  DISCORD_CLIENT_ID=...
  DISCORD_CLIENT_SECRET=...
  DISCORD_REDIRECT_URI=https://example.com/auth/discord/callback
  COOKIE_SECURE=true
  DEV_AUTH=false
"""
from __future__ import annotations

import os
from dataclasses import dataclass


# โหลดไฟล์ .env อัตโนมัติ (ถ้ามี) — ทำให้รัน dev แล้วอ่านค่า Discord ได้เลย
# ไม่มี .env / ไม่มี python-dotenv ก็ยังรันได้ (ใช้ค่า default หรือ env ของระบบ)
try:
    from dotenv import load_dotenv

    load_dotenv()
except Exception:  # pragma: no cover - python-dotenv ไม่มีก็ข้าม
    pass


def _env_bool(name: str, default: bool) -> bool:
    v = os.getenv(name)
    if v is None:
        return default
    return v.strip().lower() in ("1", "true", "yes", "on")


def _env_int(name: str, default: int) -> int:
    v = os.getenv(name)
    try:
        return int(v) if v is not None else default
    except ValueError:
        return default


@dataclass
class Settings:
    # ---- infra ----
    database_url: str = "sqlite+aiosqlite:///./rejoin.db"
    redis_url: str = ""  # ว่าง = fakeredis (dev เท่านั้น)

    # ---- security / session ----
    session_secret: str = "dev-insecure-change-me"
    cookie_secure: bool = False
    session_max_age: int = 60 * 60 * 24 * 14  # 14 วัน

    # ---- Discord OAuth ----
    discord_client_id: str = ""
    discord_client_secret: str = ""
    discord_redirect_uri: str = "http://127.0.0.1:8000/auth/discord/callback"
    # ลิงก์ชวนเข้าเซิร์ฟเวอร์ Discord (แสดงปุ่ม "เข้าร่วมชุมชน")
    discord_invite_url: str = "https://discord.gg/N7Kuayuzxb"

    # ---- dev conveniences ----
    dev_auth: bool = True  # /auth/dev (ปิดใน production)

    # ---- watchdog (ฝั่งเว็บใช้ตัดสิน offline) ----
    offline_after_sec: int = 30
    silence_sec: int = 60
    heartbeat_interval_sec: int = 15
    last_seen_ttl_sec: int = 120

    # ---- ตัวรัน (Runner) — ลิงก์ไปหน้าระบบบายพาส (ยังไม่ทำ) ----
    runner_url: str = ""  # ว่าง = ยังไม่เปิดใช้งาน (หน้า /bypass จะโชว์ "กำลังพัฒนา")

    # ---- ที่เก็บไฟล์ให้ดาวน์โหลด ----
    lua_dir: str = "skeleton/lua"
    apk_path: str = ""  # ว่าง = หาใน dist/*.apk อัตโนมัติ
    # ลิงก์ดาวน์โหลด APK สำรอง (ใช้เมื่อไม่มีไฟล์ในเครื่อง เช่น บน production)
    # ค่าเริ่มต้นชี้ไป GitHub Release "apk-latest" ที่ GitHub Actions อัปโหลดให้อัตโนมัติ
    apk_url: str = (
        "https://github.com/ffxlm/rejoin-cloud/releases/download/apk-latest/rejoin-agent-debug.apk"
    )

    # ---- retention ของประวัติเหตุการณ์ (events) ----
    event_retention_days: int = 30     # ลบเหตุการณ์ที่เก่ากว่านี้
    event_max_per_device: int = 200    # เก็บต่อเครื่องไว้ไม่เกินกี่แถวล่าสุด
    retention_interval_sec: int = 6 * 3600  # ทำงานลบของเก่าซ้ำทุกกี่วินาที

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            database_url=os.getenv("DATABASE_URL", cls.database_url),
            redis_url=os.getenv("REDIS_URL", cls.redis_url),
            session_secret=os.getenv("SESSION_SECRET", cls.session_secret),
            cookie_secure=_env_bool("COOKIE_SECURE", cls.cookie_secure),
            session_max_age=_env_int("SESSION_MAX_AGE", cls.session_max_age),
            discord_client_id=os.getenv("DISCORD_CLIENT_ID", cls.discord_client_id),
            discord_client_secret=os.getenv("DISCORD_CLIENT_SECRET", cls.discord_client_secret),
            discord_redirect_uri=os.getenv("DISCORD_REDIRECT_URI", cls.discord_redirect_uri),
            discord_invite_url=os.getenv("DISCORD_INVITE_URL", cls.discord_invite_url),
            dev_auth=_env_bool("DEV_AUTH", cls.dev_auth),
            offline_after_sec=_env_int("OFFLINE_AFTER_SEC", cls.offline_after_sec),
            silence_sec=_env_int("SILENCE_SEC", cls.silence_sec),
            heartbeat_interval_sec=_env_int("HEARTBEAT_INTERVAL_SEC", cls.heartbeat_interval_sec),
            last_seen_ttl_sec=_env_int("LAST_SEEN_TTL_SEC", cls.last_seen_ttl_sec),
            runner_url=os.getenv("RUNNER_URL", cls.runner_url),
            lua_dir=os.getenv("LUA_DIR", cls.lua_dir),
            apk_path=os.getenv("APK_PATH", cls.apk_path),
            apk_url=os.getenv("APK_URL", cls.apk_url),
            event_retention_days=_env_int(
                "EVENT_RETENTION_DAYS", cls.event_retention_days
            ),
            event_max_per_device=_env_int(
                "EVENT_MAX_PER_DEVICE", cls.event_max_per_device
            ),
            retention_interval_sec=_env_int(
                "RETENTION_INTERVAL_SEC", cls.retention_interval_sec
            ),
        )

    @property
    def discord_enabled(self) -> bool:
        return bool(self.discord_client_id and self.discord_client_secret)

    def resolve_apk_path(self) -> str | None:
        """ที่อยู่ไฟล์ APK จริง — ใช้ APK_PATH ถ้าตั้งไว้ ไม่งั้นลองหาใน dist/*.apk"""
        if self.apk_path and os.path.isfile(self.apk_path):
            return self.apk_path
        import glob

        candidates = sorted(glob.glob(os.path.join("dist", "*.apk")))
        return candidates[0] if candidates else None
