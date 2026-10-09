package com.rejoin.agent

import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONObject
import java.util.concurrent.TimeUnit

/**
 * Api — คุยกับเว็บ (ตาม CONTRACT.md §2)
 *   POST /api/agent/register   แลก device_code → device_token
 *   POST /api/agent/heartbeat  ส่งสถานะ → รับคำสั่ง
 *   POST /api/agent/event      ส่ง event (rejoin/alert)
 *   GET  /api/download/lua     ดึง Lua (แก้ที่เว็บได้ ไม่ต้อง build APK ใหม่)
 */
class Api(private val prefs: Prefs) {

    data class RegisterResult(val deviceToken: String, val deviceId: String, val intervalSec: Int)

    @Volatile
    var token: String? = null

    private val client = OkHttpClient.Builder()
        .connectTimeout(15, TimeUnit.SECONDS)
        .readTimeout(20, TimeUnit.SECONDS)
        .writeTimeout(20, TimeUnit.SECONDS)
        .build()

    private val jsonMedia = "application/json; charset=utf-8".toMediaType()

    private fun base() = prefs.serverUrl.trimEnd('/')

    fun register(androidId: String?): RegisterResult? {
        val body = JSONObject()
            .put("device_code", prefs.deviceCode)
            .put("apk_version", APK_VERSION)
            .put("android_id", androidId ?: "")
        val req = Request.Builder()
            .url("${base()}/api/agent/register")
            .post(body.toString().toRequestBody(jsonMedia))
            .build()
        return try {
            client.newCall(req).execute().use { resp ->
                if (!resp.isSuccessful) {
                    AgentState.log("register HTTP ${resp.code}")
                    return null
                }
                val o = JSONObject(resp.body?.string() ?: return null)
                RegisterResult(
                    deviceToken = o.getString("device_token"),
                    deviceId = o.getString("device_id"),
                    intervalSec = o.optInt("interval_sec", 15),
                )
            }
        } catch (e: Exception) {
            AgentState.log("register error: ${e.javaClass.simpleName}: ${e.message}")
            null
        }
    }

    fun heartbeat(
        wd: Watchdog,
        obs: Observation,
        sessionStart: Long,
        state: LuaState?,
    ): String? {
        val tok = token ?: return null
        val alive = obs.luaAgeSec != null && obs.luaAgeSec <= wd.cfg.silenceSec
        val body = JSONObject()
            .put("v", 1)
            .put("state", wd.phase.value)
            .put("armed", wd.armed)
            .put("game_running", obs.gameRunning)
            .put("lua_active", alive)
            .put("rejoin_count", wd.rejoinCount)
            .put("session_start", sessionStart)
            .put("ts", System.currentTimeMillis() / 1000)
        obs.luaAgeSec?.let { body.put("lua_age_sec", it) }
        state?.let {
            body.put("lua_state", it.state)
            it.avatar?.let { a -> body.put("avatar", a) }
            it.character?.let { c -> body.put("character", c) }
            it.map?.let { m -> body.put("map", m) }
            if (it.placeId != 0L) body.put("place_id", it.placeId)
            it.jobId?.let { j -> body.put("job_id", j) }
        }
        val req = Request.Builder()
            .url("${base()}/api/agent/heartbeat")
            .header("Authorization", "Bearer $tok")
            .post(body.toString().toRequestBody(jsonMedia))
            .build()
        return try {
            client.newCall(req).execute().use { resp ->
                if (!resp.isSuccessful) return null
                val o = JSONObject(resp.body?.string() ?: return null)
                if (o.isNull("command")) null else o.optString("command", "").ifEmpty { null }
            }
        } catch (e: Exception) {
            null
        }
    }

    fun sendEvent(type: String, detail: JSONObject) {
        val tok = token ?: return
        val body = JSONObject().put("type", type).put("detail", detail)
        val req = Request.Builder()
            .url("${base()}/api/agent/event")
            .header("Authorization", "Bearer $tok")
            .post(body.toString().toRequestBody(jsonMedia))
            .build()
        try {
            client.newCall(req).execute().close()
        } catch (e: Exception) {
            // เงียบ — event ไม่สำคัญพอจะทำให้ loop ล้ม
        }
    }

    fun downloadLua(): ByteArray? {
        val req = Request.Builder()
            .url("${base()}/api/download/lua")
            .get()
            .build()
        return try {
            client.newCall(req).execute().use { resp ->
                if (!resp.isSuccessful) {
                    AgentState.log("downloadLua HTTP ${resp.code}")
                    return null
                }
                resp.body?.bytes()
            }
        } catch (e: Exception) {
            AgentState.log("downloadLua error: ${e.javaClass.simpleName}: ${e.message}")
            null
        }
    }

    companion object {
        const val APK_VERSION = "0.2.0"
    }
}
