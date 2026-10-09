"""
routers/auth.py — ล็อกอินด้วย Discord OAuth2 (session cookie)
------------------------------------------------------------------
- GET  /auth/discord            → redirect ไป Discord (มี state กัน CSRF)
- GET  /auth/discord/callback   → แลก code → สร้าง/อัปเดต user → set session
- POST /auth/logout             → ล้าง session
- GET  /auth/dev                → ล็อกอินจำลอง (เฉพาะ DEV_AUTH=true)
- GET  /api/me                  → ข้อมูลผู้ใช้ปัจจุบัน

ข้อผิดพลาดระหว่างล็อกอินจะ redirect กลับหน้าแรกพร้อม ?auth_error=<รหัส>
(ให้หน้า login แสดงข้อความภาษาไทย ไม่โชว์ JSON ดิบ)
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

def _login_redirect(error: str) -> RedirectResponse:
    """กลับหน้า login พร้อมรหัสข้อผิดพลาด (UI แปลเป็นข้อความภาษาไทย)"""
    return RedirectResponse(f"/?auth_error={error}", status_code=303)

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
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    if not settings.discord_enabled:
        raise HTTPException(status_code=400, detail="Discord ยังไม่ถูกตั้งค่า")

    # ผู้ใช้กด "ยกเลิก" หรือ Discord ปฏิเสธ → กลับหน้า login พร้อมข้อความ
    if error:
        request.session.pop("oauth_state", None)
        return _login_redirect("denied" if error == "access_denied" else "discord")

    # ตรวจ state ให้ตรงกับที่เก็บใน session (กัน CSRF)
    expected = request.session.pop("oauth_state", None)
    if not code or not state or state != expected:
        return _login_redirect("state")

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
            return _login_redirect("token")
        access_token = tok.json().get("access_token")
        me = await client.get(
            f"{DISCORD_API}/users/@me",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        if me.status_code != 200:
            return _login_redirect("profile")
        info = me.json()

    user = await _upsert_user(
        db,
        discord_id=str(info["id"]),
        username=info.get("username"),
        avatar=info.get("avatar"),
    )
    request.session["user_id"] = user.id
    return RedirectResponse("/", status_code=303)

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
    return RedirectResponse("/", status_code=303)

@router.post("/auth/logout")
async def logout(request: Request):
    request.session.clear()
    return {"ok": True}

@router.get("/api/me")
async def me(user: User = Depends(get_current_user)):
    return user_public(user)
