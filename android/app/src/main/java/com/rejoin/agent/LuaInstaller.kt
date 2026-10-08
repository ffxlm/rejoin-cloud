package com.rejoin.agent

import android.content.Context
import java.io.File

/**
 * LuaInstaller — ดึง Lua จากเว็บ แล้วเขียนลง Delta/Autoexecute (atomic + backup)
 *
 * Lua ไม่ฝังใน APK → แก้ที่เว็บได้ทันที (PLAN.md §7.2)
 */
class LuaInstaller(
    private val context: Context,
    private val api: Api,
    private val root: RootShell,
) {
    fun install(): Boolean {
        val bytes = api.downloadLua() ?: return false
        if (bytes.isEmpty()) return false
        val tmp = File(context.cacheDir, "rejoin_agent.lua")
        tmp.writeBytes(bytes)
        // ให้ root อ่านได้ (root อ่านได้ทุกอย่างอยู่แล้ว แต่กันเหนียว)
        tmp.setReadable(true, false)
        return root.pushLua(tmp.absolutePath)
    }
}
