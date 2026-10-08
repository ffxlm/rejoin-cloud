"""
watchdog.py — หัวใจของระบบ (pure logic, testable)
------------------------------------------------------------------
Dead-man's switch: เฝ้า "ความเงียบ" ของ Lua ไม่ใช่รอให้ Lua บอกว่าตาย

ออกแบบให้เป็น pure state machine:
  - ไม่มี I/O, ไม่มีเวลาจริง → รับ `now` เข้ามา (fake clock ได้)
  - รับ observation (game_running / lua_age) → คืน action ที่ต้องทำ

สถานะ:
  OFFLINE → CONNECTED → GAME_RUNNING → LUA_ACTIVE → ARMED
  ARMED + เงียบ → REJOINING → (กลับเป็น ARMED / เกินกำหนด → ALERT)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional


class Phase(str, Enum):
    OFFLINE = "offline"
    CONNECTED = "connected"
    GAME_RUNNING = "game_running"
    LUA_ACTIVE = "lua_active"
    ARMED = "armed"
    REJOINING = "rejoining"
    ALERT = "alert"


class Action(str, Enum):
    NONE = "none"
    REJOIN = "rejoin"      # force-stop + เปิดเกมใหม่ + inject Lua
    LAUNCH = "launch"      # เกมไม่ได้รัน → เปิดเกม
    ALERT = "alert"        # กู้ไม่ได้ ต้องให้คนดู


@dataclass
class Observation:
    online: bool = False
    game_running: bool = False
    lua_age_sec: Optional[int] = None   # None = ไม่มี state จาก Lua


@dataclass
class Config:
    silence_sec: int = 60          # เงียบนานเท่านี้ = ตัดสินว่าตาย
    rejoin_timeout_sec: int = 90   # รอกู้กี่วิก่อนถือว่าล้มเหลว
    backoff_sec: tuple = (30, 60, 120)  # หน่วงระหว่างครั้ง (กัน rejoin storm)
    max_attempts: int = 3          # เกินนี้ → alert


@dataclass
class Watchdog:
    cfg: Config = field(default_factory=Config)

    # ---- state ----
    phase: Phase = Phase.OFFLINE
    armed: bool = False
    attempts: int = 0
    rejoin_started_at: Optional[int] = None
    next_allowed_at: int = 0
    last_rejoin_at: Optional[int] = None
    rejoin_count: int = 0

    # ---------- public ----------
    def arm(self, now: int) -> None:
        self.armed = True
        self.attempts = 0
        self.rejoin_started_at = None
        self.next_allowed_at = 0

    def disarm(self) -> None:
        self.armed = False
        self.rejoin_started_at = None
        self.attempts = 0

    def observe(self, now: int, obs: Observation) -> List[Action]:
        """รับ observation แล้วคืน action ที่ต้องทำ (0 หรือ 1 อย่าง)"""
        # ---- สถานะพื้นฐาน (ไม่ว่า armed หรือไม่) ----
        base = self._base_phase(obs)

        if not self.armed:
            self.phase = base
            return []

        # armed: เฝ้าความเงียบ
        alive = obs.online and obs.lua_age_sec is not None \
            and obs.lua_age_sec <= self.cfg.silence_sec

        if alive:
            # กลับมาแล้ว → รีเซ็ต
            self.phase = Phase.ARMED
            self.attempts = 0
            self.rejoin_started_at = None
            self.next_allowed_at = 0
            return []

        # ---- เงียบ / เกมหลุด ----
        # กำลังรอผลการกู้?
        if self.rejoin_started_at is not None:
            if now - self.rejoin_started_at < self.cfg.rejoin_timeout_sec:
                self.phase = Phase.REJOINING
                return []  # ยังรออยู่
            # หมดเวลา = ครั้งนี้ล้มเหลว
            self.attempts += 1
            self.rejoin_started_at = None
            if self.attempts >= self.cfg.max_attempts:
                self.phase = Phase.ALERT
                return [Action.ALERT]
            delay = self.cfg.backoff_sec[min(self.attempts - 1, len(self.cfg.backoff_sec) - 1)]
            self.next_allowed_at = now + delay
            self.phase = Phase.REJOINING
            return []

        # อยู่ในช่วง backoff?
        if now < self.next_allowed_at:
            self.phase = Phase.REJOINING
            return []

        # ---- ลงมือกู้ ----
        self.rejoin_started_at = now
        self.last_rejoin_at = now
        self.rejoin_count += 1
        self.phase = Phase.REJOINING
        action = Action.REJOIN if obs.game_running else Action.LAUNCH
        return [action]

    # ---------- helpers ----------
    def _base_phase(self, obs: Observation) -> Phase:
        if not obs.online:
            return Phase.OFFLINE
        alive = obs.lua_age_sec is not None and obs.lua_age_sec <= self.cfg.silence_sec
        if alive:
            return Phase.ARMED if self.armed else Phase.LUA_ACTIVE
        if obs.game_running:
            return Phase.GAME_RUNNING
        return Phase.CONNECTED
