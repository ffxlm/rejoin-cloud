"""
routers/auth.py — ล็อกอินด้วย Discord OAuth2 (session cookie)
------------------------------------------------------------------
- GET  /auth/discord            → redirect ไป Discord
- GET  /auth/discord/callback   → แลก code → สร้าง/อัปเดต user → set session
- POST /auth/logout             → ล้าง session
- GET  /auth/dev                → ล็อกอินจำลอง (เฉพาะ DEV_AUTH=true)
- GET  /api/me                  → ข้อมูลผู้ใช้ปัจจุบัน
"""
from __future__ import annotations

import secrets
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import Settings
from ..deps import get_current_user, get_db, get_settings
from ..models import User
from ..serializers import user_public

router = APIRouter()

DISCORD_API = "https://discord.com/api"
DISCORD_AUTHORIZE = "https://discord.com/oauth2/authorize"


async def _upsert_user(db: AsyncSession, discord_id: str, username: str | None, avatar: str | None) -> User:
    user = (
        await db.execute(select(User).where(User.discord_id == discord_id))
    ).scalar_one_or_none()
    if user is None:
        user = User(discord_id=discord_id, username=username, avatar=avatar)
        db.add(user)
    else:
        user.username = username
        user.avatar = avatar
    await db.commit()
    await db.refresh(user)
    return user


@router.get("/auth/discord")
async def discord_login(request: Request, settings: Settings = Depends(get_settings)):
    if not settings.discord_enabled:
        raise HTTPException(status_code=400, detail="Discord ยังไม่ถูกตั้งค่า (DISCORD_CLIENT_ID/SECRET)")
    state = secrets.token_urlsafe(16)
    request.session["oauth_state"] = state
    params = {
        "client_id": settings.discord_client_id,
        "redirect_uri": settings.discord_redirect_uri,
        "response_type": "code",
        "scope": "identify",
        "state": state,
    }
    return RedirectResponse(f"{DISCORD_AUTHORIZE}?{urlencode(params)}")


@router.get("/auth/discord/callback")
async def discord_callback(
    request: Request,
    code: str,
    state: str,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    if not settings.discord_enabled:
        raise HTTPException(status_code=400, detail="Discord ยังไม่ถูกตั้งค่า")
    if not state or state != request.session.get("oauth_state"):
        raise HTTPException(status_code=400, detail="state ไม่ถูกต้อง (กัน CSRF)")
    request.session.pop("oauth_state", None)

    async with httpx.AsyncClient(timeout=15) as client:
        tok = await client.post(
            f"{DISCORD_API}/oauth2/token",
            data={
                "client_id": settings.discord_client_id,
                "client_secret": settings.discord_client_secret,
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": settings.discord_redirect_uri,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        if tok.status_code != 200:
            raise HTTPException(status_code=400, detail="แลก token กับ Discord ไม่สำเร็จ")
        access_token = tok.json().get("access_token")
        me = await client.get(
            f"{DISCORD_API}/users/@me",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        if me.status_code != 200:
            raise HTTPException(status_code=400, detail="ดึงข้อมูลผู้ใช้จาก Discord ไม่สำเร็จ")
        info = me.json()

    user = await _upsert_user(
        db,
        discord_id=str(info["id"]),
        username=info.get("username"),
        avatar=info.get("avatar"),
    )
    request.session["user_id"] = user.id
    return RedirectResponse("/")


@router.get("/auth/dev")
async def dev_login(
    request: Request,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    """ล็อกอินจำลองสำหรับ dev — ปิดได้ด้วย DEV_AUTH=false"""
    if not settings.dev_auth:
        raise HTTPException(status_code=404, detail="not found")
    user = await _upsert_user(db, discord_id="dev-local", username="dev", avatar=None)
    request.session["user_id"] = user.id
    return RedirectResponse("/")


@router.post("/auth/logout")
async def logout(request: Request):
    request.session.clear()
    return {"ok": True}


@router.get("/api/me")
async def me(user: User = Depends(get_current_user)):
    return user_public(user)
