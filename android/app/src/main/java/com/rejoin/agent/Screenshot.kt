package com.rejoin.agent

import android.content.Context
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import java.io.ByteArrayOutputStream
import java.io.File

/**
 * Screenshot — แคปหน้าจอ → ย่อ → JPEG (ลดขนาดก่อนอัปขึ้นเว็บ)
 *
 * ใช้ `screencap -p` ผ่าน root (RootShell) แล้ว decode/ย่อ/บีบอัดด้วย Bitmap ของ Android
 * ไม่ต้องเพิ่ม dependency ภายนอก (ประหยัดเน็ตคลาวโฟน)
 */
object Screenshot {

    private const val MAX_WIDTH = 1280
    private const val JPEG_QUALITY = 70

    /** คืน JPEG bytes หรือ null ถ้าแคปไม่ได้ */
    fun captureJpeg(context: Context, root: RootShell): ByteArray? {
        val tmp = File(context.cacheDir, "shot_${System.currentTimeMillis()}.png")
        try {
            if (!root.captureScreen(tmp.absolutePath)) return null
            if (!tmp.exists() || tmp.length() == 0L) return null

            val decoded = BitmapFactory.decodeFile(tmp.absolutePath) ?: return null
            val scaled = downscale(decoded)
            val out = ByteArrayOutputStream()
            scaled.compress(Bitmap.CompressFormat.JPEG, JPEG_QUALITY, out)
            if (scaled !== decoded) decoded.recycle()
            scaled.recycle()
            return out.toByteArray()
        } catch (e: Exception) {
            AgentState.log("screenshot error: ${e.message}")
            return null
        } finally {
            tmp.delete()
        }
    }

    private fun downscale(src: Bitmap): Bitmap {
        if (src.width <= MAX_WIDTH) return src
        val ratio = MAX_WIDTH.toFloat() / src.width
        val h = (src.height * ratio).toInt().coerceAtLeast(1)
        return Bitmap.createScaledBitmap(src, MAX_WIDTH, h, true)
    }
}
