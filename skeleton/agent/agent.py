#!/usr/bin/env python3
"""
agent.py — Agent orchestrator (จำลอง APK; ย้ายเป็น Kotlin ทีหลัง)
------------------------------------------------------------------
รวม: Device (adb) + Watchdog (logic) + Backend (เว็บ)

loop:
  1) อ่าน lua_state.json + เช็คเกมรัน
  2) ป้อน watchdog → ได้ action
  3) ทำ action (REJOIN / LAUNCH / ALERT)
  4) ส่ง heartbeat + event ไปเว็บ
  5) รับคำสั่ง arm/disarm/rejoin_now/screenshot_now จาก response
  6) แคปหน้าจอ (ตามคำสั่ง / ตอน alert / เป็นรอบ) แล้วอัปขึ้นเว็บ

รัน:
  python3 -m skeleton.agent.agent \
      --adb .tools/platform-tools/adb --device 192.168.96.160:5555 \
      --server http://127.0.0.1:8000 --code DEMO-0001 --place 107778070777162
"""
from __future__ import annotations

import argparse
import json
import os
import tempfile
import time
import urllib.request
from typing import Optional

import httpx

from .device import Device
from .watchdog import Action, Config, Observation, Watchdog


def post_json(url: str, data: dict, token: Optional[str] = None) -> dict:
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


