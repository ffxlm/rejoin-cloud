"""
Walking Skeleton backend (FastAPI)
------------------------------------------------------------------
พิสูจน์ loop บางที่สุด:
    Lua เขียน lua_state.json
      -> agent stub อ่านไฟล์ -> POST /api/agent/heartbeat
      -> backend เก็บสถานะ -> แดชบอร์ดขึ้น alive

ยังไม่มี: auth จริง, DB จริง, screenshot, alert
ใช้ in-memory store พอสำหรับพิสูจน์ loop

รัน:
    .venv/bin/uvicorn skeleton.backend.app:app --host 0.0.0.0 --port 8000
"""
import time
from typing import Optional

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

app = FastAPI(title="Rejoin Walking Skeleton")

# ---- in-memory store (skeleton เท่านั้น) ----
DEVICES: dict[str, dict] = {}   # device_id -> state
TOKENS: dict[str, str] = {}     # device_token -> device_id
CODES: dict[str, str] = {}      # device_code -> device_id
EVENTS: list[dict] = []         # เหตุการณ์ (rejoin/alert/arm)

SILENCE_THRESHOLD = 60          # วินาที


class RegisterIn(BaseModel):
    device_code: str
    apk_version: Optional[str] = None
    android_id: Optional[str] = None


class HeartbeatIn(BaseModel):
    v: int = 1
    state: str = "connected"
    game_running: bool = False
    lua_active: bool = False
    lua_age_sec: Optional[int] = None
    avatar: Optional[str] = None
    character: Optional[str] = None
    map: Optional[str] = None
    rejoin_count: int = 0
    session_start: Optional[int] = None
    ts: Optional[int] = None


class EventIn(BaseModel):
    type: str
    detail: Optional[dict] = None


def _now() -> int:
    return int(time.time())


def _derive_status(d: dict) -> str:
    """คำนวณสถานะจริงจาก last_seen + lua_age (dead-man's switch ฝั่งเว็บ)"""
    age = _now() - d.get("last_seen", 0)
    if age > 30:
        return "offline"
    if d.get("lua_active"):
        return "armed" if d.get("armed") else "lua_active"
    if d.get("game_running"):
        return "game_running"
    return "connected"


@app.post("/api/agent/register")
def register(body: RegisterIn):
    device_id = CODES.get(body.device_code)
    if not device_id:
        # skeleton: ยอมรับ code อะไรก็ได้ สร้างเครื่องใหม่
        device_id = f"dev_{len(DEVICES) + 1}"
        CODES[body.device_code] = device_id
    token = f"tok_{device_id}"
    TOKENS[token] = device_id
    DEVICES.setdefault(device_id, {
        "device_id": device_id,
        "name": f"device {device_id}",
        "armed": False,
        "last_seen": 0,
        "game_running": False,
        "lua_active": False,
        "rejoin_count": 0,
        "session_start": None,
        "avatar": None, "character": None, "map": None,
    })
    return {"device_token": token, "device_id": device_id, "interval_sec": 15}


