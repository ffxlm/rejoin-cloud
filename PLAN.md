# แผนระบบ Auto-Rejoin สำหรับฟาร์มเกมบนคลาวโฟน

> เอกสารออกแบบ (Design Document) — รวบรวมสถาปัตยกรรม, การไหลของข้อมูล, data model,
> API, สถานะ, ความปลอดภัย และแผนพัฒนาเป็นเฟส

> **สถานะ: Phase 0 เสร็จแล้ว** — สมมติฐานหลักผ่านครบ แต่มี **1 การเปลี่ยนสถาปัตยกรรม**:
> ช่องทาง Lua → APK เปลี่ยนจาก *localhost HTTP* เป็น **file-based IPC**
> เพราะ Delta บล็อกการยิง loopback/LAN (รายละเอียดข้อ 4.1 และ `PHASE0_RESULTS.md`)

---

## 1. ปัญหาและเป้าหมาย

### ปัญหา
คนฟาร์มปล่อยบอท (ตัวรัน delta + Lua) ทิ้งไว้บนคลาวโฟน 24/7 แต่ **เกมมักหลุด/ค้าง/ดับโดยที่เจ้าของไม่รู้**
ทำให้เสียเวลาและเสียค่าเช่าคลาวโฟนไปเปล่าๆ

### เป้าหมาย
- ตรวจจับได้อัตโนมัติว่าเกมหลุด/ค้าง/ดับ
- กู้กลับเข้าเกม/เข้าแมพโดยอัตโนมัติ (auto-rejoin)
- แจ้งเตือนและโชว์สถานะให้เจ้าของเห็นบนเว็บ
- ใช้งานง่ายแบบ self-service: คนทั่วไปทำได้โดยไม่ต้องใช้คำสั่ง Termux
- รองรับผู้ใช้ 1 คนหลายเครื่อง/หลายไอดี

---

## 2. ภาพรวมสถาปัตยกรรม

```
┌── คลาวโฟน (เปิด root) ──────────────────────────────┐
│                                                       │
│   [เกม]                                               │
│   [Delta + Lua ตัวรัน]  ──ส่งข้อมูล/สัญญาณ──► [APK]   │
│   [APK Rejoin Agent]                                  │
│        │ ยัด Lua / เปิดเกม / รีเกม                  │
└────────┼──────────────────────────────────────────────┘
         │ APK แนบ "รหัสเครื่อง" ส่งไปเว็บ
         ▼
   [เว็บ + DB + Storage]  ──►  แดชบอร์ดของเจ้าของ
```

### องค์ประกอบหลัก 4 ชิ้น

| ชิ้น | ที่อยู่ | หน้าที่ |
|---|---|---|
| **Lua** | ในเกม (Delta/Autoexecute) | รันสคริปต์ + ส่ง avatar/ตัวละคร/แมพ + สัญญาณ "ยังอยู่" ให้ APK (ผ่านไฟล์) |
| **APK Agent** | บนคลาวโฟน | อ่าน state จาก Lua → เติมรหัสเครื่อง → ส่งเว็บ / เฝ้าเกม / รีเกม / ยัด Lua |
| **เว็บ** | เซิร์ฟเวอร์ | ล็อกอิน Discord, ออก/จัดการรหัสเครื่อง, แดชบอร์ด, ปุ่มเริ่ม auto-rejoin |
| **DB + Storage** | เซิร์ฟเวอร์ | เก็บ user, เครื่อง, สถานะ, ประวัติ rejoin |

---

## 3. หลักการทำงานหัวใจ (Watchdog)

### หลักคิด: เฝ้า "ความเงียบ" ไม่ใช่รอให้ Lua บอกว่าตาย

