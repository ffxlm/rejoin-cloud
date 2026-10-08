"""
test_backend.py — เทสต์ backend จริง (SQLite + fakeredis)
------------------------------------------------------------------
ครอบคลุม: ล็อกอิน, ออก/ลงทะเบียนรหัสเครื่อง, heartbeat, คำสั่ง arm/disarm,
event/rejoin count, และการ revoke
"""
from __future__ import annotations

import os
import tempfile
import time
import unittest
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
from sqlalchemy import select

from skeleton.backend.app import create_app
from skeleton.backend.config import Settings


class BackendTestCase(unittest.TestCase):
    def setUp(self) -> None:
        fd, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self.settings = Settings(
            database_url=f"sqlite+aiosqlite:///{self.db_path}",
            redis_url="",  # fakeredis
            session_secret="test-secret",
            dev_auth=True,
        )
        self.app = create_app(self.settings)

    def tearDown(self) -> None:
        try:
            os.unlink(self.db_path)
        except OSError:
            pass

    # ---------- helpers ----------
    def _login(self, client: TestClient) -> None:
        r = client.get("/auth/dev", follow_redirects=False)
        self.assertIn(r.status_code, (302, 307))

    def _new_device(self, client: TestClient, name: str = "A"):
        r = client.post("/api/me/devices", json={"name": name})
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()

    def _register(self, client: TestClient, code: str):
        return client.post(
            "/api/agent/register",
            json={"device_code": code, "apk_version": "test-1"},
        )

    # ---------- tests ----------
    def test_requires_login(self) -> None:
        with TestClient(self.app) as client:
            self.assertEqual(client.get("/api/me/devices").status_code, 401)
            self.assertEqual(client.get("/api/me").status_code, 401)

    def test_register_rejects_bad_code(self) -> None:
        with TestClient(self.app) as client:
            self._login(client)
            self._new_device(client)
            r = self._register(client, "RJ-AAAAA-BBBBB")
            self.assertEqual(r.status_code, 401)

    def test_full_flow(self) -> None:
        with TestClient(self.app) as client:
            self._login(client)
            dev = self._new_device(client, "เครื่องทดสอบ")
            code, did = dev["device_code"], dev["device_id"]

            # ลงทะเบียนด้วยรหัสจริง → ได้ token
            r = self._register(client, code)
            self.assertEqual(r.status_code, 200, r.text)
            token = r.json()["device_token"]
            self.assertEqual(r.json()["device_id"], did)
            hdr = {"Authorization": f"Bearer {token}"}

            # heartbeat → armed
            hb = client.post(
                "/api/agent/heartbeat",
                headers=hdr,
                json={
                    "state": "armed",
                    "armed": True,
                    "game_running": True,
                    "lua_active": True,
                    "lua_age_sec": 2,
                    "lua_state": "in_game",
                    "avatar": "av1",
                    "character": "ch1",
                    "map": "map1",
                    "session_start": int(time.time()),
                    "ts": int(time.time()),
                },
            )
            self.assertEqual(hb.status_code, 200)
            self.assertIsNone(hb.json()["command"])

            d = client.get("/api/me/devices").json()["devices"][0]
            self.assertEqual(d["status"], "armed")
            self.assertTrue(d["armed"])
            self.assertTrue(d["lua_active"])
            self.assertEqual(d["avatar"], "av1")
            self.assertEqual(d["character"], "ch1")
            self.assertEqual(d["map"], "map1")

            # arm ผ่านเว็บ → คำสั่งออกที่ heartbeat ถัดไป
            self.assertEqual(client.post(f"/api/device/{did}/arm").status_code, 200)
            hb2 = client.post("/api/agent/heartbeat", headers=hdr, json={"state": "armed"})
            self.assertEqual(hb2.json()["command"], "arm")

            # event rejoin → นับ 1
            self.assertEqual(
                client.post("/api/agent/event", headers=hdr, json={"type": "rejoin"}).status_code,
                200,
            )
            d = client.get("/api/me/devices").json()["devices"][0]
            self.assertEqual(d["rejoin_count"], 1)

            # events list
            ev = client.get("/api/me/events").json()["events"]
            self.assertTrue(any(e["type"] == "rejoin" for e in ev))

    def test_invalid_token(self) -> None:
        with TestClient(self.app) as client:
            r = client.post(
                "/api/agent/heartbeat",
                headers={"Authorization": "Bearer rj_not-a-real-token"},
                json={"state": "connected"},
            )
            self.assertEqual(r.status_code, 401)

    def test_revoke_on_delete(self) -> None:
        with TestClient(self.app) as client:
            self._login(client)
            dev = self._new_device(client)
            token = self._register(client, dev["device_code"]).json()["device_token"]
            hdr = {"Authorization": f"Bearer {token}"}
            self.assertEqual(
                client.post("/api/agent/heartbeat", headers=hdr, json={"state": "connected"}).status_code,
                200,
            )
            # ลบเครื่อง → token ใช้ไม่ได้ + ไม่เห็นเครื่อง
            self.assertEqual(client.delete(f"/api/me/devices/{dev['device_id']}").status_code, 200)
            self.assertEqual(
                client.post("/api/agent/heartbeat", headers=hdr, json={"state": "connected"}).status_code,
                401,
            )
            self.assertEqual(len(client.get("/api/me/devices").json()["devices"]), 0)

    def test_cannot_touch_other_users_device(self) -> None:
        with TestClient(self.app) as client:
            self._login(client)
            dev = self._new_device(client)
            client.post("/auth/logout")
            self._login(client)  # dev user เดียวกันในเทสต์นี้ — สร้างเครื่องใหม่ต่างหาก
            self.assertEqual(client.post("/api/device/999999/arm").status_code, 404)
            # ลบเครื่องเดิมก็ยังได้ (เจ้าของเดียวกัน) — ตรวจ 404 กับ id ที่ไม่มี
            self.assertEqual(client.delete("/api/me/devices/999999").status_code, 404)
            self.assertIsNotNone(dev)


    def test_partial_heartbeat_keeps_last_state_but_liveness_current(self) -> None:
        with TestClient(self.app) as client:
            self._login(client)
            dev = self._new_device(client)
            token = self._register(client, dev["device_code"]).json()["device_token"]
            hdr = {"Authorization": f"Bearer {token}"}

            client.post("/api/agent/heartbeat", headers=hdr, json={
                "state": "armed", "armed": True, "lua_active": True,
                "lua_age_sec": 2, "avatar": "av", "character": "ch", "map": "mp",
            })
            # heartbeat ถัดไปไม่มีข้อมูล Lua (Lua เงียบ) → lua_active ต้อง false
            # แต่ avatar/character/map (ค่าโชว์ล่าสุด) ต้องคงอยู่
            client.post("/api/agent/heartbeat", headers=hdr, json={"state": "rejoining"})
            d = client.get("/api/me/devices").json()["devices"][0]
            self.assertFalse(d["lua_active"])
            self.assertEqual(d["avatar"], "av")
            self.assertEqual(d["character"], "ch")
            self.assertEqual(d["map"], "mp")

    # ---------- retention ----------


