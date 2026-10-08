package com.rejoin.agent

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * WatchdogTest — พอร์ตจาก skeleton/tests/test_watchdog.py
 * ยืนยันว่า watchdog ฝั่ง Kotlin ให้ผลเหมือนฝั่ง Python
 */
class WatchdogTest {

    private fun obs(game: Boolean = true, age: Int? = 0, online: Boolean = true, state: String? = null) =
        Observation(online = online, gameRunning = game, luaAgeSec = age, luaState = state)

    @Test fun offline() {
        val w = Watchdog()
        w.observe(1000, obs(online = false))
        assertEquals(Phase.OFFLINE, w.phase)
    }

    @Test fun connectedNoGame() {
        val w = Watchdog()
        w.observe(1000, obs(game = false, age = null))
        assertEquals(Phase.CONNECTED, w.phase)
    }

    @Test fun gameRunning() {
        val w = Watchdog()
        w.observe(1000, obs(game = true, age = null))
        assertEquals(Phase.GAME_RUNNING, w.phase)
    }

    @Test fun luaActiveWhenNotArmed() {
        val w = Watchdog()
        w.observe(1000, obs(game = true, age = 5))
        assertEquals(Phase.LUA_ACTIVE, w.phase)
    }

    @Test fun armedWhenAlive() {
        val w = Watchdog()
        w.arm(1000)
        val acts = w.observe(1000, obs(game = true, age = 5))
        assertEquals(Phase.ARMED, w.phase)
        assertEquals(emptyList<Action>(), acts)
    }

    private fun armedWatchdog() = Watchdog(
        Config(silenceSec = 60, rejoinTimeoutSec = 90, backoffSec = listOf(30, 60, 120), maxAttempts = 3)
    ).also { it.arm(0) }

    @Test fun silenceTriggersRejoin() {
        val w = armedWatchdog()
        val acts = w.observe(100, obs(game = true, age = 70))
        assertEquals(listOf(Action.REJOIN), acts)
        assertEquals(Phase.REJOINING, w.phase)
        assertEquals(1, w.rejoinCount)
    }

    @Test fun noActionWhileWaiting() {
        val w = armedWatchdog()
        w.observe(100, obs(game = true, age = 70))
        val acts = w.observe(150, obs(game = true, age = 120))
        assertEquals(emptyList<Action>(), acts)
        assertEquals(Phase.REJOINING, w.phase)
    }

    @Test fun recoveryResets() {
        val w = armedWatchdog()
        w.observe(100, obs(game = true, age = 70))
        val acts = w.observe(120, obs(game = true, age = 3))
        assertEquals(emptyList<Action>(), acts)
        assertEquals(Phase.ARMED, w.phase)
        assertEquals(0, w.attempts)
    }

    @Test fun timeoutThenBackoff() {
        val w = armedWatchdog()
        w.observe(100, obs(game = true, age = 70))
        val acts = w.observe(200, obs(game = true, age = 170))
        assertEquals(emptyList<Action>(), acts)
        assertEquals(1, w.attempts)
        assertEquals(230, w.nextAllowedAt)
    }

    @Test fun backoffThenSecondRejoin() {
        val w = armedWatchdog()
        w.observe(100, obs(game = true, age = 70))
        w.observe(200, obs(game = true, age = 170))
        val acts = w.observe(231, obs(game = true, age = 200))
        assertEquals(listOf(Action.REJOIN), acts)
        assertEquals(2, w.rejoinCount)
    }

    @Test fun alertAfterMaxAttempts() {
        val w = armedWatchdog()
        var t = 100
        w.observe(t, obs(game = true, age = 70)); t += 100
        w.observe(t, obs(game = true, age = 170)); t += 31
        w.observe(t, obs(game = true, age = 200)); t += 100
        w.observe(t, obs(game = true, age = 300)); t += 61
        w.observe(t, obs(game = true, age = 360)); t += 100
        val acts = w.observe(t, obs(game = true, age = 460))
        assertEquals(listOf(Action.ALERT), acts)
        assertEquals(Phase.ALERT, w.phase)
    }

    @Test fun launchWhenGameDown() {
        val w = armedWatchdog()
        val acts = w.observe(100, obs(game = false, age = null))
        assertEquals(listOf(Action.LAUNCH), acts)
    }

    @Test fun disarmStopsWatching() {
        val w = armedWatchdog()
        w.disarm()
        val acts = w.observe(100, obs(game = true, age = 70))
        assertEquals(emptyList<Action>(), acts)
        assertEquals(Phase.GAME_RUNNING, w.phase)
    }

    // ---- เน็ตช้า/เกมโหลดนาน ----
    @Test fun longLoadDoesNotAlertEarly() {
        val w = Watchdog(Config(silenceSec = 60, rejoinTimeoutSec = 300)).also { it.arm(0) }
        assertEquals(listOf(Action.REJOIN), w.observe(100, obs(game = true, age = 70)))
        val acts = w.observe(250, obs(game = true, age = 220))
        assertEquals(emptyList<Action>(), acts)
        assertEquals(Phase.REJOINING, w.phase)
        assertEquals(0, w.attempts)
    }

    @Test fun loadingStateIsAliveNoRejoin() {
        val w = Watchdog(Config(silenceSec = 60, rejoinTimeoutSec = 300)).also { it.arm(0) }
        w.observe(100, obs(game = true, age = 70))
        val acts = w.observe(200, obs(game = true, age = 5, state = "loading"))
        assertEquals(emptyList<Action>(), acts)
        assertEquals(Phase.ARMED, w.phase)
        assertEquals(0, w.attempts)
    }

    @Test fun recoveryAfterSlowLoad() {
        val w = Watchdog(Config(silenceSec = 60, rejoinTimeoutSec = 300)).also { it.arm(0) }
        w.observe(100, obs(game = true, age = 70))
        val acts = w.observe(280, obs(game = true, age = 4, state = "in_game"))
        assertEquals(emptyList<Action>(), acts)
        assertEquals(Phase.ARMED, w.phase)
        assertEquals(1, w.rejoinCount)
        assertEquals(0, w.attempts)
    }

    @Test fun loadingProperty() {
        assertTrue(obs(age = 1, state = "loading").loading)
        assertTrue(obs(age = 1, state = "menu").loading)
        assertFalse(obs(age = 1, state = "in_game").loading)
        assertFalse(obs(age = 1, state = null).loading)
    }
}
