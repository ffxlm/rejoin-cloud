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

## เซ็น APK ด้วยคีย์ถาวร (signature เดิมทุก build)

เดิม debug APK จาก CI สร้าง keystore ใหม่ทุก run → **signature เปลี่ยนทุกครั้ง**
ทำให้ `adb install -r` ล้ม (`INSTALL_FAILED_UPDATE_INCOMPATIBLE`) ต้องถอนแอปเก่าก่อน
(ข้อมูลหาย ต้องกรอกรหัสเครื่องใหม่)

แก้แล้วด้วยการเซ็นด้วยคีย์ถาวรที่เก็บใน **GitHub Secrets**:
- `ANDROID_KEYSTORE_BASE64` — ไฟล์ `rejoin.jks` เข้ารหัส base64
- `ANDROID_KEYSTORE_PASSWORD`, `ANDROID_KEY_ALIAS`, `ANDROID_KEY_PASSWORD`

workflow จะถอด keystore ไปที่ `android/app/keystore/rejoin.jks` แล้ว `gradle` เซ็นให้
(`app/build.gradle.kts` → `signingConfigs.rejoin`) → **อัปเดตทับได้เลย**

> 🔑 เก็บสำเนา keystore + รหัสไว้ให้ดี (ดู `ANDROID_KEYSTORE_BASE64`) — หายแล้วเซ็นทับไม่ได้อีก

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
- **กัน ColorOS/realme FastFreezer** (เจอจริงบน realme RMX3201 / ColorOS 11):
  ใส่ package ตัวเองเข้า whitelist `no_frozen` (secure settings) อัตโนมัติผ่าน root
  → `RootShell.protectFromFreezer()` เรียกใน `AgentLoop.run()`
- **กัน Low-Memory Killer (LMK)** — เมื่อเครื่อง RAM น้อย (realme 2.8GB, เกมกิน ~1.7GB):
  foreground service (importance=125) ยังโดนฆ่า (`ApplicationExitInfo reason=3 LOW_MEMORY`)
  → `KeepAlive` รัน shell daemon ผ่าน root (แยกจากแอป):
  1. ตั้ง `oom_score_adj` ของตัวเอง = -1000 (root ตั้งให้ตัวเองได้)
  2. ตรึง `oom_score_adj` ของแอป = -1000 ทุก 2 วิ (กัน AMS รีเซ็ตกลับเป็น 200)
  3. ถ้าแอปตาย → `am start-foreground-service` เปิดกลับ
  หยุดเองเมื่อผู้ใช้กด "หยุดเฝ้า" (ลบ marker `files/watch.enabled`)

### หลักฐานจากเครื่องจริง (realme RMX3201, ColorOS 11, RAM 2.8GB)
- ตัวฆ่าไม่ใช่แค่ LMK แต่เป็น **`ColorHansManager` (FastFreezer) ของ realme**:
  `freeze uid: 10257 package: com.rejoin.agent ... scene: FastFreezerScene`
  → process ยังอยู่ แต่ถูก **แช่แข็ง** (CPU ไม่ถูกจัดคิว) → loop/heartbeat หยุด
- ตรวจสอบ:
  ```bash
  adb shell dumpsys deviceidle whitelist | grep rejoin          # ต้องอยู่ (battery exempt)
  adb shell cat /proc/$(adb shell pidof com.rejoin.agent)/oom_score_adj  # 200 = fg-service
  adb logcat | grep -i "ColorHansManager.*rejoin"               # ดูว่าโดน freeze ไหม
  ```
- แก้ผ่าน root (ได้ผลทันที ไม่ต้องรีบูต):
  ```bash
  adb shell su -c 'settings get secure no_frozen'               # ดูรายชื่อ
  adb shell su -c "settings put secure no_frozen '<เดิม>,com.rejoin.agent'"
  ```
  หลังเพิ่ม → CPU tick ของ process ขยับปกติ และไม่มีบรรทัด `fastfreezer` freeze อีก

**สิ่งที่ต้องทำบนเครื่องคลาวโฟนเอง (สำคัญ — โค้ดทำแทนไม่ได้):**
- ตั้งค่า ROM: อนุญาต **auto-start / background running / อย่าฆ่าแอปนี้**
  (realme: ตั้งค่า → แบตเตอรี่ → จัดการแบตเตอรี่แอป → อนุญาตให้ทำงานเบื้องหลัง)
- ล็อกแอปไว้ใน Recent Apps (ไอคอนกุญแจ) ถ้า ROM มี
- ปิด "ประหยัดแบตอัตโนมัติ" / "ล้างหน่วยความจำอัตโนมัติ" ของ ROM
- เปิด notification ของแอปไว้ (ไม่งั้น Android 13+ ตัด foreground service ได้)
- ⚠️ auto-start (oppoguardelf) ของ realme ตั้งผ่าน settings ไม่ได้ — ต้องกดใน UI

> ⚠️ Google Play เข้มงวดกับ `REQUEST_IGNORE_BATTERY_OPTIMIZATIONS` — APK นี้แจกนอก Play
> (sideload / cloud phone) จึงใช้ได้ แต่ถ้าจะขึ้น Play ต้องเปลี่ยนไปใช้วิธีอื่น
