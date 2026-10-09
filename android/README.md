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

## สถานะสเกเลตัน (buildable + รันจริงบนเครื่องแล้ว)
- [x] Gradle + Kotlin + AndroidX + Material3
- [x] `MainActivity` — กรอกรหัสเครื่อง + เซิร์ฟเวอร์, ปุ่มเริ่ม/หยุด
- [x] `RejoinService` — Foreground Service (specialUse) + notification ค้าง
- [x] `Prefs` — EncryptedSharedPreferences (เก็บ device_token เข้ารหัส)
- [x] manifest + สิทธิ์ (INTERNET, FOREGROUND_SERVICE, POST_NOTIFICATIONS, …)

### ✅ ยืนยันบนเครื่องจริง (2026-10-08)
- build บน CI สำเร็จ → `app-debug.apk` (6.8 MB)
- `adb install -r` สำเร็จ → เปิดแอป UI ขึ้นถูกต้อง
- กด "เริ่มเฝ้า" → Foreground Service รัน (`isForeground=true`) + notification ค้าง
- กด "หยุดเฝ้า" → service หยุด สถานะเป็น "หยุดแล้ว"
- ⚠️ ยังเป็นสเกเลตัน — **ยังไม่คุยกับเว็บ/ยังไม่แตะ Lua/เกม** (สเต็ปถัดไป)

## ยังไม่ทำ (สเต็ปถัดไป)
- [ ] File watcher อ่าน `Delta/Workspace/lua_state.json` → คำนวณความเงียบ
- [ ] พอร์ต `watchdog.py` เป็น Kotlin (pure state machine)
- [x] root: `su -c am force-stop / am start`
- [x] ยัด Lua (atomic + backup) — พอร์ตจาก `device.py:push_lua`
- [x] heartbeat + poll คำสั่ง arm/disarm/rejoin_now (OkHttp)
- [x] ลงทะเบียนด้วยรหัสเครื่อง → เก็บ device_token

## กันแอปถูกระบบฆ่าตอนเข้าเกม (cloud phone)

**อาการ:** กด "เฝ้าเกม" แล้วเข้าเกมไปสักพัก แอป/notification หาย — เพราะตอนเกมรัน
(Roblox/Delta กิน RAM หนัก) ROM จะฆ่า process พื้นหลัง แม้เป็น Foreground Service

**สิ่งที่แก้ในโค้ดแล้ว:**
- `android:stopWithTask="false"` → ปัดแอปออกจาก Recent Apps แล้ว service ไม่ตาย
- ขอยกเว้น **battery optimization / Doze** อัตโนมัติตอนกด "เฝ้าเกม" (ต้องกด Allow)
  (`REQUEST_IGNORE_BATTERY_OPTIMIZATIONS` + `Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS`)
- `onTaskRemoved()` → สั่งเปิด service ตัวเองกลับ (เผื่อ ROM ยังฆ่า)
- `BootReceiver` → รีบูตเครื่องแล้วเปิด service กลับ (ถ้าเคยกดเฝ้าไว้)

**สิ่งที่ต้องทำบนเครื่องคลาวโฟนเอง (สำคัญ — โค้ดทำแทนไม่ได้):**
- ตั้งค่า ROM: อนุญาต **auto-start / background running / อย่าฆ่าแอปนี้**
- ล็อกแอปไว้ใน Recent Apps (ไอคอนกุญแจ) ถ้า ROM มี
- ปิด "ประหยัดแบตอัตโนมัติ" / "ล้างหน่วยความจำอัตโนมัติ" ของ ROM
- เปิด notification ของแอปไว้ (ไม่งั้น Android 13+ ตัด foreground service ได้)

> ⚠️ Google Play เข้มงวดกับ `REQUEST_IGNORE_BATTERY_OPTIMIZATIONS` — APK นี้แจกนอก Play
> (sideload / cloud phone) จึงใช้ได้ แต่ถ้าจะขึ้น Play ต้องเปลี่ยนไปใช้วิธีอื่น
