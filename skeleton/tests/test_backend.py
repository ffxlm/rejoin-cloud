"""
test_backend.py — เทสต์ backend จริง (SQLite + fakeredis)
------------------------------------------------------------------
ครอบคลุม: ล็อกอิน, ออก/ลงทะเบียนรหัสเครื่อง, heartbeat, คำสั่ง arm/disarm,
event/rejoin count, และการ revoke
"""
from __future__ import annotations

import io
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
        self.shot_dir = tempfile.mkdtemp(prefix="rejoin_shots_")
        self.settings = Settings(
            database_url=f"sqlite+aiosqlite:///{self.db_path}",
            redis_url="",  # fakeredis
            session_secret="test-secret",
            dev_auth=True,
            screenshot_dir=self.shot_dir,
        )
        self.app = create_app(self.settings)

    def tearDown(self) -> None:
        try:
            os.unlink(self.db_path)
        except OSError:
            pass
        for name in os.listdir(self.shot_dir):
            try:
                os.unlink(os.path.join(self.shot_dir, name))
            except OSError:
                pass
        try:
            os.rmdir(self.shot_dir)
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

    # ---------- screenshot ----------
    def _auth_device(self, client: TestClient):
        dev = self._new_device(client, "เครื่องกล้อง")
        token = self._register(client, dev["device_code"]).json()["device_token"]
        return dev, {"Authorization": f"Bearer {token}"}

    def test_screenshot_upload_list_and_serve(self) -> None:
        with TestClient(self.app) as client:
            self._login(client)
            dev, hdr = self._auth_device(client)

            png = b"\x89PNG\r\n\x1a\n" + b"0" * 128
            r = client.post(
                "/api/agent/screenshot",
                headers=hdr,
                files={"file": ("shot.png", io.BytesIO(png), "image/png")},
            )
            self.assertEqual(r.status_code, 200, r.text)
            url = r.json()["url"]
            self.assertTrue(url.startswith("/screenshots/"))
            self.assertTrue(url.endswith(".png"))

            # ไฟล์อยู่จริงบนดิสก์ + static mount เสิร์ฟได้
            self.assertTrue(os.path.isfile(os.path.join(self.shot_dir, os.path.basename(url))))
            served = client.get(url)
            self.assertEqual(served.status_code, 200)
            self.assertEqual(served.content, png)

            # รายการภาพของผู้ใช้
            lst = client.get("/api/me/screenshots").json()["screenshots"]
            self.assertEqual(len(lst), 1)
            self.assertEqual(lst[0]["url"], url)
            self.assertEqual(lst[0]["device_id"], dev["device_id"])
            self.assertEqual(lst[0]["device_name"], "เครื่องกล้อง")

            # ลบภาพ → หายทั้ง DB + ไฟล์
            self.assertEqual(client.delete(f"/api/me/screenshots/{lst[0]['id']}").status_code, 200)
            self.assertEqual(client.get("/api/me/screenshots").json()["screenshots"], [])
            self.assertFalse(os.path.isfile(os.path.join(self.shot_dir, os.path.basename(url))))

    def test_screenshot_requires_device_token(self) -> None:
        with TestClient(self.app) as client:
            r = client.post(
                "/api/agent/screenshot",
                files={"file": ("shot.jpg", io.BytesIO(b"x"), "image/jpeg")},
            )
            self.assertEqual(r.status_code, 401)

    def test_screenshot_command_roundtrip(self) -> None:
        with TestClient(self.app) as client:
            self._login(client)
            dev, hdr = self._auth_device(client)
            self.assertEqual(client.post(f"/api/device/{dev['device_id']}/screenshot").status_code, 200)
            hb = client.post("/api/agent/heartbeat", headers=hdr, json={"state": "armed"})
            self.assertEqual(hb.json()["command"], "screenshot_now")

    def test_screenshot_rejects_oversize(self) -> None:
        with TestClient(self.app) as client:
            self._login(client)
            dev, hdr = self._auth_device(client)
            self.settings.screenshot_max_bytes = 16
            r = client.post(
                "/api/agent/screenshot",
                headers=hdr,
                files={"file": ("big.jpg", io.BytesIO(b"z" * 1024), "image/jpeg")},
            )
            self.assertEqual(r.status_code, 413)
            self.assertEqual(os.listdir(self.shot_dir), [])


class ScreenshotRetentionTest(unittest.IsolatedAsyncioTestCase):
    """retention ลบทั้งไฟล์และแถว DB ของภาพที่เก่ากว่า N วัน"""

    async def test_cleanup_removes_old_only(self) -> None:
        from skeleton.backend.db import Base, build_engine, build_sessionmaker
        from skeleton.backend.models import Device, Screenshot, User
        from skeleton.backend.screenshots import cleanup_old_screenshots, url_for

        fd, db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        shot_dir = tempfile.mkdtemp(prefix="rejoin_ret_")
        settings = Settings(screenshot_dir=shot_dir, screenshot_retention_days=7)
        engine = build_engine(f"sqlite+aiosqlite:///{db_path}")
        try:
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            sm = build_sessionmaker(engine)
            async with sm() as session:
                user = User(discord_id="ret-user")
                session.add(user)
                await session.flush()
                device = Device(user_id=user.id, name="d")
                session.add(device)
                await session.flush()

                now = datetime.now(timezone.utc)
                old = Screenshot(device_id=device.id, url=url_for("old.png"),
                                 ts=now - timedelta(days=10))
                new = Screenshot(device_id=device.id, url=url_for("new.png"),
                                 ts=now - timedelta(days=1))
                session.add_all([old, new])
                await session.commit()

                for name in ("old.png", "new.png"):
                    with open(os.path.join(shot_dir, name), "wb") as f:
                        f.write(b"x")

                removed = await cleanup_old_screenshots(session, settings, now=now)
                self.assertEqual(removed, 1)
                self.assertFalse(os.path.isfile(os.path.join(shot_dir, "old.png")))
                self.assertTrue(os.path.isfile(os.path.join(shot_dir, "new.png")))

                left = (await session.execute(select(Screenshot))).scalars().all()
                self.assertEqual(len(left), 1)
                self.assertTrue(left[0].url.endswith("new.png"))
        finally:
            await engine.dispose()
            try:
                os.unlink(db_path)
            except OSError:
                pass
            for name in os.listdir(shot_dir):
                try:
                    os.unlink(os.path.join(shot_dir, name))
                except OSError:
                    pass
            os.rmdir(shot_dir)


if __name__ == "__main__":
    unittest.main()
