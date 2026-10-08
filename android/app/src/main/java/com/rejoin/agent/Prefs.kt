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
        set(v) = sp.edit().putString(KEY_SERVER_URL, v).apply()

    /** device_token ที่ได้หลังลงทะเบียน (ยังไม่ใช้ในสเกเลตัน) */
    var deviceToken: String
        get() = sp.getString(KEY_DEVICE_TOKEN, "") ?: ""
        set(v) = sp.edit().putString(KEY_DEVICE_TOKEN, v).apply()

    companion object {
        private const val KEY_DEVICE_CODE = "device_code"
        private const val KEY_SERVER_URL = "server_url"
        private const val KEY_DEVICE_TOKEN = "device_token"
        const val DEFAULT_SERVER = "http://127.0.0.1:8000"
    }
}
