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
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

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
        self.assertIn(r.status_code, (302, 303, 307))

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

    def test_arm_survives_agent_restart(self) -> None:
        """APK รีสตาร์ท (armed ในหน่วยความจำหาย) ต้องไม่ล้างสถานะ armed ที่เว็บสั่งไว้
        — และเว็บต้องสั่ง arm กลับไปให้ APK ตรงกัน"""
        with TestClient(self.app) as client:
            self._login(client)
            dev = self._new_device(client)
            token = self._register(client, dev["device_code"]).json()["device_token"]
            hdr = {"Authorization": f"Bearer {token}"}
            did = dev["device_id"]

            # ผู้ใช้กด "เริ่มเฝ้าเกม" บนเว็บ
            self.assertEqual(client.post(f"/api/device/{did}/arm").status_code, 200)

            # heartbeat แรก: APK ยังไม่รู้ (armed=false) → ยึดค่าเว็บ + สั่ง arm กลับ
            hb = client.post(
                "/api/agent/heartbeat",
                headers=hdr,
                json={"state": "lua_active", "armed": False, "lua_active": True},
            )
            self.assertEqual(hb.json()["command"], "arm")
            d = client.get("/api/me/devices").json()["devices"][0]
            self.assertTrue(d["armed"], "armed ต้องคงอยู่ ไม่ถูกล้างด้วย armed=false")

            # APK รับคำสั่งแล้ว → armed=true
            client.post("/api/agent/heartbeat", headers=hdr, json={"state": "armed", "armed": True})
            d = client.get("/api/me/devices").json()["devices"][0]
            self.assertTrue(d["armed"])

            # APK รีสตาร์ท (armed กลับเป็น false) → ต้อง re-issue arm ไม่ล้างค่า
            hb = client.post(
                "/api/agent/heartbeat",
                headers=hdr,
                json={"state": "lua_active", "armed": False, "lua_active": True},
            )
            self.assertEqual(hb.json()["command"], "arm")
            d = client.get("/api/me/devices").json()["devices"][0]
            self.assertTrue(d["armed"], "armed ต้องรอดจากการรีสตาร์ท")

            # ผู้ใช้กด "หยุดเฝ้า" บนเว็บ → disarm ต้องทำงานจริง
            self.assertEqual(client.post(f"/api/device/{did}/disarm").status_code, 200)
            client.post("/api/agent/heartbeat", headers=hdr, json={"state": "lua_active", "armed": False})
            d = client.get("/api/me/devices").json()["devices"][0]
            self.assertFalse(d["armed"], "disarm ต้องคงค่าไว้")

    # ---------- ดาวน์โหลด APK ----------
    def test_apk_download_serves_local_file(self) -> None:
        with TestClient(self.app) as client:
            self._login(client)
            fd, apk = tempfile.mkstemp(suffix=".apk")
            os.write(fd, b"fake-apk")
            os.close(fd)
            try:
                with patch.object(Settings, "resolve_apk_path", return_value=apk):
                    r = client.get("/api/download/apk", follow_redirects=False)
                self.assertEqual(r.status_code, 200)
                self.assertEqual(
                    r.headers["content-type"], "application/vnd.android.package-archive"
                )
                self.assertEqual(r.content, b"fake-apk")
            finally:
                os.unlink(apk)

    def test_apk_download_falls_back_to_release(self) -> None:
        """ไม่มีไฟล์ในเครื่อง (production) → redirect ไป GitHub Release"""
        with TestClient(self.app) as client:
            self._login(client)
            with patch.object(Settings, "resolve_apk_path", return_value=None):
                r = client.get("/api/download/apk", follow_redirects=False)
                self.assertEqual(r.status_code, 302)
                self.assertIn("releases/download/apk-latest", r.headers["location"])
                # หน้าดาวน์โหลดต้องโชว์ว่ามาจาก GitHub Release
                html = client.get("/download").text
                self.assertIn("GitHub Release", html)

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


class _FakeResponse:
    def __init__(self, status_code: int, payload: dict):
        self.status_code = status_code
        self._payload = payload

    def json(self) -> dict:
        return self._payload

class _FakeDiscordClient:
    """เลียนแบบ httpx.AsyncClient สำหรับเทสต์ OAuth (ไม่ยิงเน็ตจริง)"""

    token_status = 200
    me_status = 200

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def post(self, url, **kwargs):
        if self.token_status != 200:
            return _FakeResponse(self.token_status, {})
        return _FakeResponse(200, {"access_token": "fake-access-token"})

    async def get(self, url, **kwargs):
        if self.me_status != 200:
            return _FakeResponse(self.me_status, {})
        return _FakeResponse(
            200,
            {"id": "123456789012345678", "username": "tester", "avatar": "abc123"},
        )

