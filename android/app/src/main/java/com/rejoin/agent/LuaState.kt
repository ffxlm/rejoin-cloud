package com.rejoin.agent

import org.json.JSONObject

/**
 * LuaState — state ที่ Lua เขียนลง Delta/Workspace/lua_state.json
 * ตามสัญญา CONTRACT.md §1.1
 */
data class LuaState(
    val v: Int = 1,
    val state: String? = null,     // in_game | loading | menu | unknown
    val avatar: String? = null,
    val character: String? = null,
    val map: String? = null,
    val placeId: Long = 0,
    val jobId: String? = null,
    val ts: Long = 0,
) {
    companion object {
        fun from(json: JSONObject): LuaState = LuaState(
            v = json.optInt("v", 1),
            state = json.optString("state", "").ifEmpty { null },
            avatar = json.optString("avatar", "").ifEmpty { null },
            character = json.optString("character", "").ifEmpty { null },
            map = json.optString("map", "").ifEmpty { null },
            placeId = json.optLong("place_id", 0),
            jobId = json.optString("job_id", "").ifEmpty { null },
            ts = json.optLong("ts", 0),
        )
    }
}
