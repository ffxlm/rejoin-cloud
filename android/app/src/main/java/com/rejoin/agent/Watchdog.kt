package com.rejoin.agent

/**
 * Watchdog — dead-man's switch (พอร์ตจาก skeleton/agent/watchdog.py)
 *
 * เป็น pure logic: ไม่มี I/O, ไม่เรียกเวลาจริง → รับ `now` เข้ามา (เทสต์ได้)
 * เฝ้า "ความเงียบ" ของ Lua ไม่ใช่รอให้ Lua บอกว่าตาย
 *
 * สถานะ: OFFLINE → CONNECTED → GAME_RUNNING → LUA_ACTIVE → ARMED
 *        ARMED + เงียบ → REJOINING → (กลับ ARMED / เกินกำหนด → ALERT)
 */
enum class Phase(val value: String) {
    OFFLINE("offline"),
    CONNECTED("connected"),
    GAME_RUNNING("game_running"),
    LUA_ACTIVE("lua_active"),
    ARMED("armed"),
    REJOINING("rejoining"),
    ALERT("alert"),
}

enum class Action {
    NONE,
    REJOIN, // force-stop + เปิดเกมใหม่ + ยัด Lua
    LAUNCH, // เกมไม่ได้รัน → เปิดเกม
    ALERT,  // กู้ไม่ได้ ต้องให้คนดู
}

data class Observation(
    val online: Boolean = false,
    val gameRunning: Boolean = false,
    val luaAgeSec: Int? = null,   // null = ไม่มี state จาก Lua
    val luaState: String? = null, // "in_game" | "loading" | "menu" | "unknown" | null
) {
    /** เกมกำลังโหลด/เข้าแมพ — อย่ารีเกมทับ (Lua ยังสดอยู่ แต่ยังไม่ in_game) */
    val loading: Boolean
        get() = luaState == "loading" || luaState == "joining" || luaState == "menu"
}

data class Config(
    val silenceSec: Int = 60,          // เงียบนานเท่านี้ = ตัดสินว่าตาย
    val rejoinTimeoutSec: Int = 300,   // รอกู้กี่วิก่อนถือว่าล้มเหลว (กันเน็ตช้า/เกมโหลดนาน)
    val loadingGraceSec: Int = 120,    // Lua บอก loading/menu → ให้เวลาก่อนตัดสินว่าตาย (กันรีเกมทับตอนโหลด)
    val backoffSec: List<Int> = listOf(30, 60, 120),
    val maxAttempts: Int = 3,
)

class Watchdog(val cfg: Config = Config()) {

    var phase: Phase = Phase.OFFLINE
        private set
    var armed: Boolean = false
        private set
    var attempts: Int = 0
        private set
    var rejoinStartedAt: Int? = null
        private set
    var nextAllowedAt: Int = 0
        private set
    var lastRejoinAt: Int? = null
        private set
    var rejoinCount: Int = 0
        private set
    /** เวลา (วิ) ที่เริ่มเข้าเงื่อนไข "loading แต่ไฟล์เริ่มเก่า" — ใช้ให้ grace ก่อนตัดสินว่าตาย */
    var loadingSince: Int? = null
        private set

    fun arm(now: Int) {
        armed = true
        attempts = 0
        rejoinStartedAt = null
        nextAllowedAt = 0
        loadingSince = null
    }

    fun disarm() {
        armed = false
        rejoinStartedAt = null
        attempts = 0
        loadingSince = null
    }

    /** รับ observation แล้วคืน action ที่ต้องทำ (0 หรือ 1 อย่าง) */
    fun observe(now: Int, obs: Observation): List<Action> {
        val base = basePhase(obs)

        if (!armed) {
            phase = base
            loadingSince = null
            return emptyList()
        }

        // armed: เฝ้าความเงียบ
        val alive = obs.online && obs.luaAgeSec != null && obs.luaAgeSec <= cfg.silenceSec
        if (alive) {
            phase = Phase.ARMED
            attempts = 0
            rejoinStartedAt = null
            nextAllowedAt = 0
            loadingSince = null
            return emptyList()
        }

        // เกมกำลังโหลด (Lua บอก loading/menu) แต่ไฟล์เริ่มเก่า —
        // ให้ grace ก่อนตัดสินว่า "ตาย" เพื่อไม่รีเกมทับตอนโหลด (เน็ตช้า/โหลดนาน)
        if (obs.loading) {
            val since = loadingSince ?: now.also { loadingSince = it }
            if (now - since < cfg.loadingGraceSec) {
                phase = Phase.REJOINING
                return emptyList() // ยังโหลดอยู่ — รอ
            }
            loadingSince = null // grace หมด → ปล่อยผ่านไปกู้ตามปกติ
        } else {
            loadingSince = null
        }

        // กำลังรอผลการกู้?
        val started = rejoinStartedAt
        if (started != null) {
            if (now - started < cfg.rejoinTimeoutSec) {
                phase = Phase.REJOINING
                return emptyList() // ยังรออยู่
            }
            // หมดเวลา = ครั้งนี้ล้มเหลว
            attempts += 1
            rejoinStartedAt = null
            if (attempts >= cfg.maxAttempts) {
                phase = Phase.ALERT
                return listOf(Action.ALERT)
            }
            val delay = cfg.backoffSec[minOf(attempts - 1, cfg.backoffSec.size - 1)]
            nextAllowedAt = now + delay
            phase = Phase.REJOINING
            return emptyList()
        }

        // อยู่ในช่วง backoff?
        if (now < nextAllowedAt) {
            phase = Phase.REJOINING
            return emptyList()
        }

        // ลงมือกู้
        rejoinStartedAt = now
        lastRejoinAt = now
        rejoinCount += 1
        phase = Phase.REJOINING
        return listOf(if (obs.gameRunning) Action.REJOIN else Action.LAUNCH)
    }

    private fun basePhase(obs: Observation): Phase {
        if (!obs.online) return Phase.OFFLINE
        val alive = obs.luaAgeSec != null && obs.luaAgeSec <= cfg.silenceSec
        if (alive) return if (armed) Phase.ARMED else Phase.LUA_ACTIVE
        if (obs.gameRunning) return Phase.GAME_RUNNING
        return Phase.CONNECTED
    }
}
