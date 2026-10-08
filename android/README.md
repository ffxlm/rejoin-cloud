# Android Agent (Kotlin) — สเกเลตัน

APK ตัวแทน agent.py บนเครื่อง (จะค่อยๆ พอร์ตจาก `skeleton/agent/`)

## สร้าง APK ด้วย GitHub Actions (ไม่ต้องติดตั้ง SDK บนเครื่อง)

push โค้ดใน `android/` ขึ้น GitHub → workflow `.github/workflows/android.yml` จะ:
1. ติดตั้ง JDK 17 + Android SDK + Gradle (บน runner)
2. `gradle assembleDebug`
3. อัปโหลด APK เป็น **Artifact**

ดาวน์โหลด APK:
- หน้า GitHub → แท็บ **Actions** → เลือก run ล่าสุด → **Artifacts** → `rejoin-agent-debug`
- หรือใช้ gh CLI:
  ```bash
  gh run list --workflow=android.yml
  gh run watch            # เฝ้า run ล่าสุด
  gh run download -n rejoin-agent-debug
  ```

กด build เองได้จาก Actions → *Android APK* → **Run workflow** (`workflow_dispatch`)

## ติดตั้งลงเครื่องจริง
```bash
.tools/platform-tools/adb install -r rejoin-agent-debug/app-debug.apk
```

## สถานะสเกเลตัน (buildable)
- [x] Gradle + Kotlin + AndroidX + Material3
- [x] `MainActivity` — กรอกรหัสเครื่อง + เซิร์ฟเวอร์, ปุ่มเริ่ม/หยุด
- [x] `RejoinService` — Foreground Service (specialUse) + notification ค้าง
- [x] `Prefs` — EncryptedSharedPreferences (เก็บ device_token เข้ารหัส)
- [x] manifest + สิทธิ์ (INTERNET, FOREGROUND_SERVICE, POST_NOTIFICATIONS, …)

## ยังไม่ทำ (สเต็ปถัดไป)
- [ ] File watcher อ่าน `Delta/Workspace/lua_state.json` → คำนวณความเงียบ
- [ ] พอร์ต `watchdog.py` เป็น Kotlin (pure state machine)
- [ ] root: `su -c am force-stop / am start`
- [ ] ยัด Lua (atomic + backup) — พอร์ตจาก `device.py:push_lua`
- [ ] heartbeat + poll คำสั่ง arm/disarm/rejoin_now (OkHttp)
- [ ] ลงทะเบียนด้วยรหัสเครื่อง → เก็บ device_token
