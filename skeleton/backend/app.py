"""
app.py — Rejoin Backend (FastAPI) — ของจริง (Postgres/Redis) + dev fallback
==================================================================
แทนที่ walking skeleton (in-memory) ด้วย:
  - PostgreSQL (SQLAlchemy async) — dev ใช้ SQLite อัตโนมัติ
  - Redis (last_seen TTL + คิวคำสั่ง) — dev ใช้ fakeredis
  - Discord OAuth2 + session cookie — dev เปิด /auth/dev
  - รหัสเครื่องแบบ hash (Argon2 + lookup sha256), revoke ได้
  - event log ลง DB

รัน (dev):
    .venv/bin/uvicorn skeleton.backend.app:app --host 0.0.0.0 --port 8000
รัน (production): ตั้ง env ตาม .env.example (DATABASE_URL, REDIS_URL, DISCORD_*, ...)
"""
from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager, suppress

from fastapi import Depends, FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.middleware.sessions import SessionMiddleware

from .config import Settings
from .db import Base, build_engine, build_sessionmaker, ensure_schema
from .deps import get_db, get_store
from .events import cleanup_old_events
from .models import Device, Event, User
from .redis_store import Store, build_store
from .routers import agent as agent_router
from .routers import admin as admin_router
from .routers import auth as auth_router
from .routers import device as device_router
from .routers import me as me_router
from .routers.admin import build_device_rows, build_overview, build_user_rows
from .serializers import build_device_view, user_public

TEMPLATES_DIR = os.path.join(os.path.dirname(__file__), "templates")
templates = Jinja2Templates(directory=TEMPLATES_DIR)


