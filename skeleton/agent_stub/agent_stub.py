#!/usr/bin/env python3
"""
agent_stub.py — จำลอง APK Agent (Walking Skeleton)
------------------------------------------------------------------
ทำหน้าที่แทน APK ชั่วคราว จนกว่าจะมี APK จริง:
  1) อ่าน lua_state.json จากเครื่องผ่าน adb (จำลอง APK อ่านไฟล์)
  2) เทียบ ts -> คำนวณ lua_age_sec (dead-man's switch)
  3) เช็คโปรเซสเกม (game_running)
  4) POST /api/agent/heartbeat ไป backend

รัน:
    python3 skeleton/agent_stub/agent_stub.py \
        --adb .tools/platform-tools/adb \
        --device 192.168.96.160:5555 \
        --server http://127.0.0.1:8000 \
        --code DEMO-0001
"""
import argparse
import json
import subprocess
import time
import urllib.request

LUA_STATE_PATH = "/storage/emulated/0/Delta/Workspace/lua_state.json"
GAME_PKG = "com.roblox.client"
SILENCE_THRESHOLD = 60


def adb(args, serial, adb_bin, root=False):
    cmd = [adb_bin, "-s", serial]
    if root:
        cmd += ["shell", "su", "-c"]
    else:
        cmd += ["shell"]
    cmd += args if isinstance(args, list) else [args]
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        return out.stdout.strip()
    except Exception as e:
        return f"__ERR__ {e}"


def read_lua_state(adb_bin, serial):
    raw = adb(["cat", LUA_STATE_PATH], serial, adb_bin, root=True)
    if raw.startswith("__ERR__") or not raw:
        return None
    try:
        return json.loads(raw)
    except Exception:
        return None


def game_running(adb_bin, serial):
    pid = adb(["pidof", GAME_PKG], serial, adb_bin, root=True)
    return bool(pid) and not pid.startswith("__ERR__")


def post_json(url, data, token=None):
    body = json.dumps(data).encode()
    req = urllib.request.Request(url, data=body, method="POST")
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read().decode())
    except Exception as e:
        return {"error": str(e)}


def register(server, code, adb_bin, serial):
    return post_json(f"{server}/api/agent/register", {
        "device_code": code,
        "apk_version": "stub-0.1",
        "android_id": serial,
    })


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--adb", default=".tools/platform-tools/adb")
    ap.add_argument("--device", required=True)
    ap.add_argument("--server", default="http://127.0.0.1:8000")
    ap.add_argument("--code", default="DEMO-0001")
    ap.add_argument("--interval", type=int, default=10)
    args = ap.parse_args()

    reg = register(args.server, args.code, args.adb, args.device)
    token = reg.get("device_token")
    print(f"[stub] registered: {reg}", flush=True)
    if not token:
        print("[stub] register failed, abort", flush=True)
        return

    session_start = int(time.time())
    while True:
        state = read_lua_state(args.adb, args.device)
        running = game_running(args.adb, args.device)

        lua_active = False
        lua_age = None
        payload = {
            "v": 1,
            "game_running": running,
            "lua_active": False,
            "session_start": session_start,
            "ts": int(time.time()),
        }
        if state:
            age = int(time.time()) - int(state.get("ts", 0))
            lua_age = age
            lua_active = age <= SILENCE_THRESHOLD
            payload.update({
                "lua_active": lua_active,
                "lua_age_sec": age,
                "avatar": state.get("avatar"),
                "character": state.get("character"),
                "map": state.get("map"),
            })
        payload["state"] = "armed" if lua_active else ("game_running" if running else "connected")

        resp = post_json(f"{args.server}/api/agent/heartbeat", payload, token)
        print(f"[stub] game={running} lua_active={lua_active} age={lua_age}s -> {resp}", flush=True)
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