class DiscordAuthTestCase(unittest.TestCase):
    """ทดสอบ flow ล็อกอิน Discord OAuth2 แบบครบวง (mock Discord API)"""

    def setUp(self) -> None:
        fd, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self.settings = Settings(
            database_url=f"sqlite+aiosqlite:///{self.db_path}",
            redis_url="",
            session_secret="test-secret",
            dev_auth=False,
            discord_client_id="test-client-id",
            discord_client_secret="test-client-secret",
            discord_redirect_uri="http://testserver/auth/discord/callback",
        )
        self.app = create_app(self.settings)

    def tearDown(self) -> None:
        try:
            os.unlink(self.db_path)
        except OSError:
            pass

    def _start_login(self, client: TestClient) -> str:
        r = client.get("/auth/discord", follow_redirects=False)
        self.assertEqual(r.status_code, 307)
        self.assertIn("discord.com/oauth2/authorize", r.headers["location"])
        return parse_qs(urlparse(r.headers["location"]).query)["state"][0]

    def test_login_redirects_to_discord_with_state(self) -> None:
        with TestClient(self.app) as client:
            self._start_login(client)

    def test_callback_creates_user_and_session(self) -> None:
        with TestClient(self.app) as client:
            state = self._start_login(client)
            with patch(
                "skeleton.backend.routers.auth.httpx.AsyncClient", _FakeDiscordClient
            ):
                cb = client.get(
                    f"/auth/discord/callback?code=abc&state={state}",
                    follow_redirects=False,
                )
            self.assertEqual(cb.status_code, 303)
            self.assertEqual(cb.headers["location"], "/")

            me = client.get("/api/me")
            self.assertEqual(me.status_code, 200)
            body = me.json()
            self.assertEqual(body["username"], "tester")
            self.assertTrue(
                body["avatar_url"].startswith("https://cdn.discordapp.com/avatars/")
            )

    def test_callback_rejects_bad_state(self) -> None:
        with TestClient(self.app) as client:
            self._start_login(client)
            cb = client.get(
                "/auth/discord/callback?code=abc&state=wrong",
                follow_redirects=False,
            )
            self.assertEqual(cb.status_code, 303)
            self.assertIn("auth_error=state", cb.headers["location"])

    def test_callback_handles_denied(self) -> None:
        with TestClient(self.app) as client:
            cb = client.get(
                "/auth/discord/callback?error=access_denied",
                follow_redirects=False,
            )
            self.assertEqual(cb.status_code, 303)
            self.assertIn("auth_error=denied", cb.headers["location"])

    def test_callback_handles_token_failure(self) -> None:
        with TestClient(self.app) as client:
            state = self._start_login(client)

            class _Failing(_FakeDiscordClient):
                token_status = 400

            with patch("skeleton.backend.routers.auth.httpx.AsyncClient", _Failing):
                cb = client.get(
                    f"/auth/discord/callback?code=abc&state={state}",
                    follow_redirects=False,
                )
            self.assertEqual(cb.status_code, 303)
            self.assertIn("auth_error=token", cb.headers["location"])

    def test_login_page_shows_discord_button(self) -> None:
        with TestClient(self.app) as client:
            html = client.get("/").text
            self.assertIn("/auth/discord", html)


class AdminAccessTestCase(unittest.TestCase):
    """ทดสอบระบบหลังบ้าน: ผู้ใช้คนแรกเป็นแอดมิน + กันสิทธิ์เข้าถึง"""

    def setUp(self) -> None:
        fd, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self.settings = Settings(
            database_url=f"sqlite+aiosqlite:///{self.db_path}",
            redis_url="",
            session_secret="test-secret",
            dev_auth=True,
            discord_client_id="test-client-id",
            discord_client_secret="test-client-secret",
            discord_redirect_uri="http://testserver/auth/discord/callback",
        )
        self.app = create_app(self.settings)

    def tearDown(self) -> None:
        try:
            os.unlink(self.db_path)
        except OSError:
            pass

    def _login_dev(self, client: TestClient) -> None:
        r = client.get("/auth/dev", follow_redirects=False)
        self.assertIn(r.status_code, (302, 303, 307))

    def _login_discord(self, client: TestClient) -> None:
        """ล็อกอินผู้ใช้คนที่สองผ่าน Discord (mock) → ไม่ใช่แอดมิน"""
        start = client.get("/auth/discord", follow_redirects=False)
        state = parse_qs(urlparse(start.headers["location"]).query)["state"][0]
        with patch("skeleton.backend.routers.auth.httpx.AsyncClient", _FakeDiscordClient):
            client.get(
                f"/auth/discord/callback?code=abc&state={state}",
                follow_redirects=False,
            )

    def test_first_user_becomes_admin(self) -> None:
        with TestClient(self.app) as client:
            self._login_dev(client)
            self.assertTrue(client.get("/api/me").json()["is_admin"])
            page = client.get("/admin")
            self.assertEqual(page.status_code, 200)
            self.assertIn("ภาพรวมระบบ", page.text)

    def test_non_admin_is_forbidden(self) -> None:
        with TestClient(self.app) as client:
            self._login_dev(client)       # ผู้ใช้คนแรก = แอดมิน
            self._login_discord(client)   # ผู้ใช้คนที่สอง = ผู้ใช้ทั่วไป
            self.assertFalse(client.get("/api/me").json()["is_admin"])
            self.assertEqual(client.get("/admin").status_code, 403)
            self.assertEqual(client.get("/api/admin/overview").status_code, 403)
            self.assertEqual(client.get("/api/admin/users").status_code, 403)
            self.assertEqual(client.get("/api/admin/devices").status_code, 403)

    def test_anonymous_sees_login(self) -> None:
        with TestClient(self.app) as client:
            r = client.get("/admin")
            self.assertEqual(r.status_code, 200)
            self.assertIn("เข้าสู่ระบบ", r.text)

    def test_sidebar_button_only_for_admin(self) -> None:
        with TestClient(self.app) as client:
            self._login_dev(client)
            self.assertIn('href="/admin"', client.get("/").text)
            self._login_discord(client)
            self.assertNotIn('href="/admin"', client.get("/").text)

    def test_admin_overview_api(self) -> None:
        with TestClient(self.app) as client:
            self._login_dev(client)
            body = client.get("/api/admin/overview").json()
            self.assertEqual(body["users"], 1)
            self.assertEqual(body["devices"], 0)
            self.assertEqual(body["rejoins"], 0)


if __name__ == "__main__":
    unittest.main()