def _human_size(n: int) -> str:
    """แปลงขนาดไฟล์เป็นข้อความอ่านง่าย เช่น 6.8 MB"""
    size = float(n)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} GB"


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_env()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        engine = build_engine(settings.database_url)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            await conn.run_sync(ensure_schema)
        app.state.settings = settings
        app.state.engine = engine
        app.state.sessionmaker = build_sessionmaker(engine)
        app.state.store = build_store(settings.redis_url, settings.last_seen_ttl_sec)

        async def _run_retention() -> None:
            """ลบเหตุการณ์ที่เก่ากว่า retention (best-effort)"""
            try:
                async with app.state.sessionmaker() as session:
                    await cleanup_old_events(session, settings)
            except Exception:
                pass

        # ลบของเก่าตอนเริ่มระบบ + ทำซ้ำเป็นรอบ ๆ ระหว่างรัน (กัน DB บวม)
        await _run_retention()

        async def _retention_loop() -> None:
            while True:
                await asyncio.sleep(settings.retention_interval_sec)
                await _run_retention()

        retention_task = asyncio.create_task(_retention_loop())
        try:
            yield
        finally:
            retention_task.cancel()
            with suppress(asyncio.CancelledError):
                await retention_task
            await app.state.store.close()
            await engine.dispose()

    app = FastAPI(title="Rejoin Backend", version="1.0.0", lifespan=lifespan)
    # ตัวแปรที่ทุก template เข้าถึงได้ (ปุ่ม "เข้าร่วมชุมชน" ใช้ร่วมกันทุกหน้า)
    templates.env.globals["discord_invite_url"] = settings.discord_invite_url
    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.session_secret,
        max_age=settings.session_max_age,
        https_only=settings.cookie_secure,
    )

    app.include_router(auth_router.router)
    app.include_router(me_router.router)
    app.include_router(agent_router.router)
    app.include_router(device_router.router)
    app.include_router(admin_router.router)

    _AUTH_ERRORS = {
        "denied": "คุณยกเลิกการเข้าสู่ระบบ หรือไม่อนุญาตสิทธิ์ กรุณาลองใหม่",
        "state": "เซสชันล็อกอินหมดอายุหรือไม่ถูกต้อง กรุณาลองใหม่อีกครั้ง",
        "token": "เชื่อมต่อ Discord ไม่สำเร็จ (แลก token) กรุณาลองใหม่",
        "profile": "ดึงข้อมูลผู้ใช้จาก Discord ไม่สำเร็จ กรุณาลองใหม่",
        "discord": "Discord ตอบกลับข้อผิดพลาด กรุณาลองใหม่",
    }

    def _login_response(request: Request) -> HTMLResponse:
        err = request.query_params.get("auth_error")
        return templates.TemplateResponse(
            request,
            "login.html",
            {
                "discord_enabled": settings.discord_enabled,
                "auth_error": _AUTH_ERRORS.get(err) if err else None,
            },
        )

    async def _current_user(request: Request, db: AsyncSession) -> User | None:
        uid = request.session.get("user_id")
        if not uid:
            return None
        user = await db.get(User, uid)
        if user is None:
            request.session.clear()
            return None
        return user

    @app.get("/health")
    async def health(store: Store = Depends(get_store)):
        return {"ok": True, "redis": await store.ping(), "db": settings.database_url.split("://")[0]}

    @app.get("/", response_class=HTMLResponse)
    async def dashboard(
        request: Request,
        db: AsyncSession = Depends(get_db),
        store: Store = Depends(get_store),
    ):
        user = await _current_user(request, db)
        if user is None:
            return _login_response(request)

        devices = (
            await db.execute(select(Device).where(Device.user_id == user.id).order_by(Device.id))
        ).scalars().all()
        views = [
            await build_device_view(d, store, settings, rejoin_count=d.rejoin_total or 0)
            for d in devices
        ]

        events = (
            await db.execute(
                select(Event)
                .where(Event.device_id.in_([d.id for d in devices]) if devices else False)
                .order_by(Event.ts.desc())
                .limit(400)
            )
        ).scalars().all() if devices else []

        # ---- สรุปภาพรวม (ภาษาคน) ----
        import time as _time
        now = int(_time.time())
        name_by_id = {d.id: d.name for d in devices}
        armed_count = sum(1 for v in views if v["status"] == "armed")
        problem_count = sum(1 for v in views if v["status"] in ("alert", "offline"))
        total_rejoins = sum(v["rejoin_count"] for v in views)

        def _ago(ts: int) -> str:
            sec = max(0, now - ts)
            if sec < 60:
                return f"{sec} วินาทีที่แล้ว"
            if sec < 3600:
                return f"{sec // 60} นาทีที่แล้ว"
            if sec < 86400:
                return f"{sec // 3600} ชั่วโมงที่แล้ว"
            return f"{sec // 86400} วันที่แล้ว"

        def _event_view(e: Event) -> dict:
            ts = int(e.ts.timestamp())
            return {"type": e.type, "ts": ts, "ago": _ago(ts), "detail": e.detail or {}}

        # จัดกลุ่มเหตุการณ์ "แยกตามเครื่อง" (แต่ละการ์ดมีของตัวเอง)
        # ประวัติโชว์ได้เยอะขึ้น แต่ฝั่ง UI เป็นกล่องเลื่อน (ไม่ให้หน้ายาว)
        MAX_EVENTS = 50
        events_by_dev: dict[int, list] = {}
        for e in events:
            bucket = events_by_dev.setdefault(e.device_id, [])
            if len(bucket) < MAX_EVENTS:
                bucket.append(_event_view(e))

        panels = [
            {
                **v,
                "session_start_ago": _ago(v["session_start"]) if v["session_start"] else None,
                "last_seen_ago": (
                    _ago(now - v["last_seen_age_sec"]) if v["last_seen_age_sec"] is not None else None
                ),
                "events": events_by_dev.get(d.id, []),
            }
            for d, v in zip(devices, views)
        ]

        return templates.TemplateResponse(
            request,
            "dashboard.html",
            {
                "user": user_public(user),
                "active": "dashboard",
                "devices": views,
                "panels": panels,
                "armed_count": armed_count,
                "problem_count": problem_count,
                "total_rejoins": total_rejoins,
                "discord_enabled": settings.discord_enabled,
                "dev_auth": settings.dev_auth,
            },
        )

    @app.get("/guide", response_class=HTMLResponse)
    async def guide(request: Request, db: AsyncSession = Depends(get_db)):
        user = await _current_user(request, db)
        if user is None:
            return _login_response(request)
        return templates.TemplateResponse(
            request,
            "guide.html",
            {"user": user_public(user), "active": "guide"},
        )

    @app.get("/bypass", response_class=HTMLResponse)
    async def bypass(request: Request, db: AsyncSession = Depends(get_db)):
        user = await _current_user(request, db)
        if user is None:
            return _login_response(request)
        return templates.TemplateResponse(
            request,
            "bypass.html",
            {
                "user": user_public(user),
                "active": "bypass",
                "runner_url": settings.runner_url,
            },
        )

    @app.get("/download", response_class=HTMLResponse)
    async def download(request: Request, db: AsyncSession = Depends(get_db)):
        user = await _current_user(request, db)
        if user is None:
            return _login_response(request)

        apk = None
        apk_path = settings.resolve_apk_path()
        if apk_path:
            apk = {
                "name": os.path.basename(apk_path),
                "size": _human_size(os.path.getsize(apk_path)),
                "remote": False,
            }
        elif settings.apk_url:
            # ไม่มีไฟล์ในเครื่อง (production) → ให้ดาวน์โหลดจาก GitHub Release
            apk = {
                "name": os.path.basename(settings.apk_url) or "rejoin-agent-debug.apk",
                "size": None,
                "remote": True,
            }
        lua_path = os.path.join(settings.lua_dir, "rejoin_agent.lua")
        return templates.TemplateResponse(
            request,
            "download.html",
            {
                "user": user_public(user),
                "active": "download",
                "apk": apk,
                "apk_version": settings.apk_version,
                "lua_ok": os.path.isfile(lua_path),
            },
        )

    @app.get("/admin", response_class=HTMLResponse)
    async def admin_panel(
        request: Request,
        db: AsyncSession = Depends(get_db),
        store: Store = Depends(get_store),
    ):
        user = await _current_user(request, db)
        if user is None:
            return _login_response(request)
        # ปุ่มในเมนูโชว์เฉพาะแอดมิน — แต่ต้องกันที่ฝั่งเซิร์ฟเวอร์ด้วย (เข้า URL ตรง ๆ)
        if not user.is_admin:
            return templates.TemplateResponse(
                request,
                "forbidden.html",
                {"user": user_public(user)},
                status_code=403,
            )

        overview = await build_overview(db, store, settings)
        return templates.TemplateResponse(
            request,
            "admin.html",
            {
                "user": user_public(user),
                "active": "admin",
                "overview": overview,
                "users": await build_user_rows(db),
                "devices": await build_device_rows(db, store, settings),
            },
        )

    return app


app = create_app()
