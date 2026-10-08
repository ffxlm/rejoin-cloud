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

import os
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.middleware.sessions import SessionMiddleware

from .config import Settings
from .db import Base, build_engine, build_sessionmaker
from .deps import get_db, get_store
from .models import Device, Event, Screenshot, User
from .redis_store import Store, build_store
from .routers import agent as agent_router
from .routers import auth as auth_router
from .routers import device as device_router
from .routers import me as me_router
from .screenshots import cleanup_old_screenshots
from .serializers import build_device_view, user_public

TEMPLATES_DIR = os.path.join(os.path.dirname(__file__), "templates")
templates = Jinja2Templates(directory=TEMPLATES_DIR)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_env()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        engine = build_engine(settings.database_url)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        app.state.settings = settings
        app.state.engine = engine
        app.state.sessionmaker = build_sessionmaker(engine)
        app.state.store = build_store(settings.redis_url, settings.last_seen_ttl_sec)
        # ลบภาพหน้าจอที่เก่ากว่า retention ตอนเริ่มระบบ
        try:
            async with app.state.sessionmaker() as session:
                await cleanup_old_screenshots(session, settings)
        except Exception:
            pass
        try:
            yield
        finally:
            await app.state.store.close()
            await engine.dispose()

    app = FastAPI(title="Rejoin Backend", version="1.0.0", lifespan=lifespan)
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

    os.makedirs(settings.screenshot_dir, exist_ok=True)
    app.mount(
        "/screenshots",
        StaticFiles(directory=settings.screenshot_dir, check_dir=False),
        name="screenshots",
    )

    def _login_response(request: Request) -> HTMLResponse:
        return templates.TemplateResponse(
            request,
            "login.html",
            {"discord_enabled": settings.discord_enabled, "dev_auth": settings.dev_auth},
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
        counts = {}
        if devices:
            rows = (
                await db.execute(
                    select(Event.device_id, func.count(Event.id))
                    .where(Event.device_id.in_([d.id for d in devices]), Event.type == "rejoin")
                    .group_by(Event.device_id)
                )
            ).all()
            counts = {r[0]: r[1] for r in rows}

        views = [
            await build_device_view(d, store, settings, rejoin_count=counts.get(d.id, 0))
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

        shots = (
            await db.execute(
                select(Screenshot)
                .where(Screenshot.device_id.in_([d.id for d in devices]) if devices else False)
                .order_by(Screenshot.ts.desc())
                .limit(120)
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

        def _shot_view(s: Screenshot) -> dict:
            ts = int(s.ts.timestamp())
            return {"id": s.id, "url": s.url, "ts": ts, "ago": _ago(ts)}

        # จัดกลุ่มภาพ + เหตุการณ์ "แยกตามเครื่อง" (แต่ละการ์ดมีของตัวเอง)
        MAX_EVENTS, MAX_SHOTS = 8, 6
        events_by_dev: dict[int, list] = {}
        for e in events:
            bucket = events_by_dev.setdefault(e.device_id, [])
            if len(bucket) < MAX_EVENTS:
                bucket.append(_event_view(e))
        shots_by_dev: dict[int, list] = {}
        for s in shots:
            bucket = shots_by_dev.setdefault(s.device_id, [])
            if len(bucket) < MAX_SHOTS:
                bucket.append(_shot_view(s))

        panels = [
            {
                **v,
                "session_start_ago": _ago(v["session_start"]) if v["session_start"] else None,
                "last_seen_ago": (
                    _ago(now - v["last_seen_age_sec"]) if v["last_seen_age_sec"] is not None else None
                ),
                "events": events_by_dev.get(d.id, []),
                "screenshots": shots_by_dev.get(d.id, []),
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

    return app


app = create_app()
