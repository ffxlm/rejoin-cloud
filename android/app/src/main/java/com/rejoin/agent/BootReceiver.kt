package com.rejoin.agent

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import androidx.core.content.ContextCompat

/**
 * BootReceiver — เปิด Foreground Service กลับมาหลังเครื่องรีบูต
 *
 * ทำงานเฉพาะเมื่อผู้ใช้เคยกด "เฝ้าเกม" ไว้ก่อนปิดเครื่อง (prefs.watchEnabled)
 * ไม่งั้นจะเปิด service เองโดยที่ผู้ใช้ไม่ได้สั่ง — ไม่ควรทำ
 */
class BootReceiver : BroadcastReceiver() {

    override fun onReceive(context: Context, intent: Intent) {
        if (intent.action != Intent.ACTION_BOOT_COMPLETED) return
        if (!Prefs(context).watchEnabled) return
        ContextCompat.startForegroundService(
            context,
            Intent(context, RejoinService::class.java),
        )
    }
}
