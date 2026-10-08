# Phase 0 — Checklist พิสูจน์สมมติฐาน (ก่อนเขียนโค้ดจริง)

> เป้าหมาย: ยืนยัน 4 สมมติฐานมรณะ ที่ **ถ้าผิด = ต้องรื้อสถาปัตยกรรม**
> ทุกข้อต้องเทสต์บน **คลาวโฟนจริง** เท่านั้น (unit test ไม่ได้)

**เกณฑ์ผ่าน Phase 0 = ทั้ง 4 ข้อผ่าน** ถ้าข้อไหนไม่ผ่าน ให้ดูหัวข้อ "ทางถอย" ท้ายเอกสาร

| # | สมมติฐาน | ถ้าผิดกระทบ |
|---|---|---|
| **T1** | path `Delta/Autoexecute` ใช้งานได้จริง (เขียน/อ่านได้) | จุดติดตั้ง Lua ทั้งระบบ |
| **T2** | Delta (สวิตช์ Auto Execute) รัน Lua อัตโนมัติ | แกน watchdog |
| **T3** | ตอนรีเกม Delta inject Lua เองได้ | ดีไซน์ "APK เปิดเกมแล้วรอ" พัง ต้องให้ APK trigger |
| **T4** | Lua อ่าน/เขียนไฟล์ได้ + ยิง HTTP ไป `127.0.0.1` ได้ | ช่องทาง Lua → APK |

---

## 0. เตรียมเครื่องและเครื่องมือ

### 0.1 เชื่อม adb + ตรวจ root
```bash
adb connect <IP>:<PORT>          # คลาวโฟนส่วนใหญ่ต่อผ่านเน็ต
adb devices
adb shell getprop ro.build.version.release      # เวอร์ชัน Android
adb shell getprop ro.product.cpu.abi
adb shell su -c id                              # ต้องได้ uid=0(root)
```
**ผ่าน:** `uid=0(root)` → ใช้เส้นทาง root ได้ (แนะนำตามแผน)

### 0.2 หา package เกม + ตัวรัน
```bash
adb shell pm list packages | grep -i roblox
adb shell pm list packages | grep -i delta
adb shell pm list packages | grep -i exec
```
จดชื่อ package ไว้ (เช่น `com.roblox.client`) — ใช้ต่อทุกข้อ

### 0.3 เตรียม listener (ใช้ใน T2/T4)
บน **PC**:
```bash
python3 phase0/local_listener.py 8787
```
อีกหน้าต่าง — ผูกพอร์ตมือถือ → PC:
```bash
adb reverse tcp:8787 tcp:8787
adb reverse --list                # ต้องเห็น tcp:8787
```
> เคล็ดลับ: `adb reverse` ทำให้ Lua ที่ยิงไป `127.0.0.1:8787` บนมือถือ ไปโผล่ที่ PC
> โดยไม่ต้องติดตั้งอะไรบนเครื่อง — ใช้พิสูจน์ว่า Lua ออก localhost ได้จริง

**ทางถอยถ้า `adb reverse` ใช้ไม่ได้** (เช่น adb ไม่ผ่าน): รัน listener บนเครื่องแทน
```bash
adb shell su -c "nc -l -p 8787"          # busybox nc
# หรือบางตัว: adb shell su -c "nc -l 8787"
```

---

## T1 — path `Delta/Autoexecute` ใช้งานได้จริง

**ขั้นตอน**
```bash
adb shell su -c "ls -la /storage/emulated/0/Delta/"
adb shell su -c "ls -la /storage/emulated/0/Delta/Autoexecute/"
adb shell su -c "ls -la /sdcard/Delta/Autoexecute/"       # alias ชี้ที่เดียวกันไหม
adb shell su -c "ls -d /storage/emulated/0/*elta* /storage/emulated/0/*Delta*"  # ทนตัวพิมพ์

# ทดสอบเขียน/อ่านจริง
adb shell su -c "echo phase0-test > /storage/emulated/0/Delta/Autoexecute/_phase0_test.txt"
adb shell su -c "cat /storage/emulated/0/Delta/Autoexecute/_phase0_test.txt"
adb shell su -c "rm /storage/emulated/0/Delta/Autoexecute/_phase0_test.txt"
```

