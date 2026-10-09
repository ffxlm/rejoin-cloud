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
    /** ผลการติดตั้ง + เหตุผล (ไว้โชว์ใน log ให้รู้ว่าล้มตรงไหน) */
    data class InstallResult(val ok: Boolean, val detail: String)

    fun install(): InstallResult {
        val bytes = api.downloadLua()
            ?: return InstallResult(false, "ดาวน์โหลด Lua จากเว็บไม่สำเร็จ (เช็ค server/เน็ต)")
        if (bytes.isEmpty()) return InstallResult(false, "ไฟล์ Lua ที่ดาวน์โหลดมาว่างเปล่า")

        val tmp = File(context.cacheDir, "rejoin_agent.lua")
        return try {
            tmp.writeBytes(bytes)
            // ให้ root อ่านได้ (root อ่านได้ทุกอย่างอยู่แล้ว แต่กันเหนียว)
            tmp.setReadable(true, false)
            val r = root.pushLua(tmp.absolutePath)
            if (r.ok) {
                InstallResult(true, "เขียนแล้ว ${bytes.size} ไบต์")
            } else {
                InstallResult(
                    false,
                    "ติดตั้งไม่สำเร็จ (exit=${r.code}): ${r.out.trim().take(180)}",
                )
            }
        } catch (e: Exception) {
            InstallResult(false, "เขียนไฟล์ชั่วคราวไม่สำเร็จ: ${e.message}")
        }
    }
}
