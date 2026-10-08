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
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.lifecycleScope
import androidx.lifecycle.repeatOnLifecycle
import com.rejoin.agent.databinding.ActivityMainBinding
import kotlinx.coroutines.launch

/**
 * MainActivity — หน้าจอตั้งค่า: กรอกรหัสเครื่อง + เซิร์ฟเวอร์ + placeId แล้วกดเริ่ม/หยุดเฝ้า
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
        binding.inputPlace.setText(prefs.placeId.toString())
        binding.inputShot.setText(prefs.screenshotIntervalSec.toString())

        binding.btnStart.setOnClickListener { startWatching() }
        binding.btnStop.setOnClickListener { stopWatching() }

        observeState()
        requestNotificationPermission()
    }

    private fun startWatching() {
        val code = binding.inputCode.text.toString().trim()
        val server = binding.inputServer.text.toString().trim()
        val place = binding.inputPlace.text.toString().trim().toLongOrNull()
        if (code.isEmpty()) {
            Toast.makeText(this, "กรอกรหัสเครื่องก่อน (RJ-XXXXX-XXXXX)", Toast.LENGTH_SHORT).show()
            return
        }
        if (place == null) {
            Toast.makeText(this, "placeId ต้องเป็นตัวเลข", Toast.LENGTH_SHORT).show()
            return
        }
        prefs.deviceCode = code
        prefs.serverUrl = server
        prefs.placeId = place
        prefs.screenshotIntervalSec =
            binding.inputShot.text.toString().trim().toIntOrNull()?.coerceAtLeast(0) ?: 0

        ContextCompat.startForegroundService(this, Intent(this, RejoinService::class.java))
    }

    private fun stopWatching() {
        stopService(Intent(this, RejoinService::class.java))
        AgentState.setStatus(getString(R.string.status_stopped))
    }

    private fun observeState() {
        lifecycleScope.launch {
            repeatOnLifecycle(Lifecycle.State.STARTED) {
                launch {
                    AgentState.status.collect { binding.txtStatus.text = it }
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
