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

    /** ยัด Lua แบบ atomic + backup — รับ path ไฟล์ในเครื่อง (cache) */
    fun pushLua(localPath: String): Boolean {
        val cmd = buildString {
            append("cp '$localPath' '$LUA_FILE.tmp'; ")
            append("[ -f '$LUA_FILE' ] && cp '$LUA_FILE' '$LUA_FILE.bak'; ")
            append("mv '$LUA_FILE.tmp' '$LUA_FILE' && chmod 664 '$LUA_FILE'")
        }
        return run(cmd).ok
    }

    companion object {
        const val GAME_PKG = "com.roblox.client"
        const val AUTOEXEC_DIR = "/storage/emulated/0/Delta/Autoexecute"
        const val LUA_FILE = "$AUTOEXEC_DIR/rejoin_agent.lua"
        const val STATE_FILE = "/storage/emulated/0/Delta/Workspace/lua_state.json"
    }
}
