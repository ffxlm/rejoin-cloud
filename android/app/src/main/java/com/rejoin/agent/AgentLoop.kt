package com.rejoin.agent

import android.content.Context
import android.provider.Settings
import kotlinx.coroutines.currentCoroutineContext
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import org.json.JSONObject

/**
 * AgentLoop — orchestrator (พอร์ตจาก skeleton/agent/agent.py)
 *
 * loop:
 *   1) อ่าน lua_state.json + เช็คเกมรัน
 *   2) ป้อน watchdog → ได้ action
 *   3) ทำ action (REJOIN / LAUNCH / ALERT)
 *   4) ส่ง heartbeat + event ไปเว็บ
 *   5) รับคำสั่ง arm/disarm/rejoin_now จาก response
 */
class AgentLoop(
    private val context: Context,
    private val prefs: Prefs,
) {
    private val root = RootShell()
    private val api = Api(prefs)
    private val luaInstaller = LuaInstaller(context, api, root)
    private val watchdog = Watchdog(
        Config(
            silenceSec = prefs.silenceSec,
            rejoinTimeoutSec = prefs.timeoutSec,
        )
    )
    private val sessionStart = System.currentTimeMillis() / 1000

    suspend fun run() {
        // ---- 1) ลงทะเบียน ----
        AgentState.setStatus("กำลังลงทะเบียน…")
        val reg = api.register(androidId())
        if (reg != null) {
            api.token = reg.deviceToken
            prefs.deviceToken = reg.deviceToken
            prefs.intervalSec = reg.intervalSec
            AgentState.log("ลงทะเบียนสำเร็จ device=${reg.deviceId}")
        } else if (!prefs.deviceToken.isNullOrEmpty()) {
            api.token = prefs.deviceToken
            AgentState.log("ใช้ token เดิม (ลงทะเบียนชั่วคราวไม่สำเร็จ)")
        } else {
            AgentState.setStatus("ลงทะเบียนไม่สำเร็จ — ตรวจรหัสเครื่อง/เซิร์ฟเวอร์")
            AgentState.log("ลงทะเบียนล้มเหลว: ${prefs.serverUrl}")
            return
        }

        // ---- 2) ติดตั้ง Lua ลง Autoexecute ----
        AgentState.setStatus("กำลังติดตั้ง Lua…")
        if (luaInstaller.install()) {
            AgentState.log("ติดตั้ง Lua → Delta/Autoexecute สำเร็จ")
        } else {
            AgentState.log("ติดตั้ง Lua ไม่สำเร็จ (จะลองใหม่ก่อนรีเกม)")
        }

        val intervalMs = prefs.intervalSec.coerceAtLeast(3) * 1000L
        AgentState.log("เริ่มเฝ้า: interval=${intervalMs / 1000}s silence=${prefs.silenceSec}s timeout=${prefs.timeoutSec}s")

        // ---- 3) loop หลัก ----
        while (currentCoroutineContext().isActive) {
            val state = root.readLuaState()
            val gameRunning = root.gameRunning()
            val now = nowSec()
            val age = state?.let { (now - it.ts).toInt() }

            val obs = Observation(
                online = true,
                gameRunning = gameRunning,
                luaAgeSec = age,
                luaState = state?.state,
            )

            for (action in watchdog.observe(now, obs)) {
                doAction(action)
            }

            val cmd = api.heartbeat(watchdog, obs, sessionStart, state)
            handleCommand(cmd)

            AgentState.setStatus(
                "${watchdog.phase.value} | game=${if (gameRunning) "on" else "off"} | " +
                    "lua_age=${age?.toString() ?: "-"}s | rejoin=${watchdog.rejoinCount}" +
                    (if (watchdog.armed) " | ARMED" else "")
            )
            delay(intervalMs)
        }
    }

    private suspend fun doAction(action: Action) {
        when (action) {
            Action.REJOIN, Action.LAUNCH -> {
                AgentState.log(">>> ACTION ${action.name}: รีเกม")
                root.forceStop()
                delay(2000)
                luaInstaller.install() // กัน Lua หาย
                root.launch(prefs.placeId)
                api.sendEvent(
                    "rejoin",
                    JSONObject().put("action", action.name).put("count", watchdog.rejoinCount),
                )
            }
            Action.ALERT -> {
                AgentState.log("!!! ALERT: กู้ไม่ได้ ต้องให้คนดู")
                api.sendEvent("alert", JSONObject().put("attempts", watchdog.attempts))
            }
            Action.NONE -> {}
        }
    }

    private suspend fun handleCommand(cmd: String?) {
        when (cmd) {
            "arm" -> {
                watchdog.arm(nowSec())
                AgentState.log("armed by web")
            }
            "disarm" -> {
                watchdog.disarm()
                AgentState.log("disarmed by web")
            }
            "rejoin_now" -> {
                AgentState.log("rejoin_now by web")
                root.forceStop()
                delay(2000)
                luaInstaller.install()
                root.launch(prefs.placeId)
                api.sendEvent("rejoin", JSONObject().put("action", "manual"))
            }
        }
    }

    private fun androidId(): String? =
        Settings.Secure.getString(context.contentResolver, Settings.Secure.ANDROID_ID)

    private fun nowSec(): Int = (System.currentTimeMillis() / 1000).toInt()
}
