package com.rejoin.agent

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.Service
import android.content.Intent
import android.content.pm.ServiceInfo
import android.os.Build
import android.os.IBinder
import androidx.core.app.NotificationCompat

/**
 * RejoinService — Foreground Service ที่จะเฝ้าเกมตลอดเวลา
 *
 * สเกเลตัน: แค่รันเป็น foreground + แสดง notification ค้างไว้ (พิสูจน์ว่า service
 * อยู่รอด) — สเต็ปถัดไปจะเพิ่ม:
 *   - File watcher อ่าน lua_state.json (คำนวณความเงียบ)
 *   - watchdog state machine (พอร์ตจาก watchdog.py)
 *   - root: force-stop / launch เกม + ยัด Lua
 *   - heartbeat/poll ไปเว็บด้วย OkHttp
 */
class RejoinService : Service() {

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onCreate() {
        super.onCreate()
        createChannel()
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        val notification = buildNotification()
        if (Build.VERSION.SDK_INT >= 34) {
            startForeground(
                NOTIF_ID,
                notification,
                ServiceInfo.FOREGROUND_SERVICE_TYPE_SPECIAL_USE,
            )
        } else {
            startForeground(NOTIF_ID, notification)
        }
        // TODO(step 2): เริ่ม watchdog loop (coroutine) ตรงนี้
        return START_STICKY
    }

    override fun onDestroy() {
        // TODO(step 2): ยกเลิก coroutine / ปิด resource
        super.onDestroy()
    }

    private fun createChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val channel = NotificationChannel(
                CHANNEL_ID,
                getString(R.string.channel_name),
                NotificationManager.IMPORTANCE_LOW,
            )
            val nm = getSystemService(NotificationManager::class.java)
            nm.createNotificationChannel(channel)
        }
    }

    private fun buildNotification(): Notification =
        NotificationCompat.Builder(this, CHANNEL_ID)
            .setContentTitle(getString(R.string.notif_title))
            .setContentText(getString(R.string.notif_text))
            .setSmallIcon(android.R.drawable.stat_notify_sync)
            .setOngoing(true)
            .build()

    companion object {
        private const val CHANNEL_ID = "rejoin_agent"
        private const val NOTIF_ID = 1
    }
}