**ผ่านเมื่อ**
- [ ] โฟลเดอร์มีจริง และเขียน/อ่านไฟล์ได้
- [ ] `/sdcard/...` กับ `/storage/emulated/0/...` ชี้ที่เดียวกัน
- [ ] ยืนยันตัวพิมพ์จริงของโฟลเดอร์ (Autoexecute vs AutoExecute)

**บันทึก:** path จริง = `____________________`

---

## T2 — Delta รัน Lua อัตโนมัติ (สวิตช์ Auto Execute)

**เตรียม**
```bash
# 1) ปิดเกมให้สะอาดก่อน
adb shell su -c "am force-stop com.roblox.client"

# 2) วาง probe เป็นชื่อไฟล์จริงของเรา
adb push phase0/phase0_probe.lua /storage/emulated/0/Delta/Autoexecute/rejoin_agent.lua
adb shell su -c "ls -la /storage/emulated/0/Delta/Autoexecute/"
```

**ขั้นตอน**
1. เปิด Delta → **เปิดสวิตช์ Auto Execute** (หาตำแหน่งในเมนู Delta ให้เจอ จดภาพหน้าจอไว้)
2. เปิดเกม:
   ```bash
   adb shell su -c "monkey -p com.roblox.client -c android.intent.category.LAUNCHER 1"
   ```
3. รอโหลดเข้าเกม/เข้า place ~60–120 วิ
4. ดูฝั่ง listener ว่ามี POST `/lua/heartbeat` เข้ามาไหม และดึง log:
   ```bash
   adb shell su -c "find /storage/emulated/0 -iname 'phase0_probe*.log' 2>/dev/null"
   adb shell su -c "find /storage/emulated/0 -ipath '*Delta*' -iname '*.log' 2>/dev/null"
   ```

**ผ่านเมื่อ** (อย่างใดอย่างหนึ่ง)
- [ ] listener ได้รับ POST จาก Lua, **หรือ**
- [ ] เจอไฟล์ `phase0_probe.log` ที่ Lua เขียนไว้

**บันทึก:** โฟลเดอร์ workspace ของ executor = `____________________`

---

## T3 — ตอนรีเกม Delta inject Lua เองได้ (ข้อสำคัญสุด)

เทสต์ว่า **ไม่ต้องแตะ Delta** แล้ว Lua รันใหม่อัตโนมัติเมื่อเกมถูกเปิดใหม่

**ขั้นตอน**
```bash
# 1) เริ่มนับใหม่: ลบ log เก่า
adb shell su -c "rm -f /storage/emulated/0/Delta/Autoexecute/phase0_probe*.log"

# 2) ฆ่าเกม
adb shell su -c "am force-stop com.roblox.client"
adb shell su -c "pidof com.roblox.client"      # ต้องว่าง

# 3) เปิดเกมใหม่ (ไม่แตะ Delta เลย)
adb shell su -c "monkey -p com.roblox.client -c android.intent.category.LAUNCHER 1"
```
รอ ~60–120 วิ แล้วเช็ค log/listener เหมือน T2

**ผ่านเมื่อ**
- [ ] Lua รันเองหลังรีเกม โดยไม่ต้องเปิด Delta / inject มือ

**ถ้าไม่ผ่าน** → ต้องรู้ว่า APK ต้อง trigger อะไรแทน:
- [ ] ลองเปิดแอป Delta แล้วดูว่ามัน auto-inject ให้ไหม
- [ ] จดว่า inject ต้องกดปุ่มไหน / เปิดแอปอะไร (APK จะสั่งผ่าน `am start` แทน)