@app.post("/api/agent/heartbeat")
def heartbeat(body: HeartbeatIn, authorization: Optional[str] = Header(None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "missing bearer token")
    token = authorization.split(" ", 1)[1]
    device_id = TOKENS.get(token)
    if not device_id:
        raise HTTPException(401, "invalid token")

    d = DEVICES[device_id]
    d.update({
        "last_seen": _now(),
        "game_running": body.game_running,
        "lua_active": body.lua_active,
        "lua_age_sec": body.lua_age_sec,
        "avatar": body.avatar,
        "character": body.character,
        "map": body.map,
        "rejoin_count": body.rejoin_count,
        "session_start": body.session_start or d.get("session_start"),
    })
    d["status"] = _derive_status(d)
    # skeleton: คืนคำสั่ง arm/disarm ถ้ามี
    cmd = None
    if d.pop("_pending_arm", False):
        d["armed"] = True
        d["status"] = _derive_status(d)
        cmd = "arm"
    if d.pop("_pending_disarm", False):
        d["armed"] = False
        d["status"] = _derive_status(d)
        cmd = "disarm"
    return {"ok": True, "command": cmd}


@app.get("/api/me/devices")
def list_devices():
    out = []
    for d in DEVICES.values():
        d["status"] = _derive_status(d)
        out.append({k: v for k, v in d.items() if not k.startswith("_")})
    return {"devices": out}


@app.post("/api/agent/event")
def agent_event(body: EventIn, authorization: Optional[str] = Header(None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "missing bearer token")
    token = authorization.split(" ", 1)[1]
    device_id = TOKENS.get(token)
    if not device_id:
        raise HTTPException(401, "invalid token")
    ev = {"device_id": device_id, "type": body.type,
          "detail": body.detail or {}, "ts": _now()}
    EVENTS.append(ev)
    if body.type == "rejoin":
        DEVICES[device_id]["rejoin_count"] = DEVICES[device_id].get("rejoin_count", 0) + 1
    return {"ok": True}


@app.get("/api/me/events")
def list_events(limit: int = 20):
    return {"events": EVENTS[-limit:][::-1]}


@app.post("/api/device/{device_id}/arm")
def arm(device_id: str):
    if device_id not in DEVICES:
        raise HTTPException(404, "no device")
    DEVICES[device_id]["_pending_arm"] = True
    return {"ok": True, "queued": "arm"}


@app.post("/api/device/{device_id}/disarm")
def disarm(device_id: str):
    if device_id not in DEVICES:
        raise HTTPException(404, "no device")
    DEVICES[device_id]["_pending_disarm"] = True
    return {"ok": True, "queued": "disarm"}


@app.get("/health")
def health():
    return {"ok": True, "devices": len(DEVICES), "events": len(EVENTS)}


@app.get("/", response_class=HTMLResponse)
def dashboard():
    rows = ""
    for d in DEVICES.values():
        st = _derive_status(d)
        color = {"armed": "#22c55e", "lua_active": "#eab308", "offline": "#ef4444"}.get(st, "#64748b")
        age = _now() - d.get("last_seen", 0)
        rows += f"""
        <tr>
          <td>{d['device_id']}</td>
          <td><span style="color:{color};font-weight:bold">● {st}</span></td>
          <td>{'✅' if d.get('game_running') else '❌'}</td>
          <td>{'✅' if d.get('lua_active') else '❌'}</td>
          <td>{d.get('avatar') or '-'}</td>
          <td>{d.get('character') or '-'}</td>
          <td>{d.get('map') or '-'}</td>
          <td>{age}s</td>
          <td>{d.get('rejoin_count', 0)}</td>
        </tr>"""
    ev_rows = ""
    for e in EVENTS[-15:][::-1]:
        ev_rows += (f"<tr><td>{e['ts']}</td><td>{e['type']}</td>"
                    f"<td>{e['device_id']}</td><td>{e['detail']}</td></tr>")
    events_html = f"""<h2>Events (ล่าสุด)</h2>
    <table><tr><th>ts</th><th>type</th><th>device</th><th>detail</th></tr>
    {ev_rows or '<tr><td colspan="4">ยังไม่มี event</td></tr>'}</table>"""
    html = f"""<!doctype html><html><head><meta charset="utf-8">
    <meta http-equiv="refresh" content="3">
    <title>Rejoin Skeleton</title>
    <style>body{{font-family:monospace;background:#0f172a;color:#e2e8f0;padding:20px}}
    table{{border-collapse:collapse;width:100%}} td,th{{border:1px solid #334155;padding:6px 10px;text-align:left}}
    th{{background:#1e293b}} h1{{color:#38bdf8}} h2{{color:#38bdf8;margin-top:30px}}</style></head>
    <body><h1>Rejoin — Walking Skeleton</h1>
    <p>dead-man's switch ฝั่งเว็บ: ไม่ได้ยิน heartbeat > 30s = offline</p>
    <table><tr><th>device</th><th>status</th><th>game</th><th>lua</th><th>avatar</th>
    <th>character</th><th>map</th><th>last_seen</th><th>rejoin</th></tr>
    {rows or '<tr><td colspan="9">ยังไม่มีเครื่อง</td></tr>'}</table>
    {events_html}
    </body></html>"""
    return HTMLResponse(html)
