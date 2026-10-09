package com.rejoin.agent

import org.json.JSONObject
import java.util.concurrent.TimeUnit

/**
 * RootShell — กระทำกับเครื่องผ่าน root (`su -c …`)
 * พอร์ตจาก skeleton/agent/device.py
 *
 * ต้องมี root (Magisk) — ตาม PLAN.md §13 (แนะนำใช้ root เพราะคลาวโฟนส่วนใหญ่เปิดได้)
 */
class RootShell {

    data class Result(val code: Int, val out: String) {
        val ok: Boolean get() = code == 0
    }

    fun run(command: String, timeoutMs: Long = 20_000): Result {
        return try {
            val pb = ProcessBuilder("su", "-c", command)
            pb.redirectErrorStream(true)
            val proc = pb.start()
            val out = proc.inputStream.bufferedReader().readText()
            val finished = proc.waitFor(timeoutMs, TimeUnit.MILLISECONDS)
            if (!finished) {
                proc.destroyForcibly()
                Result(-1, out)
            } else {
                Result(proc.exitValue(), out)
            }
        } catch (e: Exception) {
            Result(-1, e.message ?: "exec error")
        }
    }

    // ---------- ตรวจสอบ ----------
    fun gameRunning(): Boolean {
        val r = run("pidof $GAME_PKG")
        return r.ok && r.out.trim().isNotEmpty()
    }

    /** ตรวจว่า su ใช้งานได้จริง (ไม่ถูกปฏิเสธสิทธิ์) — ไว้แยกอาการ "ไม่มี root" ออกจาก error อื่น */
    fun rootAvailable(): Boolean {
        val r = run("id")
        return r.ok && r.out.contains("uid=0")
    }

    fun readLuaState(): LuaState? {
        val r = run("cat '$STATE_FILE'")
        if (!r.ok || r.out.isBlank()) return null
        return try {
            LuaState.from(JSONObject(r.out.trim()))
        } catch (e: Exception) {
            null
        }
    }

    // ---------- กระทำ ----------
    fun forceStop() {
        run("am force-stop $GAME_PKG")
    }

    fun launch(placeId: Long) {
        run("am start -a android.intent.action.VIEW -d 'roblox://placeId=$placeId' $GAME_PKG")
    }

    /** ยัด Lua แบบ atomic + backup — รับ path ไฟล์ในเครื่อง (cache)
     *
     * ทนกว่าเดิม: หาโฟลเดอร์ Autoexecute จากหลาย path (ตัวพิมพ์/alias) แล้วสร้างให้ถ้าไม่มี
     * คืน [Result] เพื่อให้ผู้เรียกรู้สาเหตุจริง (exit code + ข้อความ error ของ su/cp/mv)
     */
    fun pushLua(localPath: String): Result {
        if (!rootAvailable()) {
            return Result(-1, "ไม่มีสิทธิ์ root (su ถูกปฏิเสธ) — อนุญาต root ให้แอปใน Magisk")
        }
        val dir = resolveAutoexecDir()
            ?: return Result(
                -1,
                "ไม่พบโฟลเดอร์ Autoexecute และสร้างไม่ได้ (ลอง: ${AUTOEXEC_CANDIDATES.joinToString()})",
            )
        val dest = "$dir/$LUA_FILENAME"
        val cmd = buildString {
            append("cp '$localPath' '$dest.tmp'; ")
            append("[ -f '$dest' ] && cp '$dest' '$dest.bak'; ")
            append("mv '$dest.tmp' '$dest' && chmod 664 '$dest' && test -s '$dest'")
        }
        return run(cmd)
    }

    /** หาโฟลเดอร์ Autoexecute ที่มีอยู่จริง (ทนตัวพิมพ์) — ถ้าไม่มีเลยให้สร้างที่ path หลัก */
    private fun resolveAutoexecDir(): String? {
        for (dir in AUTOEXEC_CANDIDATES) {
            if (run("test -d '$dir'").ok) return dir
        }
        val primary = AUTOEXEC_CANDIDATES.first()
        return if (run("mkdir -p '$primary'").ok) primary else null
    }

    companion object {
        const val GAME_PKG = "com.roblox.client"
        const val LUA_FILENAME = "rejoin_agent.lua"
        const val AUTOEXEC_DIR = "/storage/emulated/0/Delta/Autoexecute"
        const val LUA_FILE = "$AUTOEXEC_DIR/$LUA_FILENAME"
        const val STATE_FILE = "/storage/emulated/0/Delta/Workspace/lua_state.json"

        /** path ที่เป็นไปได้ของ Autoexecute (Delta บางเวอร์ชันใช้ AutoExecute) */
        val AUTOEXEC_CANDIDATES = listOf(
            "/storage/emulated/0/Delta/Autoexecute",
            "/storage/emulated/0/Delta/AutoExecute",
            "/sdcard/Delta/Autoexecute",
            "/sdcard/Delta/AutoExecute",
        )
    }
}