**บันทึก:** วิธี trigger ที่ได้ผล = `____________________`

---

## T4 — Lua อ่าน/เขียนไฟล์ + ยิง localhost HTTP

ใช้ `phase0_probe.lua` เดิม (มันทดสอบ B และ C ให้ในตัว)

**ตรวจไฟล์ (B)** — ดู log จาก T2/T3 หาบรรทัด `writefile`/`readfile`

**ตรวจ HTTP (C)**
```bash
adb reverse tcp:8787 tcp:8787        # ให้แน่ใจว่ายังผูกอยู่
# เปิด listener ไว้ที่ PC แล้วเปิดเกมให้ probe รัน
```

**ผ่านเมื่อ**
- [ ] `writefile` / `readfile` ทำงาน (มีบรรทัด OK ใน log)
- [ ] มี HTTP request มาถึง listener จากอย่างน้อย 1 ฟังก์ชัน
      (`request` / `http_request` / `syn.request` / `http.request`)
- [ ] จดชื่อฟังก์ชัน HTTP ที่ใช้ได้จริง: `____________________`

**หมายเหตุสำคัญ:** `game:HttpGet` ของ Roblox วิ่งผ่านเซิร์ฟเวอร์ Roblox → **ยิง localhost ไม่ได้**
ต้องใช้ฟังก์ชันระดับ executor (`request` ฯลฯ) เท่านั้น — นี่คือเหตุผลที่ต้องเทสต์ข้อนี้

---

## ทางถอย (ถ้าข้อไหนไม่ผ่าน)

| ข้อ | ถ้าไม่ผ่าน | ทางถอย |
|---|---|---|
| T1 | เขียนโฟลเดอร์ไม่ได้ (Android 11+ ไม่ root) | ขอ MANAGE_EXTERNAL_STORAGE + ให้ผู้ใช้ตั้ง path เอง |
| T2 | Auto Execute ไม่รันอัตโนมัติ | APK ต้องสั่ง inject เอง (หา intent/ปุ่ม) |
| T3 | รีเกมแล้วไม่ inject | **APK ต้องเปิด Delta + สั่ง inject** เป็นขั้นตอนใน auto-rejoin |
| T4 ไฟล์ | อ่าน/เขียนไม่ได้ | ลดบทบาท Lua → สื่อสารผ่าน HTTP อย่างเดียว |
| T4 HTTP | ยิง localhost ไม่ได้ | ถอยไปใช้ **ไฟล์ config/state** ที่ APK อ่าน (shared folder) |

---

## ตารางบันทึกผล

| # | สมมติฐาน | ผ่าน? | หลักฐาน / หมายเหตุ |
|---|---|---|---|
| T1 | path ใช้งานได้ | ☐ ผ่าน ☐ ไม่ | |
| T2 | Auto Execute รัน Lua | ☐ ผ่าน ☐ ไม่ | |
| T3 | รีเกม inject เองได้ | ☐ ผ่าน ☐ ไม่ | |
| T4 | ไฟล์ + localhost HTTP | ☐ ผ่าน ☐ ไม่ | |

**Gate:** ถ้าผ่านครบ → ไปต่อ *Contract → Walking Skeleton*
ถ้า T3 ไม่ผ่าน → ปรับสถาปัตยกรรมก่อน (APK trigger inject) แล้วกลับมาเทสต์ใหม่

---

## คำสั่งอ้างอิงเร็ว

```bash
# เช็คเกมยังรัน
adb shell su -c "pidof com.roblox.client"
adb shell su -c "ps -A | grep -i roblox"

# แคปจอ (พิสูจน์สิทธิ์ screencap)
adb shell su -c "screencap -p /sdcard/phase0_screen.png"
adb pull /sdcard/phase0_screen.png

# เปิด/ปิดเกม
adb shell su -c "am force-stop com.roblox.client"
adb shell su -c "monkey -p com.roblox.client -c android.intent.category.LAUNCHER 1"
```
