package com.rejoin.agent

import android.Manifest
import android.content.Intent
import android.content.pm.PackageManager
import android.content.res.ColorStateList
import android.os.Build
import android.os.Bundle
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import androidx.core.app.ActivityCompat
import androidx.core.content.ContextCompat
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.lifecycleScope
import androidx.lifecycle.repeatOnLifecycle
import com.rejoin.agent.databinding.ActivityMainBinding
import kotlinx.coroutines.launch

/**
 * MainActivity — หน้าจอตั้งค่าแบบ iOS (dark):
 * กรอกรหัสเครื่อง + เซิร์ฟเวอร์ + placeId แล้วสลับ Switch "เฝ้าเกม" เพื่อเริ่ม/หยุด
 */
class MainActivity : AppCompatActivity() {

    private lateinit var binding: ActivityMainBinding
    private lateinit var prefs: Prefs

    /** กันไม่ให้ listener ยิงซ้ำตอนเราสั่ง setChecked() เอง (เช่น revert หรือ sync สถานะ) */
    private var suppressSwitch = false

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityMainBinding.inflate(layoutInflater)
        setContentView(binding.root)

        prefs = Prefs(this)
        binding.inputCode.setText(prefs.deviceCode)
        binding.inputServer.setText(prefs.serverUrl)
        binding.inputPlace.setText(prefs.placeId.toString())

        binding.switchWatch.setOnCheckedChangeListener { _, checked ->
            if (suppressSwitch) return@setOnCheckedChangeListener
            if (checked) startWatching() else stopWatching()
        }

        observeState()
        requestNotificationPermission()

        // กลับเข้าหน้าใหม่ตอน service ยังรันอยู่ → switch ต้องติด
        setSwitchSilently(AgentState.status.value.running)
    }

    /** ตั้งค่า switch โดยไม่กระตุ้น listener */
    private fun setSwitchSilently(checked: Boolean) {
        suppressSwitch = true
        binding.switchWatch.isChecked = checked
        suppressSwitch = false
    }

    private fun startWatching() {
        val code = binding.inputCode.text.toString().trim()
        val server = binding.inputServer.text.toString().trim()
        val place = binding.inputPlace.text.toString().trim().toLongOrNull()
        if (code.isEmpty()) {
            Toast.makeText(this, "กรอกรหัสเครื่องก่อน (RJ-XXXXX-XXXXX)", Toast.LENGTH_SHORT).show()
            setSwitchSilently(false)
            return
        }
        if (place == null) {
            Toast.makeText(this, "placeId ต้องเป็นตัวเลข", Toast.LENGTH_SHORT).show()
            setSwitchSilently(false)
            return
        }
        prefs.deviceCode = code
        prefs.serverUrl = server
        prefs.placeId = place

        ContextCompat.startForegroundService(this, Intent(this, RejoinService::class.java))
    }

    private fun stopWatching() {
        stopService(Intent(this, RejoinService::class.java))
        AgentState.setStatus(getString(R.string.status_stopped), StatusLevel.IDLE)
    }

    private fun observeState() {
        lifecycleScope.launch {
            repeatOnLifecycle(Lifecycle.State.STARTED) {
                launch {
                    AgentState.status.collect { status -> renderStatus(status) }
                }
                launch {
                    AgentState.logs.collect { list ->
                        binding.txtLog.text = list.joinToString("\n")
                        binding.scrollLog.post { binding.scrollLog.fullScroll(android.view.View.FOCUS_DOWN) }
                    }
                }
            }
        }
    }

    /** วาดสถานะ: ข้อความภาษาคน + สีจุดบอกสถานะ (เขียว=ทำงาน, เหลือง=กำลังกู้, แดง=ผิดพลาด) */
    private fun renderStatus(status: AgentStatus) {
        binding.txtStatus.text = status.text
        binding.statusDot.backgroundTintList =
            ColorStateList.valueOf(ContextCompat.getColor(this, levelColorRes(status.level)))
        binding.txtStatus.setTextColor(
            ContextCompat.getColor(
                this,
                if (status.level == StatusLevel.IDLE) R.color.ios_secondary_label else R.color.ios_label,
            )
        )
        // service หยุดเอง/ผิดพลาด → ดัน switch กลับ off
        if (!status.running) setSwitchSilently(false)
    }

    private fun levelColorRes(level: StatusLevel): Int = when (level) {
        StatusLevel.IDLE -> R.color.ios_secondary_label
        StatusLevel.INFO -> R.color.ios_blue
        StatusLevel.ACTIVE -> R.color.ios_green
        StatusLevel.WARN -> R.color.ios_orange
        StatusLevel.ERROR -> R.color.ios_red
    }

    private fun requestNotificationPermission() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            if (ContextCompat.checkSelfPermission(this, Manifest.permission.POST_NOTIFICATIONS)
                != PackageManager.PERMISSION_GRANTED
            ) {
                ActivityCompat.requestPermissions(
                    this,
                    arrayOf(Manifest.permission.POST_NOTIFICATIONS),
                    REQ_NOTIF,
                )
            }
        }
    }

    companion object {
        private const val REQ_NOTIF = 1001
    }
}