class Agent:
    def __init__(self, adb, serial, server, code, place_id, lua_path,
                 interval=10, cfg: Optional[Config] = None, shot_interval=0):
        self.dev = Device(adb, serial)
        self.server = server.rstrip("/")
        self.code = code
        self.place_id = place_id
        self.lua_path = lua_path
        self.interval = interval
        self.shot_interval = shot_interval  # 0 = ปิด (แคปเฉพาะสั่ง/ตอน alert)
        self.wd = Watchdog(cfg or Config())
        self.token: Optional[str] = None
        self.device_id: Optional[str] = None
        self.session_start = int(time.time())
        self.armed_reported = False
        self.last_shot = 0

    # ---------- backend ----------
    def register(self) -> bool:
        r = post_json(f"{self.server}/api/agent/register", {
            "device_code": self.code, "apk_version": "agent-0.2",
        })
        self.token = r.get("device_token")
        self.device_id = r.get("device_id")
        print(f"[agent] registered: {r}", flush=True)
        return bool(self.token)

    def send_event(self, etype: str, detail: dict) -> None:
        post_json(f"{self.server}/api/agent/event",
                  {"type": etype, "detail": detail}, self.token)

    def send_heartbeat(self, obs: Observation, extra: dict) -> Optional[str]:
        payload = {
            "v": 1,
            "state": self.wd.phase.value,
            "armed": self.wd.armed,
            "game_running": obs.game_running,
            "lua_active": obs.lua_age_sec is not None and obs.lua_age_sec <= self.wd.cfg.silence_sec,
            "lua_age_sec": obs.lua_age_sec,
            "rejoin_count": self.wd.rejoin_count,
            "session_start": self.session_start,
            "ts": int(time.time()),
        }
        payload.update(extra)
        r = post_json(f"{self.server}/api/agent/heartbeat", payload, self.token)
        return r.get("command")

    # ---------- screenshot ----------
    def send_screenshot(self) -> bool:
        """แคปหน้าจอแล้วอัปขึ้นเว็บ (multipart) — คืน True ถ้าสำเร็จ"""
        if not self.token:
            return False
        fd, path = tempfile.mkstemp(suffix=".png", prefix="rejoin_shot_")
        os.close(fd)
        try:
            if not self.dev.capture_screenshot(path):
                print("[agent] screenshot: แคปไม่สำเร็จ", flush=True)
                return False
            with open(path, "rb") as f:
                content = f.read()
            files = {"file": ("screenshot.png", content, "image/png")}
            r = httpx.post(
                f"{self.server}/api/agent/screenshot",
                headers={"Authorization": f"Bearer {self.token}"},
                files=files,
                timeout=30,
            )
            ok = r.status_code == 200
            print(f"[agent] screenshot upload: {r.status_code}", flush=True)
            return ok
        except Exception as e:
            print(f"[agent] screenshot error: {e}", flush=True)
            return False
        finally:
            try:
                os.remove(path)
            except OSError:
                pass

    # ---------- actions ----------
    def do_action(self, action: Action) -> None:
        if action in (Action.REJOIN, Action.LAUNCH):
            print(f"[agent] >>> ACTION {action.value}: restart game", flush=True)
            self.dev.force_stop()
            time.sleep(2)
            self.dev.push_lua(self.lua_path)   # กัน Lua หาย
            self.dev.launch(self.place_id)
            self.send_event("rejoin", {"action": action.value,
                                       "count": self.wd.rejoin_count})
        elif action == Action.ALERT:
            print("[agent] !!! ALERT: กู้ไม่ได้ ต้องให้คนดู", flush=True)
            self.send_event("alert", {"attempts": self.wd.attempts})
            # แคปหลักฐานตอน alert (ให้คนดูว่าเกิดอะไรขึ้น)
            self.send_screenshot()

    # ---------- main loop ----------
    def run(self) -> None:
        if not self.register():
            print("[agent] register failed", flush=True)
            return
        while True:
            state = self.dev.read_state()
            running = self.dev.game_running()

            age = None
            lua_state = None
            extra = {}
            if state:
                try:
                    age = int(time.time()) - int(state.get("ts", 0))
                except Exception:
                    age = None
                lua_state = state.get("state")
                extra = {
                    "avatar": state.get("avatar"),
                    "character": state.get("character"),
                    "map": state.get("map"),
                    "lua_state": lua_state,
                }

            obs = Observation(online=True, game_running=running,
                              lua_age_sec=age, lua_state=lua_state)
            actions = self.wd.observe(int(time.time()), obs)

            for a in actions:
                self.do_action(a)

            cmd = self.send_heartbeat(obs, extra)
            if cmd == "arm" and not self.wd.armed:
                self.wd.arm(int(time.time()))
                print("[agent] armed by web", flush=True)
            elif cmd == "disarm" and self.wd.armed:
                self.wd.disarm()
                print("[agent] disarmed by web", flush=True)
            elif cmd == "screenshot_now":
                print("[agent] screenshot by web", flush=True)
                self.send_screenshot()

            # แคปเป็นรอบเมื่อ arm อยู่ (ถ้าตั้ง shot_interval > 0)
            now = int(time.time())
            if (self.wd.armed and self.shot_interval > 0
                    and now - self.last_shot >= self.shot_interval):
                if self.send_screenshot():
                    self.last_shot = now

            print(f"[agent] phase={self.wd.phase.value} game={running} "
                  f"age={age}s rejoin={self.wd.rejoin_count} actions={[a.value for a in actions]}",
                  flush=True)
            time.sleep(self.interval)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--adb", default=".tools/platform-tools/adb")
    ap.add_argument("--device", required=True)
    ap.add_argument("--server", default="http://127.0.0.1:8000")
    ap.add_argument("--code", default="DEMO-0001")
    ap.add_argument("--place", type=int, default=107778070777162)
    ap.add_argument("--lua", default="skeleton/lua/rejoin_agent.lua")
    ap.add_argument("--interval", type=int, default=10)
    ap.add_argument("--silence", type=int, default=60)
    ap.add_argument("--timeout", type=int, default=300,
                    help="รอกู้กี่วิก่อนถือว่าล้มเหลว (ต้องครอบเวลาโหลดเกม; เน็ตช้าตั้งสูงขึ้นได้)")
    ap.add_argument("--screenshot-interval", type=int, default=0,
                    help="แคปหน้าจออัตโนมัติทุกกี่วิขณะ arm (0 = ปิด; ยังสั่งแคปจากเว็บได้เสมอ)")
    args = ap.parse_args()

    cfg = Config(silence_sec=args.silence, rejoin_timeout_sec=args.timeout)
    agent = Agent(args.adb, args.device, args.server, args.code,
                  args.place, args.lua, args.interval, cfg,
                  shot_interval=args.screenshot_interval)
    agent.run()


if __name__ == "__main__":
    main()
