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
    private val keepAlive = KeepAlive(context, root)
    private val watchdog = Watchdog(
        Config(
            silenceSec = prefs.silenceSec,
            rejoinTimeoutSec = prefs.timeoutSec,
        )
    )
    private val sessionStart = System.currentTimeMillis() / 1000

    /** phase ล่าสุดที่เขียน log ไปแล้ว — เขียนรายละเอียดเทคนิคเฉพาะตอนเปลี่ยน (กัน log ล้น) */
    private var lastPhase: Phase? = null

    /** Lua ลง Autoexecute สำเร็จแล้วหรือยัง — ถ้ายัง ลองใหม่เรื่อยๆ */
    private var luaReady = false
    private var lastLuaTrySec = 0

    /** สถานะ root — auto-rejoin ต้องใช้ force-stop; ถ้าไม่มี ต้องแจ้งผู้ใช้ตรง ๆ */
    private var rootOk = true
    private var rootMsg = ""
    private var lastRootState: RootShell.RootState? = null

    suspend fun run() {
        // ---- 1) ลงทะเบียน ----
        AgentState.setStatus("กำลังลงทะเบียน…", StatusLevel.INFO, running = true)
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
            AgentState.setStatus("ลงทะเบียนไม่สำเร็จ", StatusLevel.ERROR)
            AgentState.log("ลงทะเบียนล้มเหลว: ${prefs.serverUrl}")
            return
        }

        // ---- 2) เช็ค root ก่อน (auto-rejoin ต้องใช้ force-stop) ----
        refreshRoot()

        // ---- 2.1) กัน ColorOS/realme แช่แข็งแอป (FastFreezer) — ตัวการที่ loop หยุดตอนเข้าเกม ----
        if (rootOk) {
            val w = root.protectFromFreezer(context.packageName)
            AgentState.log("กันแช่แข็งแอป (no_frozen): ${w.out.trim()}")
            // กัน LMK ฆ่า (RAM น้อย): daemon ตรึง oom_score_adj + เปิด service กลับถ้าตาย
            keepAlive.start()
            AgentState.log("เปิดตัวกันถูกฆ่า (keep-alive daemon)")
        }

        // ---- 3) ติดตั้ง Lua ลง Autoexecute (เฉพาะเมื่อมีรูท) ----
        if (rootOk) {
            AgentState.setStatus("กำลังติดตั้ง Lua…", StatusLevel.INFO, running = true)
            val install = luaInstaller.install()
            luaReady = install.ok
            lastLuaTrySec = nowSec()
            if (install.ok) {
                AgentState.log("ติดตั้ง Lua → Delta/Autoexecute สำเร็จ (${install.detail})")
            } else {
                AgentState.log("ติดตั้ง Lua ไม่สำเร็จ: ${install.detail}")
            }
        } else {
            lastLuaTrySec = nowSec()
        }

        // เกมยังไม่รัน → ล้าง state เก่าที่ค้างจากรอบก่อน (กันข้อมูลผี: ชื่อ/แมพของ session เก่า)
        if (rootOk && !root.gameRunning()) {
            root.run("rm -f '${RootShell.STATE_FILE}'")
            AgentState.log("ล้าง state เก่า (เกมยังไม่รัน)")
        }

        val intervalMs = prefs.intervalSec.coerceAtLeast(3) * 1000L
        AgentState.log("เริ่มเฝ้า: interval=${intervalMs / 1000}s silence=${prefs.silenceSec}s timeout=${prefs.timeoutSec}s")

        // ---- 4) loop หลัก ----
        while (currentCoroutineContext().isActive) {
            val raw = root.readLuaState()
            val gameRunning = root.gameRunning()
            val now = nowSec()
            val age = raw?.let { (now - it.ts).toInt() }
            val fresh = age != null && age <= prefs.silenceSec

            val obs = Observation(
                online = true,
                gameRunning = gameRunning,
                luaAgeSec = age,
                luaState = raw?.state,
            )

            for (action in watchdog.observe(now, obs)) {
                doAction(action)
            }

            // ส่งข้อมูลตัวละคร/แมพ/place ขึ้นเว็บ "เฉพาะตอนข้อมูลจริง"
            // (เกมรันอยู่ + Lua ยังสด) — กันค่าผีจากไฟล์ state เก่าค้างขึ้นแดชบอร์ด
            val liveState = raw?.takeIf { gameRunning && fresh }
            val cmd = api.heartbeat(watchdog, obs, sessionStart, liveState)
            handleCommand(cmd)

            // ยังไม่พร้อม → เช็ค root + ลองติดตั้งใหม่ทุก ~LUA_RETRY_SEC
            if (!luaReady && now - lastLuaTrySec >= LUA_RETRY_SEC) {
                lastLuaTrySec = now
                refreshRoot()
                if (rootOk) {
                    val retry = luaInstaller.install()
                    luaReady = retry.ok
                    AgentState.log(
                        if (retry.ok) "ติดตั้ง Lua สำเร็จ (หลังลองใหม่)"
                        else "ติดตั้ง Lua ยังไม่สำเร็จ: ${retry.detail}"
                    )
                }
                // ไม่มีรูท → ไม่ลองติดตั้ง (ไม่มีทางสำเร็จ) รอผู้ใช้อนุญาตก่อน
            }

            // การ์ดสถานะ: ไม่มีรูท → แจ้งตรง ๆ แทนสถานะ phase ปกติ (ผู้ใช้จะได้เห็นชัด ๆ)
            AgentState.setStatus(
                if (rootOk) phaseStatus(watchdog.phase)
                else AgentStatus(rootMsg, StatusLevel.ERROR, running = true)
            )

            // รายละเอียดเทคนิค (phase/game/lua_age/rejoin) ย้ายไปอยู่ใน log แทนการ์ดสถานะ
            // เขียนเฉพาะตอน phase เปลี่ยน — ไม่งั้น log จะล้นทุก interval
            if (watchdog.phase != lastPhase) {
                lastPhase = watchdog.phase
                AgentState.log(
                    "สถานะ: ${watchdog.phase.value} | game=${if (gameRunning) "on" else "off"} | " +
                        "lua_age=${age?.toString() ?: "-"}s | rejoin=${watchdog.rejoinCount}" +
                        (if (watchdog.armed) " | ARMED" else "")
                )
            }
            // ตรึง adj ตัวเองเป็นระยะ (สำรอง — daemon ตรึงทุก 2 วิอยู่แล้ว)
            if (rootOk) keepAlive.pinSelf()
            delay(intervalMs)
        }
    }

    private suspend fun doAction(action: Action) {
        when (action) {
            Action.REJOIN, Action.LAUNCH -> {
                AgentState.log(">>> ACTION ${action.name}: รีเกม")
                root.forceStop()
                delay(2000)
                reinstallLua("ก่อนรีเกม") // กัน Lua หาย
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
                reinstallLua("ก่อน rejoin_now")
                root.launch(prefs.placeId)
                api.sendEvent("rejoin", JSONObject().put("action", "manual"))
            }
        }
    }

    /** ติดตั้ง Lua ใหม่ (ก่อนรีเกม) แล้วอัปเดตสถานะ + log ถ้าล้มเหลว */
    private fun reinstallLua(whenLabel: String) {
        val r = luaInstaller.install()
        luaReady = r.ok
        if (!r.ok) AgentState.log("ติดตั้ง Lua $whenLabel ไม่สำเร็จ: ${r.detail}")
    }

    /**
     * เช็ค root แล้วอัปเดตสถานะ — ถ้าไม่มี ให้ log ตรง ๆ ว่า "เครื่องไม่ได้รูท"
     * (log เฉพาะตอนสถานะเปลี่ยน กันข้อความซ้ำทุก 60 วิ)
     */
    private fun refreshRoot() {
        val r = root.checkRoot()
        rootOk = r.state == RootShell.RootState.OK
        rootMsg = when (r.state) {
            RootShell.RootState.OK -> ""
            RootShell.RootState.NOT_ROOTED -> "เครื่องนี้ไม่ได้รูท — ใช้ auto-rejoin ไม่ได้"
            RootShell.RootState.DENIED -> "เครื่องนี้ยังไม่อนุญาต root — กด Allow ใน Magisk"
        }
        if (r.state != lastRootState) {
            lastRootState = r.state
            if (!rootOk) AgentState.log(rootMsg)
        }
        // แสดงบนการ์ดสถานะทันที (ไม่รอ loop) — ผู้ใช้จะได้เห็นว่าเครื่องไม่ได้รูท
        if (!rootOk) AgentState.setStatus(rootMsg, StatusLevel.ERROR, running = true)
    }

    private fun androidId(): String? =
        Settings.Secure.getString(context.contentResolver, Settings.Secure.ANDROID_ID)

    private fun nowSec(): Int = (System.currentTimeMillis() / 1000).toInt()

    companion object {
        /** ระยะห่างขั้นต่ำระหว่างการลองติดตั้ง Lua ซ้ำ (วินาที) — กัน log/เน็ตถี่เกิน */
        private const val LUA_RETRY_SEC = 60
    }
}
