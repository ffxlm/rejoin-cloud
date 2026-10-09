package com.rejoin.agent

import kotlinx.coroutines.flow.MutableStateFlow

/** ระดับความสำคัญของสถานะ → ใช้เลือกสี "จุดบอกสถานะ" บน UI */
enum class StatusLevel { IDLE, INFO, ACTIVE, WARN, ERROR }

/**
 * สถานะที่โชว์บนการ์ด "สถานะ" — ข้อความภาษาคน + ระดับสี + กำลังทำงานอยู่ไหม
 * (รายละเอียดเทคนิคอย่าง phase/game/lua_age ให้ไปอยู่ใน log แทน)
 */
data class AgentStatus(
    val text: String,
    val level: StatusLevel = StatusLevel.IDLE,
    val running: Boolean = false,
)

/**
 * แปลง phase ของ watchdog → สถานะภาษาคนสำหรับโชว์บน UI
 */
fun phaseStatus(phase: Phase): AgentStatus = when (phase) {
    Phase.OFFLINE -> AgentStatus("ออฟไลน์", StatusLevel.ERROR, running = true)
    Phase.CONNECTED -> AgentStatus("เชื่อมต่อแล้ว", StatusLevel.INFO, running = true)
    Phase.GAME_RUNNING -> AgentStatus("เกมรันอยู่", StatusLevel.INFO, running = true)
    Phase.LUA_ACTIVE -> AgentStatus("ทำงานอยู่", StatusLevel.ACTIVE, running = true)
    Phase.ARMED -> AgentStatus("กำลังเฝ้าเกม", StatusLevel.ACTIVE, running = true)
    Phase.REJOINING -> AgentStatus("กำลังรีเกม…", StatusLevel.WARN, running = true)
    Phase.ALERT -> AgentStatus("ต้องตรวจสอบ", StatusLevel.ERROR, running = true)
}

/**
 * AgentState — สะพานส่งสถานะ/log จาก service → UI (ไม่ต้องใช้ broadcast)
 */
object AgentState {
    val status = MutableStateFlow(AgentStatus("ยังไม่ทำงาน"))
    val logs = MutableStateFlow<List<String>>(emptyList())

    private const val MAX_LOGS = 200

    fun setStatus(text: String, level: StatusLevel = StatusLevel.IDLE, running: Boolean = false) {
        status.value = AgentStatus(text, level, running)
    }

    fun setStatus(s: AgentStatus) {
        status.value = s
    }

    fun log(line: String) {
        val ts = java.text.SimpleDateFormat("HH:mm:ss", java.util.Locale.US).format(java.util.Date())
        logs.value = (logs.value + "[$ts] $line").takeLast(MAX_LOGS)
    }

    fun reset() {
        logs.value = emptyList()
    }
}
