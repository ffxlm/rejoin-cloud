package com.rejoin.agent

import android.content.Context
import androidx.security.crypto.EncryptedSharedPreferences
import androidx.security.crypto.MasterKey

/**
 * Prefs — เก็บค่า config + device_token แบบเข้ารหัส
 * (EncryptedSharedPreferences / Android Keystore — ไม่เก็บ plaintext)
 */
class Prefs(context: Context) {

    private val masterKey = MasterKey.Builder(context)
        .setKeyScheme(MasterKey.KeyScheme.AES256_GCM)
        .build()

    private val sp = EncryptedSharedPreferences.create(
        context,
        "rejoin_secure_prefs",
        masterKey,
        EncryptedSharedPreferences.PrefKeyEncryptionScheme.AES256_SIV,
        EncryptedSharedPreferences.PrefValueEncryptionScheme.AES256_GCM,
    )

    var deviceCode: String
        get() = sp.getString(KEY_DEVICE_CODE, "") ?: ""
        set(v) = sp.edit().putString(KEY_DEVICE_CODE, v).apply()

    var serverUrl: String
        get() = sp.getString(KEY_SERVER_URL, DEFAULT_SERVER) ?: DEFAULT_SERVER
        set(v) = sp.edit().putString(KEY_SERVER_URL, v).apply()    /** device_token ที่ได้หลังลงทะเบียน (เก็บเข้ารหัส) */
    var deviceToken: String?
        get() = sp.getString(KEY_DEVICE_TOKEN, null)
        set(v) = sp.edit().putString(KEY_DEVICE_TOKEN, v).apply()

    var placeId: Long
        get() = sp.getLong(KEY_PLACE_ID, DEFAULT_PLACE_ID)
        set(v) = sp.edit().putLong(KEY_PLACE_ID, v).apply()

    var intervalSec: Int
        get() = sp.getInt(KEY_INTERVAL, 8)
        set(v) = sp.edit().putInt(KEY_INTERVAL, v).apply()

    var silenceSec: Int
        get() = sp.getInt(KEY_SILENCE, 60)
        set(v) = sp.edit().putInt(KEY_SILENCE, v).apply()

    var timeoutSec: Int
        get() = sp.getInt(KEY_TIMEOUT, 300)
        set(v) = sp.edit().putInt(KEY_TIMEOUT, v).apply()

    /** แคปหน้าจออัตโนมัติทุกกี่วินาทีขณะ arm (0 = ปิด; สั่งแคปจากเว็บได้เสมอ) */
    var screenshotIntervalSec: Int
        get() = sp.getInt(KEY_SHOT_INTERVAL, 0)
        set(v) = sp.edit().putInt(KEY_SHOT_INTERVAL, v).apply()

    companion object {
        private const val KEY_DEVICE_CODE = "device_code"
        private const val KEY_SERVER_URL = "server_url"
        private const val KEY_DEVICE_TOKEN = "device_token"
        private const val KEY_PLACE_ID = "place_id"
        private const val KEY_INTERVAL = "interval_sec"
        private const val KEY_SILENCE = "silence_sec"
        private const val KEY_TIMEOUT = "timeout_sec"
        private const val KEY_SHOT_INTERVAL = "screenshot_interval_sec"

        const val DEFAULT_SERVER = "https://rejoin.example.com"  // ← แก้เป็นโดเมนจริงของคุณ
        const val DEFAULT_PLACE_ID = 107778070777162L
    }
}