เพราะเวลาเกมหลุด **Lua มักตายไปพร้อมเกม** — มันแจ้งไม่ได้
การเฝ้าความเงียบ (dead-man's switch) จึงจับได้ทุกกรณี:
เกมดับ / เกมค้าง / ตัวรันแฮงก์ / เน็ตหลุด

```
Lua ──เขียนไฟล์ lua_state.json ทุก 10 วิ──► Delta/Workspace/
                                             │
                                    APK อ่านไฟล์, ts เก่าเกิน 60 วิ?
                                             │
                                     ใช่ ──► APK สั่งเปิดเกม + เปิด Delta ใหม่
```

### ทำไม APK ต้องรับจาก Lua แบบ local (ไม่พึ่งเน็ต)
- **ไม่พึ่งเน็ต**: แม้เน็ตคลาวโฟนหลุด APK ยังรู้ในเครื่องว่า Lua ยังทำงานไหม → ตัดสินใจรีเกมถูกต้อง
- **Lua ไม่ต้องมีรหัส**: รหัสอยู่ที่ APK ที่เดียว

> **อัปเดตจากผลเทสต์ Phase 0 (สำคัญ):** Delta **บล็อกการยิง localhost/self-IP HTTP**
> (ทดสอบแล้ว `127.0.0.1` และ IP ในเครื่องเอง → `ConnectFail` ทั้งหมด)
> ขณะที่ยิง HTTP/HTTPS **ออกเน็ตภายนอกได้ปกติ**
> → ช่องทาง Lua → APK จึงเปลี่ยนจาก "local HTTP server" เป็น **file-based IPC**
> (Lua เขียนไฟล์ state ลง `Delta/Workspace/` แล้ว APK อ่าน) รายละเอียดข้อ 4.1

### ชั้นป้องกันที่ 2: APK → เว็บ
APK ส่ง heartbeat ไปเว็บด้วย ถ้าเว็บไม่ได้ยิน APK = APK ตาย/เครื่องดับ → เว็บแจ้งเตือนคน

---

## 4. การไหลของข้อมูล

### 4.1 Lua → APK (file-based IPC — เปลี่ยนจาก localhost HTTP)
- **เหตุผลที่เปลี่ยน:** Delta ไม่ให้ Lua ยิง HTTP ไป `127.0.0.1`/self-IP (ConnectFail) — พิสูจน์ใน Phase 0
- **ช่องทาง:** Lua เขียนไฟล์ state ลง workspace ของ executor
  - path: `Delta/Workspace/lua_state.json` (**relative path เท่านั้น** — absolute write ล้มเหลว)
  - `writefile` / `readfile` / `isfile` ทำงานได้จริง (ยืนยันแล้ว)
- Lua เขียนไฟล์นี้ซ้ำทุก 10 วิ (heartbeat + state)
- APK อ่านไฟล์ทุก X วิ → เทียบ `ts` กับเวลาปัจจุบัน → ตัดสินความเงียบ

```json
{
  "state": "in_game",
  "avatar": "ชื่อ/รูปตัวละคร",
  "character": "ชื่อตัวละคร",
  "map": "ชื่อ/รหัสแมพ",
  "ts": 1730000000
}
```

- **atomic write ฝั่ง Lua:** เขียน `lua_state.tmp` → `rename` ทับ `lua_state.json` กัน APK อ่านไฟล์ครึ่งๆ กลางๆ
- **ทางเลือกเสริม (ถ้าต้องการ realtime):** Lua ยิงเว็บตรงด้วย **HTTPS** (external ผ่าน — ยืนยันแล้ว)
  แต่ต้องมีคีย์ในไฟล์ config แยก (ไม่ฝังในโค้ด Lua)

### 4.2 APK → เว็บ
- แนบรหัสเครื่อง (device token) ใน header
- ส่ง: สถานะเครื่อง, สถานะเกม, ข้อมูลจาก Lua

```
POST /api/agent/heartbeat
Authorization: Bearer <device_token>
{
  "state": "armed",
  "game_running": true,
  "lua_active": true,
  "avatar": "...",
  "character": "...",
  "map": "...",
  "rejoin_count": 3,
  "session_start": 1730000000
}
```

### 4.3 เว็บ → APK (คำสั่ง)
- APK poll `GET /api/device/:id/command` ทุก M วินาที หรือใช้ MQTT push
- คำสั่ง: `arm` (เริ่ม auto-rejoin), `disarm`, `rejoin_now`, `stop`, `update_lua`

---

## 5. สถานะ (State Machine)

```
offline → connected → game_running → lua_active → armed
                                         │           │
                                         └─ พร้อมกด Start ─┘
armed + heartbeat ขาด → rejoining → (กลับได้ → armed / ไม่ได้ → alert)
```

| สถานะ | ความหมาย |
|---|---|
| `offline` | APK ไม่ได้เชื่อมต่อเว็บ |
| `connected` | APK เชื่อมแล้ว ยังไม่เจอเกม |
| `game_running` | ตรวจเจอโปรเซสเกม |
| `lua_active` | ได้ heartbeat จาก Lua (มี avatar/ตัวละคร/แมพ) |
| `armed` | ผู้ใช้กด "เริ่ม auto-rejoin" แล้ว → ระบบเฝ้าเต็มตัว |
| `rejoining` | กำลังกู้เกม |
| `alert` | กู้ไม่ได้ ต้องให้คนดู |

**"พร้อมแล้ว"** = `game_running` **และ** `lua_active`
→ ปุ่ม "เริ่ม auto-rejoin" enable เมื่อสถานะ = `lua_active`

---

## 6. การไหลตอนเกมหลุด (อัตโนมัติ 100%)

```
1. เกมหลุด → Lua เงียบ
2. APK จับได้ (เงียบเกิน 60 วิ)
3. APK สั่งเปิดเกมใหม่ + เปิด Delta
4. Delta inject Lua จาก Autoexecute อัตโนมัติ
5. Lua รันใหม่ → ส่ง heartbeat กลับ
6. APK รายงานเว็บ → +1 rejoin, อัปเดตเวลา
7. ถ้ากู้ไม่ได้ → retry/backoff → แจ้งเตือน (LINE/Telegram/Discord)
```

**เงื่อนไข retry:** จำกัดจำนวนครั้ง + backoff กัน rejoin storm (เช่น 3 ครั้ง ห่างกัน 30 วิ → 1 นาที → 2 นาที)

---

## 7. การติดตั้ง Lua และ config

### 7.1 ตำแหน่งโฟลเดอร์
```
/storage/emulated/0/Delta/Autoexecute/   ← path หลัก
/sdcard/Delta/Autoexecute/                ← alias (ชี้ที่เดียวกัน)
```

การค้นหา (robust):
- ลอง `/storage/emulated/0/...` ก่อน → fallback `/sdcard/...`
- ทนตัวพิมพ์: เช็คทั้ง `Autoexecute` / `AutoExecute`
- ถ้าหาไม่เจอ → ให้ผู้ใช้ตั้ง path เองได้ในหน้า APK

### 7.2 หลักการติดตั้ง Lua
- **Lua ไม่ฝังใน APK** → APK ดาวน์โหลด Lua จากเว็บตอนรัน (ใช้ device_token) → แก้ Lua ที่เว็บได้ทันที
- ชื่อไฟล์เฉพาะของเรา: `rejoin_agent.lua` (ไม่ทับไฟล์ลูกค้า)
- **atomic write**: เขียน `.tmp` → rename ทับ
- **backup** ไฟล์เดิมก่อนทุกครั้ง (`.bak`)
- **ยืนยันด้วย heartbeat** ไม่ใช่แค่ "เขียนสำเร็จ"

### 7.3 เรื่องคีย์
- **Lua ไม่มีคีย์** → สื่อสารผ่านไฟล์ใน workspace → APK เติมรหัสให้
- ถ้าจำเป็นให้ Lua ยิงเว็บตรง (HTTPS) → ใช้ **ไฟล์ config แยก** (ไม่ฝังในโค้ด Lua) เพื่อให้เปลี่ยนคีย์ได้ง่าย
- ทางที่แนะนำที่สุด: **Lua ไม่มีคีย์เลย**

### 7.4 สิ่งที่ต้องเทสต์กับ Delta จริงก่อนปิดงาน
1. สวิตช์ **Auto Execute** ใน Delta เปิดอยู่หรือไม่ (ถ้าปิด ยัดไฟล์ไปก็ไม่รัน)
2. ตอนรีเกม **Delta inject Lua เองได้หรือไม่** (ถ้าไม่ได้ ต้องให้ APK ช่วย trigger)

---

## 8. บัญชีและความปลอดภัย

### 8.1 รหัส 2 ระดับ

| รหัส | ได้มาจาก | user เห็นไหม | ใช้ทำอะไร |
|---|---|---|---|
| **รหัสผู้ใช้** (session) | ล็อกอิน Discord อัตโนมัติ | ❌ ไม่เห็น (อยู่ในคุกกี้) | เข้าเว็บ ดูแดชบอร์ด |
| **รหัสเครื่อง** (device code) | กด "เพิ่มเครื่อง" ในเว็บ | ✅ เห็น | กรอกใน APK |

### 8.2 กฎความปลอดภัย
- เก็บรหัสเครื่องฝั่งเซิร์ฟเวอร์เป็น **hash** (Argon2/bcrypt) ไม่เก็บ plaintext
- เปลี่ยน/เพิกถอน (revoke) รหัสเครื่องได้
- แนะนำ: รหัสเครื่องใช้ "ลงทะเบียน" ครั้งแรก → APK ได้ **device_token** แยกต่อเครื่อง
- ฝั่ง APK เก็บ token ใน **EncryptedSharedPreferences / Android Keystore**
- ห้ามใช้ `device_id` เฉยๆ แทนรหัส (ปลอมได้)
- ห้ามแยกผู้ใช้ด้วย IP (คลาวโฟนออกเน็ต NAT IP เดียวกัน)

### 8.3 1 คน หลายเครื่อง
```
ผู้ใช้ ──รหัสผู้ใช้──► ล็อกอินเว็บ, ดูแดชบอร์ด
   ├─ เครื่อง A ──รหัสเครื่อง A──► กรอกใน APK A
   ├─ เครื่อง B ──รหัสเครื่อง B──► กรอกใน APK B
   └─ เครื่อง C ──รหัสเครื่อง C──► กรอกใน APK C
```

---

## 9. Data Model

| ตาราง | ฟิลด์สำคัญ |
|---|---|
| `users` | id, discord_id, username, avatar, created_at |
| `devices` | id, user_id, name, game_pkg, status, last_seen, armed_at, rejoin_count, session_start, lua_version |
| `device_tokens` | id, device_id, token_hash, created_at, revoked_at |
| `device_state` | device_id, avatar, character, map, updated_at (จาก Lua) |
| `events` | device_id, type (connect/rejoin/alert/arm), detail, ts |

**หมายเหตุ:**
- `runtime` และ `rejoin_count` คำนวณจาก `events` + `armed_at` (ไม่เก็บซ้ำ กันข้อมูลเพี้ยน)
- `last_seen` เก็บเร็วๆ ใน Redis (TTL) สำหรับ watchdog

---

## 10. API หลัก

```
# Auth
GET  /auth/discord                    → เริ่ม OAuth
GET  /auth/discord/callback           → รับ callback, สร้าง session

# ผู้ใช้ / แดชบอร์ด
GET  /api/me                          → ข้อมูลผู้ใช้
GET  /api/me/devices                  → รายการเครื่อง + สถานะ
POST /api/me/devices                  → เพิ่มเครื่อง → ออกรหัสเครื่อง
DELETE /api/me/devices/:id            → ลบเครื่อง / revoke รหัส
GET  /api/download/apk                → ดาวน์โหลด APK
GET  /api/download/lua?device=..      → ดาวน์โหลด Lua (เฉพาะเครื่อง)

# APK / Agent
POST /api/agent/register              → ลงทะเบียนด้วยรหัสเครื่อง → device_token
POST /api/agent/heartbeat             → ส่งสถานะ (ทุก N วิ)
GET  /api/device/:id/command          → APK poll คำสั่ง
POST /api/device/:id/arm              → กดเริ่ม auto-rejoin
POST /api/device/:id/disarm           → หยุด auto-rejoin
```

---

## 11. แดชบอร์ด (สิ่งที่แสดง)

ต่อ 1 เครื่อง (การ์ด):
- สถานะ (🟢 armed / 🟡 lua_active / 🔴 offline-alert)
- รันมาแล้วกี่นาที (จาก `session_start`)
- rejoin กี่ครั้ง (`rejoin_count`)
- avatar, ตัวละคร, แมพ (จาก Lua)
- ปุ่ม: เริ่ม/หยุด auto-rejoin, rejoin ทันที, ดูประวัติ

ระดับผู้ใช้:
- จัดกลุ่มเครื่องทั้งหมดของผู้ใช้
- ปุ่ม "เพิ่มเครื่อง"
- ภาพรวม: กี่เครื่องออนไลน์/หลุด/แจ้งเตือน

Realtime: อัปเดตสถานะสดด้วย WebSocket

---

## 12. สแตกเทคโนโลยี

| ชิ้น | เทคโนโลยี |
|---|---|
| Auth | Discord OAuth2 |
| Backend | FastAPI (Python) หรือ NestJS (Node) |
| DB | PostgreSQL + Redis (last_seen TTL / คิวคำสั่ง) |
| Realtime | WebSocket |
| APK | Kotlin + Foreground Service + root + **file watcher** (อ่าน lua_state.json) + OkHttp |
| Lua | ตัวรันเดิม + ส่ง heartbeat/state → APK |
| แจ้งเตือน | LINE / Telegram / Discord webhook |
| Infra | Docker + docker-compose บน VPS |

### สิทธิ์ที่ APK ต้องใช้
| งาน | root | ไม่ root |
|---|---|---|
| เปิด/รีเกม | ✅ `su -c am start` | ⚠️ Intent + SYSTEM_ALERT_WINDOW |
| เขียน `Delta/Autoexecute` | ✅ | ⚠️ Android 11+ ต้อง MANAGE_EXTERNAL_STORAGE |
| เช็คเกมยังรัน | ✅ อ่าน process | ⚠️ UsageStatsManager |
| กดปุ่มในเกม | ✅ `input tap` | ⚠️ AccessibilityService |

→ **แนะนำใช้ root** เพราะคลาวโฟนส่วนใหญ่เปิดได้ และเลี่ยงปัญหาสิทธิ์ทั้งหมด

---

## 13. ขั้นตอนการใช้ (สำหรับลูกค้า)

**ครั้งแรก (ทำครั้งเดียว)**
1. เข้าเว็บ → ล็อกอินด้วย Discord → เข้าแดชบอร์ด (ไม่ต้องจำรหัส)
2. กด "เพิ่มเครื่อง" → ได้รหัสเครื่อง + ปุ่มโหลด APK
3. ติดตั้ง APK บนคลาวโฟน → กรอกรหัสเครื่อง → กด Start
4. APK เชื่อมต่อเว็บสำเร็จ

**เริ่มใช้งาน**
5. กดปุ่มใน APK → ยัด Lua ลง `Delta/Autoexecute` อัตโนมัติ + เปิดเกม + เปิด Delta
6. รอสักครู่ → เว็บขึ้น "พร้อม"
7. กด "เริ่ม auto-rejoin" บนเว็บ → ระบบเฝ้า 🟢

**ระหว่างใช้** — แดชบอร์ดโชว์สถานะสด, runtime, rejoin count, avatar, ตัวละคร, แมพ

---

## 14. แผนพัฒนาเป็นเฟส

### เฟส 0 — เทสต์สมมติฐาน (สำคัญสุด) ✅ เสร็จแล้ว
- [x] ยืนยัน path `Delta/Autoexecute` ใช้งานได้จริง → **ผ่าน** (`/storage/emulated/0/Delta/Autoexecute`)
- [x] ยืนยันสวิตช์ Auto Execute ใน Delta เปิดแล้วรัน Lua อัตโนมัติ → **ผ่าน** (GUI ตัวนับวิ่งเอง)
- [x] ยืนยันตอนรีเกม Delta inject Lua เองได้ → **ผ่าน** (force-stop → เปิดใหม่ → รันเอง)
- [x] ยืนยันช่องทาง Lua → APK → **เปลี่ยนเป็น file-based IPC** (localhost HTTP ถูกบล็อก)
- [x] ยืนยัน `writefile`/`readfile` ได้ แต่ **ต้องใช้ relative path**

> รายละเอียดผลเทสต์ทั้งหมด: `PHASE0_RESULTS.md`, checklist: `PHASE0_CHECKLIST.md`

### เฟส 1 — MVP (เฟสเดียว)
- [ ] Backend: Discord login, เพิ่มเครื่อง, ออก/เก็บรหัสเครื่อง (hash)
- [ ] Backend: API รับ heartbeat, เก็บสถานะ, watchdog (Redis TTL)
- [ ] APK: ใส่รหัสเครื่อง, register, foreground service, heartbeat ไปเว็บ
- [ ] APK: ยัด Lua ลง Delta/Autoexecute (atomic + backup)
- [ ] Lua template: ส่ง heartbeat/state → APK
- [ ] APK: เฝ้าความเงียบ Lua → เปิดเกม/Delta ใหม่
- [ ] แดชบอร์ดพื้นฐาน: สถานะ + ปุ่มเริ่ม auto-rejoin

### เฟส 2 — ใช้งานจริง
- [ ] avatar/ตัวละคร/แมพ จาก Lua
- [ ] ประวัติ rejoin + นับครั้ง
- [ ] แจ้งเตือน LINE/Telegram/Discord
- [ ] WebSocket อัปเดตสด
- [ ] retry/backoff ตอนกู้ไม่ได้

### เฟส 3 — ขยาย
- [ ] MQTT แทน polling (สเกลหลายร้อยเครื่อง)
- [ ] auto-stop instance เมื่อกู้ไม่ได้นาน (ประหยัดค่าเช่า)
- [ ] fallback OCR ถ้า Lua ดึง avatar/ตัวละครไม่ได้
- [ ] จัดการหลายเครื่องแบบกลุ่ม

---

## 15. ความเสี่ยง

| ความเสี่ยง | รายละเอียด | แนวทางลด |
|---|---|---|
| ToS ของเกม/คลาวโฟน | auto + adb อาจผิดข้อตกลง | ศึกษาก่อน, ใช้ความระวัง |
| ความปลอดภัย adb | ห้ามเปิดพอร์ต adb เปล่า | ใช้ root ในเครื่องแทน adb |
| false positive | rejoin ตอนกำลังโหลด | timeout ตาม state + backoff |
| APK ถูกระบบฆ่า | Doze/battery | Foreground Service + keep-alive + heartbeat ไปเว็บ |
| Lua อ่านไฟล์/ยิง localhost ไม่ได้ | Delta **บล็อก loopback/LAN HTTP** (พิสูจน์แล้ว) แต่ยิงเน็ตออกได้ | ใช้ file-based IPC (เขียน state ลง workspace) — ยืนยันแล้วว่าทำงาน |
| เกม anti-cheat | ตรวจ root/Accessibility | เทสต์กับเกมจริง |

---

## 16. สรุปประโยคเดียว

> **Lua ส่งข้อมูลให้ APK → APK เติมรหัสเครื่องแล้วส่งเว็บ → เว็บโชว์แดชบอร์ดของเจ้าของรหัสนั้น
> และ APK เฝ้าความเงียบของ Lua เพื่อรีเกมเองโดยไม่พึ่งเน็ต**

---

## 17. ผลเทสต์ Phase 0 (สรุป — รายละเอียดใน `PHASE0_RESULTS.md`)

### เครื่องทดสอบ
| รายการ | ค่า |
|---|---|
| รุ่น / Android | Realme RMX3201 / Android 11 (arm64-v8a) |
| root | ✅ Magisk |
| เกม+executor | `com.roblox.client` (Delta v2.740.931) — **package เดียว** |
| path | `/storage/emulated/0/Delta/Autoexecute` (relative workspace: `Delta/Workspace`) |

### ข้อที่ยืนยันแล้ว
- **T1** path `Delta/Autoexecute` ใช้งานได้ ✅
- **T2** Auto Execute รัน Lua อัตโนมัติ ✅ (ยืนยันด้วย GUI ตัวนับวิ่ง)
- **T3** รีเกม Delta inject Lua เองได้ ✅
- **T4a** `writefile`/`readfile`/`isfile` ได้ ✅ แต่ **absolute path ไม่ได้ → ใช้ relative เท่านั้น**
- **T4b** HTTP: ยิง **ภายนอกได้** (ทั้ง http/https) แต่ยิง **localhost/self-IP ไม่ได้** (ConnectFail)

### สิ่งที่ต้องเปลี่ยนเพราะผลเทสต์
1. **Lua → APK**: localhost HTTP ❌ → **file-based IPC** ✅ (ข้อ 4.1)
2. **Delta ไม่ใช่แอปแยก** — เปิดแค่ `com.roblox.client` ตัวเดียว ไม่มีแอป Delta ให้สลับ
3. **`writefile` ต้อง relative path** เสมอ

### ยังค้าง (ทำในเฟสถัดไป)
- จำลอง "เกมค้าง/หลุดกลางทาง" จริง (Phase 0 เทสต์แค่ force-stop)
- ฝั่ง APK อ่านไฟล์ state ได้จริง (ยังไม่มี APK → อยู่ใน Walking Skeleton)
