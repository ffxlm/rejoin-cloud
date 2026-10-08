# Phase 0 — บันทึกผลการเทสต์ (Results Log)

> อัปเดตล่าสุด: 2026-10-08
> เป้าหมาย: พิสูจน์ 4 สมมติฐานมรณะ ก่อนเขียนโค้ดจริง

## ข้อมูลเครื่องเป้าหมาย

| รายการ | ค่า |
|---|---|
| ปลายทาง adb | `192.168.96.160:5555` |
| รุ่น | RMX3201 (Realme) |
| Android | 11 |
| ABI | arm64-v8a |
| SELinux | Enforcing |
| root | ✅ Magisk (`context=u:r:magisk:s0`, su = `/product/bin/su`) |
| adb | 1.0.41 (37.0.1) — `.tools/platform-tools/adb` |
| เกม | `com.roblox.client` (พบแล้ว) |

---

## ผลรายข้อ

### ขั้น 1 — adb + root ✅ ผ่าน
- `adb connect 192.168.96.160:5555` → `device`
- `su -c id` → `uid=0(root)` ทดสอบซ้ำ 2 ครั้ง ได้ผลเดิม
- เกม `com.roblox.client` ติดตั้งอยู่
- หมายเหตุ: SELinux Enforcing; ยังไม่พบ package Delta/executor (หาในขั้น 2)

### ขั้น 2 — หา package Delta + ตรวจ path ✅ ผ่าน
- **ไม่มี package ชื่อ Delta** — Delta คือ **Roblox client ที่ถูกแพตช์** ติดตั้งทับเป็น
  `com.roblox.client` v**2.740.931** (ตรงกับไฟล์ `Download/Delta-2.740.931.apk`)
- `pm path com.roblox.client` → `/data/app/.../com.roblox.client-.../base.apk`
- โปรเซสที่รันอยู่: `com.roblox.client` (pid 26718)
- โครงสร้างโฟลเดอร์ Delta (บน `/storage/emulated/0/Delta/`):
  | โฟลเดอร์ | บทบาท |
  |---|---|
  | `Autoexecute/` | จุดวางสคริปต์ auto-run → มี `rejoin_agent.lua` แล้ว |
  | `Workspace/` | workspace ของ executor (writefile แบบ relative ลงที่นี่) |
  | `Scripts/` | ว่าง |
  | `Internals/` | Assets, Cache, Settings, Secured (ภายในของ Delta) |
- มี asset `AutoExecNotify.png` → Delta มีระบบ auto-exec จริง (ต้องยืนยัน T2)

> **ผลกระทบต่อแผน:** มีเพียง **package เดียว** ที่ต้องเปิด (`com.roblox.client`) — executor
> รันอยู่ในโปรเซสเดียวกัน ไม่มีแอป Delta แยกให้เปิด/สลับ

### T1 — path `Delta/Autoexecute` ✅ ผ่าน
- `/storage/emulated/0/Delta/Autoexecute/` มีจริง เขียน/อ่านได้
- วาง `rejoin_agent.lua` ได้แล้ว
- workspace ของ executor = `/storage/emulated/0/Delta/Workspace/`

### T2 — Delta Auto Execute รัน Lua อัตโนมัติ ✅ ผ่าน
- ยืนยันด้วย **GUI ตัวนับวิ่งมุมจอ** (`REJOIN autoexec OK | 32s | ...`) โผล่เองโดยไม่แตะเกม
- probe รันเองหลายรอบ (t=...483/484) + เขียน log เอง
- ข้อสรุป: Auto Execute ทำงาน → วางไฟล์ใน `Autoexecute/` แล้วรันเองเมื่อเข้าเกม

### T3 — รีเกม Delta inject Lua เอง ✅ ผ่าน
- `am force-stop com.roblox.client` → เปิดใหม่ผ่าน deep link (ไม่แตะ Delta)
- autoexec รันเองอัตโนมัติ (log + GUI ขึ้น) → Delta inject Lua เองได้
- **ผลกระทบดี:** ไม่ต้องให้ APK trigger inject แยก สถาปัตยกรรมเดิมใช้ได้

### T4 — Lua ไฟล์ + localhost HTTP
**ไฟล์ ✅ ผ่าน**
- `writefile(rel)` / `readfile` / `isfile` ทำงาน — workspace = `Delta/Workspace/`
- `writefile(abs)` ❌ (`failed to read file`) → **ต้องใช้ relative path เท่านั้น**

**HTTP — ผลชัด (เทสต์ตอนเข้าแมพจริง):**
| ปลายทาง | ผล |
|---|---|
| `https://httpbin.org/post` | ✅ OK (405 = เชื่อมได้) |
| `http://httpbin.org/post` | ✅ OK (405) |
| `http://example.com/` | ✅ OK 200 |
| `http://127.0.0.1:8787` (loopback) | ❌ ConnectFail |
| `http://192.168.96.160:8790` (self-IP ap0) | ❌ ConnectFail |
| `http://10.79.67.100:8790` (self-IP ccmni2) | ❌ ConnectFail |

- **สรุป:** ออก **HTTP/HTTPS ภายนอกได้** (ทั้ง cleartext และ TLS)
  แต่ **ยิง localhost/self-IP (LAN) ไม่ได้** — executor บล็อก/ไม่รองรับ
- ยืนยันว่าไม่ใช่ปัญหา listener: `nc` จาก shell ไป `127.0.0.1:8787` ได้ (`NC_OK`)

### ⚠️ ข้อสรุปเปลี่ยนสถาปัตยกรรม
**"Lua → APK ผ่าน localhost HTTP" (หัวใจของแผนข้อ 3–4) ใช้ไม่ได้กับ Delta**
→ ต้องใช้ **ทางถอย = file-based IPC**: Lua เขียน state ลง `Delta/Workspace/lua_state.json`
  แล้ว APK อ่านไฟล์ (writefile/readfile พิสูจน์แล้วว่าทำงาน)
- หรือทางเลือก: Lua ยิงเว็บตรงด้วย HTTPS (external ผ่าน) แต่ต้องมีคีย์ในไฟล์ config