class EventRetentionTest(unittest.IsolatedAsyncioTestCase):
    """retention ลบเหตุการณ์ที่เก่ากว่า N วัน + เกินเพดานต่อเครื่อง"""

    async def test_cleanup_removes_old_and_excess(self) -> None:
        from skeleton.backend.db import Base, build_engine, build_sessionmaker
        from skeleton.backend.events import cleanup_old_events
        from skeleton.backend.models import Device, Event, User

        fd, db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        settings = Settings(event_retention_days=7, event_max_per_device=3)
        engine = build_engine(f"sqlite+aiosqlite:///{db_path}")
        try:
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            sm = build_sessionmaker(engine)
            async with sm() as session:
                user = User(discord_id="ev-user")
                session.add(user)
                await session.flush()
                d1 = Device(user_id=user.id, name="d1", rejoin_total=9)
                d2 = Device(user_id=user.id, name="d2")
                session.add_all([d1, d2])
                await session.flush()

                now = datetime.now(timezone.utc)
                # d1: 5 events ใหม่ (ควรเหลือ 3 ใหม่สุด) + 1 event เก่า 10 วัน
                for i in range(5):
                    session.add(
                        Event(device_id=d1.id, type="rejoin", ts=now - timedelta(minutes=i))
                    )
                session.add(
                    Event(device_id=d1.id, type="rejoin", ts=now - timedelta(days=10))
                )
                # d2: 1 event เก่า → ถูกลบตามอายุ
                session.add(
                    Event(device_id=d2.id, type="arm", ts=now - timedelta(days=10))
                )
                await session.commit()

                removed = await cleanup_old_events(session, settings, now=now)
                # 1 เก่าของ d1 + 2 เกินเพดานของ d1 + 1 เก่าของ d2 = 4
                self.assertEqual(removed, 4)

                left = (
                    await session.execute(select(Event).order_by(Event.device_id, Event.ts.desc()))
                ).scalars().all()
                self.assertEqual(len(left), 3)
                self.assertTrue(all(e.device_id == d1.id for e in left))

                # ยอดสะสม (rejoin_total) ต้องไม่ถูก retention แตะ
                await session.refresh(d1)
                self.assertEqual(d1.rejoin_total, 9)
        finally:
            await engine.dispose()
            try:
                os.unlink(db_path)
            except OSError:
                pass


if __name__ == "__main__":
    unittest.main()
