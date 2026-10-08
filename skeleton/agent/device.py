"""
device.py — การกระทำกับเครื่อง (ผ่าน adb)
------------------------------------------------------------------
รวบรวมคำสั่งที่ "APK Agent" ต้องทำ รวมที่เดียว เพื่อย้ายไป Kotlin ทีหลังได้ง่าย:
  - เช็คเกมรัน
  - force-stop เกม
  - เปิดเกม (deep link เข้าแมพ)
  - ยัด Lua (atomic + backup)
  - อ่าน lua_state.json
  - แคปหน้าจอ (screencap -p)
"""
from __future__ import annotations

import json
import os
import subprocess
from typing import Optional

GAME_PKG = "com.roblox.client"
LUA_DIR = "/storage/emulated/0/Delta/Autoexecute"
LUA_FILE = f"{LUA_DIR}/rejoin_agent.lua"
STATE_FILE = "/storage/emulated/0/Delta/Workspace/lua_state.json"


class Device:
    def __init__(self, adb_bin: str, serial: str):
        self.adb = adb_bin
        self.serial = serial

    def _run(self, args, root=False, timeout=15) -> str:
        cmd = [self.adb, "-s", self.serial, "shell"]
        if root:
            cmd += ["su", "-c"]
        cmd += args if isinstance(args, list) else [args]
        try:
            out = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
            return out.stdout.strip()
        except Exception as e:
            return f"__ERR__ {e}"

    # ---------- ตรวจสอบ ----------
    def game_running(self) -> bool:
        pid = self._run(["pidof", GAME_PKG], root=True)
        return bool(pid) and not pid.startswith("__ERR__")

    def read_state(self) -> Optional[dict]:
        raw = self._run(["cat", STATE_FILE], root=True)
        if raw.startswith("__ERR__") or not raw:
            return None
        try:
            return json.loads(raw)
        except Exception:
            return None

    # ---------- กระทำ ----------
    def force_stop(self) -> None:
        self._run(["am", "force-stop", GAME_PKG], root=True)

    def launch(self, place_id: int) -> None:
        self._run([
            "am", "start", "-a", "android.intent.action.VIEW",
            "-d", f"roblox://placeId={place_id}", GAME_PKG,
        ], root=True)

    def push_lua(self, local_path: str) -> bool:
        """ยัด Lua แบบ atomic + backup ไฟล์เดิม"""
        tmp = f"{LUA_FILE}.tmp"
        # 1) push ไป tmp
        p = subprocess.run([self.adb, "-s", self.serial, "push", local_path, tmp],
                           capture_output=True, text=True, timeout=30)
        if p.returncode != 0:
            return False
        # 2) backup ของเดิม (ถ้ามี) แล้ว rename ทับ
        self._run(
            f"cd {LUA_DIR} && "
            f"[ -f rejoin_agent.lua ] && cp rejoin_agent.lua rejoin_agent.lua.bak; "
            f"mv rejoin_agent.lua.tmp rejoin_agent.lua && "
            f"chmod 664 rejoin_agent.lua",
            root=True,
        )
        return True

    # ---------- แคปหน้าจอ ----------
    def capture_screenshot(self, local_path: str, timeout: int = 25) -> bool:
        """แคปหน้าจอผ่าน adb (screencap -p) → เขียนเป็น PNG ลง local_path"""
        try:
            with open(local_path, "wb") as f:
                p = subprocess.run(
                    [self.adb, "-s", self.serial, "exec-out", "screencap", "-p"],
                    stdout=f, stderr=subprocess.DEVNULL, timeout=timeout,
                )
            return p.returncode == 0 and os.path.getsize(local_path) > 0
        except Exception:
            return False
