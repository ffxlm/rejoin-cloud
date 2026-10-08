package com.rejoin.agent

import android.Manifest
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import android.os.Bundle
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import androidx.core.app.ActivityCompat
import androidx.core.content.ContextCompat
import com.rejoin.agent.databinding.ActivityMainBinding

/**
 * MainActivity — หน้าจอตั้งค่า: กรอกรหัสเครื่อง + เซิร์ฟเวอร์ แล้วกดเริ่ม/หยุดเฝ้า
 *
 * สเกเลตัน: ยังไม่ทำ watchdog/heartbeat จริง — แค่เริ่ม/หยุด Foreground Service
 * (สเต็ปถัดไปจะพอร์ต logic จาก skeleton/agent/watchdog.py มาใส่ service)
 */
class MainActivity : AppCompatActivity() {

    private lateinit var binding: ActivityMainBinding
    private lateinit var prefs: Prefs

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityMainBinding.inflate(layoutInflater)
        setContentView(binding.root)

        prefs = Prefs(this)
        binding.inputCode.setText(prefs.deviceCode)
        binding.inputServer.setText(prefs.serverUrl)

        binding.btnStart.setOnClickListener { startWatching() }
        binding.btnStop.setOnClickListener { stopWatching() }

        requestNotificationPermission()
    }

    private fun startWatching() {
        val code = binding.inputCode.text.toString().trim()
        val server = binding.inputServer.text.toString().trim()
        if (code.isEmpty()) {
            Toast.makeText(this, "กรอกรหัสเครื่องก่อน (RJ-XXXXX-XXXXX)", Toast.LENGTH_SHORT).show()
            return
        }
        prefs.deviceCode = code
        prefs.serverUrl = server

        val intent = Intent(this, RejoinService::class.java)
        ContextCompat.startForegroundService(this, intent)
        binding.txtStatus.text = getString(R.string.status_watching)
    }

    private fun stopWatching() {
        stopService(Intent(this, RejoinService::class.java))
        binding.txtStatus.text = getString(R.string.status_stopped)
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
