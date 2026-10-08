"""
models.py — Data model ตาม CONTRACT.md §5 (PostgreSQL, แต่รันบน SQLite ได้)
------------------------------------------------------------------
ตาราง: users, devices, device_tokens, device_state, events
หมายเหตุ:
  - ไม่เก็บ device_code/device_token เป็น plaintext → เก็บ lookup (sha256) + hash (Argon2)
  - rejoin_total = ยอดสะสมตลอดชีพ (ไม่ขึ้นกับ retention ของ events) ส่วน runtime
    ยังคำนวณจาก events
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base

# BIGINT บน Postgres, แต่ SQLite ต้องเป็น INTEGER จึง autoincrement ได้
PK = BigInteger().with_variant(Integer, "sqlite")
JSONType = JSON().with_variant(JSONB(), "postgresql")


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(PK, primary_key=True)
    discord_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    username: Mapped[Optional[str]] = mapped_column(String(128))
    avatar: Mapped[Optional[str]] = mapped_column(String(256))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)

    devices: Mapped[List["Device"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class Device(Base):
    __tablename__ = "devices"

    id: Mapped[int] = mapped_column(PK, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(128), default="เครื่องใหม่")
    game_pkg: Mapped[str] = mapped_column(String(128), default="com.roblox.client")
    status: Mapped[str] = mapped_column(String(32), default="offline")
    armed: Mapped[bool] = mapped_column(Boolean, default=False)
    armed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    session_start: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    lua_version: Mapped[Optional[str]] = mapped_column(String(32))
    apk_version: Mapped[Optional[str]] = mapped_column(String(32))
    last_seen: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    rejoin_total: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0"
    )  # ยอดกู้เกมสำเร็จสะสม (ไม่ถูกลบโดย retention)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)

    user: Mapped["User"] = relationship(back_populates="devices")
    tokens: Mapped[List["DeviceToken"]] = relationship(
        back_populates="device", cascade="all, delete-orphan"
    )
    state: Mapped[Optional["DeviceState"]] = relationship(
        back_populates="device", cascade="all, delete-orphan", uselist=False,
        lazy="selectin",
    )


class DeviceToken(Base):
    """รหัสเครื่อง (device_code) และ device_token — เก็บเฉพาะ hash"""

    __tablename__ = "device_tokens"

    id: Mapped[int] = mapped_column(PK, primary_key=True)
    device_id: Mapped[int] = mapped_column(ForeignKey("devices.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(Text)          # Argon2 ของรหัสจริง
    lookup: Mapped[str] = mapped_column(String(64), index=True)  # sha256(รหัส) ไว้ค้นหา O(1)
    label: Mapped[Optional[str]] = mapped_column(String(32))     # "code" | "token"
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    device: Mapped["Device"] = relationship(back_populates="tokens")


class DeviceState(Base):
    """state ล่าสุดจาก Lua (denormalized ให้แดชบอร์ดโชว์เร็ว)"""

    __tablename__ = "device_state"

    device_id: Mapped[int] = mapped_column(
        ForeignKey("devices.id", ondelete="CASCADE"), primary_key=True
    )
    avatar: Mapped[Optional[str]] = mapped_column(String(128))
    character: Mapped[Optional[str]] = mapped_column(String(128))
    map: Mapped[Optional[str]] = mapped_column(String(128))
    place_id: Mapped[Optional[int]] = mapped_column(BigInteger)
    job_id: Mapped[Optional[str]] = mapped_column(String(128))
    lua_state: Mapped[Optional[str]] = mapped_column(String(32))
    lua_age_sec: Mapped[Optional[int]] = mapped_column(Integer)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)

    device: Mapped["Device"] = relationship(back_populates="state")


class Event(Base):
    __tablename__ = "events"

    id: Mapped[int] = mapped_column(PK, primary_key=True)
    device_id: Mapped[int] = mapped_column(ForeignKey("devices.id", ondelete="CASCADE"), index=True)
    type: Mapped[str] = mapped_column(String(32))
    detail: Mapped[Optional[dict]] = mapped_column(JSONType)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)

    __table_args__ = (Index("idx_events_device_ts", "device_id", "ts"),)
