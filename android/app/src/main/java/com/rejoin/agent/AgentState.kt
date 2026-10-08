package com.rejoin.agent

import kotlinx.coroutines.flow.MutableStateFlow

/**
 * AgentState — สะพานส่งสถานะ/log จาก service → UI (ไม่ต้องใช้ broadcast)
 */
object AgentState {
    val status = MutableStateFlow("ยังไม่ทำงาน")
    val logs = MutableStateFlow<List<String>>(emptyList())

    private const val MAX_LOGS = 200

    fun setStatus(s: String) {
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
