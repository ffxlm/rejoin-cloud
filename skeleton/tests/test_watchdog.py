"""
test_watchdog.py — unit tests สำหรับ watchdog (pure logic, ไม่ต้องมีเครื่อง)
รัน:  python3 -m unittest discover -s skeleton/tests -v
หรือ: .venv/bin/python -m unittest skeleton.tests.test_watchdog -v
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from skeleton.agent.watchdog import Action, Config, Observation, Phase, Watchdog


def obs(game=True, age=0, online=True):
    return Observation(online=online, game_running=game, lua_age_sec=age)


class TestBasePhases(unittest.TestCase):
    def test_offline(self):
        w = Watchdog()
        w.observe(1000, obs(online=False))
        self.assertEqual(w.phase, Phase.OFFLINE)

    def test_connected_no_game(self):
        w = Watchdog()
        w.observe(1000, obs(game=False, age=None))
        self.assertEqual(w.phase, Phase.CONNECTED)

    def test_game_running(self):
        w = Watchdog()
        w.observe(1000, obs(game=True, age=None))
        self.assertEqual(w.phase, Phase.GAME_RUNNING)

    def test_lua_active_when_not_armed(self):
        w = Watchdog()
        w.observe(1000, obs(game=True, age=5))
        self.assertEqual(w.phase, Phase.LUA_ACTIVE)


class TestArmedAlive(unittest.TestCase):
    def test_armed_when_alive(self):
        w = Watchdog()
        w.arm(1000)
        acts = w.observe(1000, obs(game=True, age=5))
        self.assertEqual(w.phase, Phase.ARMED)
        self.assertEqual(acts, [])


class TestRejoin(unittest.TestCase):
    def setUp(self):
        self.w = Watchdog(Config(silence_sec=60, rejoin_timeout_sec=90,
                                 backoff_sec=(30, 60, 120), max_attempts=3))
        self.w.arm(0)

    def test_silence_triggers_rejoin(self):
        acts = self.w.observe(100, obs(game=True, age=70))  # age > 60
        self.assertEqual(acts, [Action.REJOIN])
        self.assertEqual(self.w.phase, Phase.REJOINING)
        self.assertEqual(self.w.rejoin_count, 1)

    def test_no_action_while_waiting(self):
        self.w.observe(100, obs(game=True, age=70))
        acts = self.w.observe(150, obs(game=True, age=120))  # ยังไม่ครบ 90 วิ
        self.assertEqual(acts, [])
        self.assertEqual(self.w.phase, Phase.REJOINING)

    def test_recovery_resets(self):
        self.w.observe(100, obs(game=True, age=70))
        acts = self.w.observe(120, obs(game=True, age=3))  # กลับมา
        self.assertEqual(acts, [])
        self.assertEqual(self.w.phase, Phase.ARMED)
        self.assertEqual(self.w.attempts, 0)

    def test_timeout_then_backoff(self):
        self.w.observe(100, obs(game=True, age=70))            # rejoin #1
        acts = self.w.observe(200, obs(game=True, age=170))    # เกิน 90 วิ → ล้มเหลว
        self.assertEqual(acts, [])                             # ยังไม่ถึงเวลา backoff
        self.assertEqual(self.w.attempts, 1)
        self.assertEqual(self.w.next_allowed_at, 200 + 30)

    def test_backoff_then_second_rejoin(self):
        self.w.observe(100, obs(game=True, age=70))
        self.w.observe(200, obs(game=True, age=170))   # fail #1, backoff 30
        acts = self.w.observe(231, obs(game=True, age=200))  # ผ่าน backoff → rejoin #2
        self.assertEqual(acts, [Action.REJOIN])
        self.assertEqual(self.w.rejoin_count, 2)

    def test_alert_after_max_attempts(self):
        t = 100
        # attempt 1
        self.w.observe(t, obs(game=True, age=70)); t += 100  # timeout
        self.w.observe(t, obs(game=True, age=170))            # fail#1 -> backoff 30
        t += 31
        self.w.observe(t, obs(game=True, age=200))            # rejoin #2
        t += 100
        self.w.observe(t, obs(game=True, age=300))            # fail#2 -> backoff 60
        t += 61
        self.w.observe(t, obs(game=True, age=360))            # rejoin #3
        t += 100
        acts = self.w.observe(t, obs(game=True, age=460))     # fail#3 -> alert
        self.assertEqual(acts, [Action.ALERT])
        self.assertEqual(self.w.phase, Phase.ALERT)

    def test_launch_when_game_down(self):
        acts = self.w.observe(100, obs(game=False, age=None))
        self.assertEqual(acts, [Action.LAUNCH])

    def test_disarm_stops_watching(self):
        self.w.disarm()
        acts = self.w.observe(100, obs(game=True, age=70))
        self.assertEqual(acts, [])
        self.assertEqual(self.w.phase, Phase.GAME_RUNNING)


if __name__ == "__main__":
    unittest.main(verbosity=2)
