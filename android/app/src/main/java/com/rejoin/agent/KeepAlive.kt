package com.rejoin.agent

import android.content.Context
import android.os.Process
import java.io.File

/**
 * KeepAlive — ให้ process รอดจาก Low-Memory Killer (LMK) บนเครื่อง RAM น้อย
 *
 * ปัญหาที่เจอจริง (realme RMX3201 / ColorOS 11 / RAM 2.8GB, zram 1.6GB):
 * เกมกิน RAM ~1.7GB → ระบบตึง → LMK ฆ่า foreground service
 * (ApplicationExitInfo reason=3 LOW_MEMORY ทั้งที่ importance=125)
 *
 * วิธีแก้: shell loop ที่รันผ่าน root แยกจากแอป (แอปตายก็ยังอยู่):
 *   1) ตั้ง oom_score_adj ของตัวเอง = -1000 (root ตั้งให้ตัวเองได้ — พิสูจน์แล้ว)
 *   2) ตรึง oom_score_adj ของแอป = -1000 ทุก 2 วิ (กัน AMS รีเซ็ตกลับเป็น 200)
 *   3) ถ้าแอปตาย → เปิด RejoinService กลับ
 * หยุดเองเมื่อไฟล์ marker ถูกลบ (ผู้ใช้กด "หยุดเฝ้า")
 */
class KeepAlive(private val context: Context, private val root: RootShell) {

    private val scriptFile = File(context.filesDir, "keepalive.sh")
    private val markerFile = File(context.filesDir, "watch.enabled")
    private val pidFile = File(context.filesDir, "keepalive.pid")

    /** เริ่ม daemon + สร้าง marker (เรียกหลังเช็ค root ผ่านแล้ว) */
    fun start() {
        if (root.checkRoot().state != RootShell.RootState.OK) return
        markerFile.writeText("1")
        scriptFile.writeText(script(markerFile.absolutePath))
        // ปิดตัวเก่าก่อน (กันซ้ำ) แล้วสตาร์ทแบบ detach (setsid → parent = init)
        root.run(
            buildString {
                append("if [ -f '${pidFile.absolutePath}' ]; then ")
                append("kill \$(cat '${pidFile.absolutePath}') 2>/dev/null; fi; ")
                append("setsid sh '${scriptFile.absolutePath}' >/dev/null 2>&1 < /dev/null & ")
                append("echo \$! > '${pidFile.absolutePath}'")
            }
        )
    }

    /** หยุด daemon + ลบ marker (ผู้ใช้กดหยุดเฝ้า) */
    fun stop() {
        markerFile.delete()
        root.run(
            "if [ -f '${pidFile.absolutePath}' ]; then " +
                "kill \$(cat '${pidFile.absolutePath}') 2>/dev/null; rm -f '${pidFile.absolutePath}'; fi"
        )
    }

    /** ตรึง adj ของ process ตัวเองด้วย (สำรอง เผื่อ daemon ยังไม่ทันตั้ง) */
    fun pinSelf() {
        root.run("echo -1000 > /proc/${Process.myPid()}/oom_score_adj 2>/dev/null")
    }

    /**
     * ตัว script จริง — ฝังเป็น string (เขียนลง filesDir แล้วรันผ่าน root)
     * `${'$'}` ใช้ escape ไม่ให้ Kotlin interpolate
     */
    private fun script(markerPath: String): String = """
        #!/system/bin/sh
        echo -1000 > /proc/self/oom_score_adj 2>/dev/null
        magiskpolicy --live 'allow magisk untrusted_app file write' 2>/dev/null
        while [ -f "$markerPath" ]; do
          p=${'$'}(pidof com.rejoin.agent)
          if [ -n "${'$'}p" ]; then
            echo -1000 > /proc/${'$'}p/oom_score_adj 2>/dev/null
          else
            am start-foreground-service -n com.rejoin.agent/.RejoinService >/dev/null 2>&1
          fi
          sleep 2
        done
    """.trimIndent()
}
