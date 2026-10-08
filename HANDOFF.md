# HANDOFF — งานต่อไปสำหรับคนที่มารับช่วง

> อัปเดตล่าสุด: 2026-10-08 · commit `4bc4ea3`
> อ่านคู่กับ: `PLAN.md` (ดีไซน์), `CONTRACT.md` (สัญญา/DB), `PHASE0_RESULTS.md` (ผลเทสต์)

---

## 0. สรุปสั้น (TL;DR)

ระบบ **Auto-Rejoin** พิสูจน์แกนหลักครบแล้วบนเครื่องจริง:
**Lua เขียน state → agent อ่าน → watchdog ตัดสิน → สั่งรีเกมเอง → Lua กลับมา → armed**

- ✅ Phase 0 (สมมติฐาน) — ผ่านครบ (มี 1 การเปลี่ยนสถาปัตยกรรม: file-based IPC)
- ✅ Contract + DB schema — ร่างแล้ว
- ✅ Walking Skeleton — รันได้จริง
- ✅ Watchdog + auto-rejoin จริง — ผ่าน (13/13 unit tests + end-to-end บนเครื่อง)
- ⏭️ เหลือ: ทำ "ของจริง" ในเฟส 1 (auth, DB, APK Kotlin, alert, screenshot)

---

## 1. สถานะที่รันอยู่ตอนนี้ (และวิธีปิด)

| อย่าง | pid | คำสั่ง | หมายเหตุ |
|---|---|---|---|
| backend | 5903 | `.venv/bin/uvicorn skeleton.backend.app:app --host 0.0.0.0 --port 8000` | in-memory, หยุดแล้วข้อมูลหาย |
| agent | 5965 | `python3 -m skeleton.agent.agent ...` | **ยัง armed อยู่** กำลังเฝ้าเครื่อง |
| listener | 2535 | `python3 phase0/local_listener.py 8787` | ของเหลือจาก Phase 0 ไม่ใช้แล้ว |

ปิดทั้งหมด:
```bash
pkill -f "uvicorn skeleton.backend"; pkill -f "skeleton.agent.agent"; pkill -f local_listener
```
> ⚠️ **agent ยัง arm อยู่** — ถ้าทิ้งไว้แล้วเกมหลุด มันจะรีเกมเอง

---

## 2. Environment / วิธี setup ตั้งแต่ศูนย์

```bash
cd /home/film/Desktop/rejoin
# 1) adb (อยู่ใน .tools ไม่ขึ้น git)
.tools/platform-tools/adb connect 192.168.96.160:5555
.tools/platform-tools/adb devices          # ต้องเห็น device

# 2) python venv (ไม่ขึ้น git — ต้องสร้างใหม่)
python3 -m venv .venv
.venv/bin/pip install fastapi "uvicorn[standard]"

# 3) รันเทสต์
.venv/bin/python -m unittest discover -s skeleton/tests -v
```

**ยังไม่มีในเครื่องนี้ (ต้องติดตั้งถ้าจะทำต่อ):**
- Android SDK + Gradle (สำหรับ APK Kotlin จริง) — `ANDROID_HOME` ว่าง
- PostgreSQL, Redis, MinIO (สำหรับเฟส 1)
- มีแล้ว: Java 21, Node 24, Python 3.12

---

## 3. ข้อจำกัดที่พิสูจน์แล้ว (สำคัญมาก — อย่าลืม)

1. **Delta บล็อก HTTP ไป localhost/self-IP** (`ConnectFail`) แต่ยิงเน็ตภายนอกได้
   → สื่อสาร Lua→APK **ต้องใช้ไฟล์** (`Delta/Workspace/lua_state.json`)
2. **Lua `writefile` ใช้ได้แค่ relative path** — absolute path ล้มเหลว (`failed to read file`)
3. **Delta ไม่ใช่แอปแยก** — มีแค่ `com.roblox.client` (v2.740.931) ตัวเดียว
4. **Auto Execute ทำงานเอง** — วาง `rejoin_agent.lua` ใน `Delta/Autoexecute/` แล้วรันเอง (ไม่ต้องกด)
5. **ตอนรีเกม Delta inject Lua เอง** — ไม่ต้องให้ APK trigger แยก
6. **เน็ตคลาวโฟนช้ามาก** (ping 800–2000ms, เข้าเกม ~3 นาที) → timeout ต้องเผื่อเยอะ

---

## 4. งานต่อไป — เรียงตามลำดับความสำคัญ

### 🔴 P0 — แก้ก่อน (เจอจากการเทสต์จริง)
- [ ] **ยืด `rejoin_timeout`** จาก 90 → ~300 วิ
  - เหตุ: เน็ตช้า เกมโหลด 3 นาที → ตอนนี้ watchdog นับ fail ทั้งที่กำลังโหลด (false positive)
  - ที่แก้: `skeleton/agent/agent.py` (`--timeout`), `skeleton/agent/watchdog.py` (`Config.rejoin_timeout_sec`)
  - เพิ่มเทสต์: จำลองโหลดนาน > timeout ว่าต้องไม่ alert
- [ ] **แยก "กำลังโหลด" ออกจาก "ตาย"** — ใช้ state จาก Lua (`loading`/`menu`) ไม่ใช่แค่เวลา
  - Lua ควรเขียน `state` ให้ละเอียดขึ้น (ดูข้อ 5)
- [ ] **`adb reverse`/listener ของเก่า** — ลบทิ้งได้ ไม่ใช้ในดีไซน์ใหม่

### 🟠 P1 — เฟส 1 จริง: APK Kotlin (แทน agent.py)
- [ ] สร้าง Android project (Kotlin, Gradle) — ต้องติดตั้ง Android SDK ก่อน
- [ ] **Foreground Service** ทำงานตลอด (กัน Doze/ระบบฆ่า)
- [ ] ลงทะเบียนด้วยรหัสเครื่อง → ได้ device_token → เก็บใน **EncryptedSharedPreferences/Keystore**
- [ ] อ่าน `lua_state.json` (file watcher) → คำนวณความเงียบ
- [ ] ย้าย logic จาก `watchdog.py` เป็น Kotlin (พอร์ตตรงๆ ได้ — มันเป็น pure)
- [ ] สั่งรีเกมผ่าน root (`su -c am force-stop / am start`)
- [ ] ยัด Lua (atomic + backup) — พอร์ตจาก `device.py:push_lua`
- [ ] ส่ง heartbeat ไปเว็บ (OkHttp)
- [ ] Poll คำสั่ง arm/disarm/rejoin_now

### 🟠 P1 — Backend จริง (แทน in-memory)
- [ ] **Discord OAuth2** login (session cookie)
- [ ] **PostgreSQL** — ใช้ schema ใน `CONTRACT.md` (6 ตาราง)
- [ ] **Redis** — เก็บ `last_seen` (TTL) สำหรับ watchdog
- [ ] ออก/จัดการ **รหัสเครื่อง** (hash ด้วย Argon2/bcrypt — อย่าเก็บ plaintext)
- [ ] `/api/agent/register` ตรวจ device_code จริง (ตอนนี้รับมั่ว)
- [ ] revoke token
- [ ] ย้าย event log จาก memory → ตาราง `events`

### 🟡 P2 — ฟีเจอร์ใช้งานจริง
- [ ] แคปภาพหน้าจอ (root `screencap`) + ย่อ + JPEG → อัปขึ้น S3/MinIO + retention 7 วัน
- [ ] avatar/ตัวละคร/แมพ จาก Lua (มีแล้วบางส่วน — ทำ fallback)
- [ ] แจ้งเตือน LINE/Telegram/Discord webhook ตอน alert
- [ ] WebSocket อัปเดตแดชบอร์ดสด
- [ ] retry/backoff ที่ปรับตาม state (มีพื้นฐานแล้วใน watchdog)

### 🟢 P3 — ขยาย
- [ ] MQTT แทน polling
- [ ] auto-stop instance เมื่อกู้ไม่ได้นาน
- [ ] fallback OCR ถ้า Lua ดึงข้อมูลไม่ได้
- [ ] จัดการหลายเครื่องแบบกลุ่ม

---

## 5. สัญญาที่ต้องขยาย (Contract changes)

**Lua state ต้องละเอียดขึ้น** — ตอนนี้มีแค่ `in_game`:
```json
{
  "v": 1,
  "state": "in_game | loading | menu | unknown",
  "phase_detail": "joining | teleporting | lobby",
  "avatar": "...", "character": "...", "map": "...",
  "place_id": 0, "job_id": "...",
  "ts": 0
}
```
→ ให้ agent แยก "กำลังโหลด" (อย่ารีเกม) ออกจาก "ตาย" (รีเกม) ได้

**ยังไม่ตัดสิน:**
- realtime: ใช้ **ไฟล์อย่างเดียว** หรือ **ไฟล์ + Lua ยิงเว็บ HTTPS ตรง**?
  (ยิงเน็ตออกได้ ยืนยันแล้ว — แต่ต้องมีคีย์ใน config file)

---

## 6. กับดัก/บทเรียนที่เจอ

| เรื่อง | บทเรียน |
|---|---|
| `game:HttpGet` | วิ่งผ่านเซิร์ฟเวอร์ Roblox → ยิง localhost ไม่ได้ **ห้ามใช้** |
| `writefile` absolute | ล้มเหลว — ใช้ relative เท่านั้น |
| Delta autoexec | ไม่ต้องกด ทำงานเอง — อย่าไปสั่งซ้ำ |
| `adb reverse` | ใช้พิสูจน์ loopback ตอน Phase 0 เท่านั้น ไม่ใช้ในระบบจริง |
| เน็ตช้า | อย่าตั้ง timeout สั้น — เกมโหลด 3 นาที |
| `nc -l` บนเครื่อง | ใช้เป็น HTTP server ชั่วคราวได้ (toybox) แต่ไม่ต้องใช้แล้ว |
| GUI ยืนยัน | `gethui()` + ScreenGui ตัวนับวิ่ง = วิธีเช็ค autoexec ที่ดี |

---

## 7. แผนที่ repo

```
rejoin-cloud/
├── PLAN.md               # ดีไซน์หลัก (อัปเดตตาม Phase 0 แล้ว)
├── CONTRACT.md           # สัญญา Lua/APK/เว็บ + DB schema  ★อ่านก่อนโค้ด
├── HANDOFF.md            # ← ไฟล์นี้
├── PHASE0_CHECKLIST.md   # checklist เทสต์ Phase 0
├── PHASE0_RESULTS.md     # ผลเทสต์ Phase 0
├── phase0/               # สคริปต์ probe + listener (ของ Phase 0)
└── skeleton/
    ├── README.md         # วิธีรัน skeleton
    ├── lua/rejoin_agent.lua      # Lua เขียน state (autoexec)
    ├── agent/
    │   ├── watchdog.py           # ★ state machine (พอร์ตเป็น Kotlin ทีหลัง)
    │   ├── device.py             # adb actions
    │   └── agent.py              # orchestrator
    ├── tests/test_watchdog.py    # 13 tests
    └── backend/app.py            # FastAPI + dashboard (in-memory)
```

**ไม่ขึ้น git (ตาม `.gitignore`):** `.venv/`, `.tools/`, `phase0/artifacts/`, `*.png`, `*.apk`

---

## 8. วิธีทดสอบ auto-rejoin (ทำซ้ำได้)

```bash
# 1) เปิด backend
.venv/bin/uvicorn skeleton.backend.app:app --host 0.0.0.0 --port 8000

# 2) รัน agent (background)
.venv/bin/python -m skeleton.agent.agent \
  --adb .tools/platform-tools/adb --device 192.168.96.160:5555 \
  --server http://127.0.0.1:8000 --code DEMO-0001 --place 107778070777162

# 3) สั่ง arm ผ่าน API (จำลองกดปุ่มบนเว็บ)
curl -X POST http://127.0.0.1:8000/api/device/dev_1/arm

# 4) ฆ่าเก่าเพื่อจำลองหลุด
.tools/platform-tools/adb shell su -c "am force-stop com.roblox.client"

# 5) เฝ้าดู log: ควรเห็น phase เปลี่ยน connected -> rejoining -> armed
#    และ rejoin_count เพิ่ม
curl http://127.0.0.1:8000/api/me/devices
```
> รอเกมโหลดได้ถึง 3 นาที (เน็ตช้า) — อย่าใจร้อน

---

## 9. การตัดสินใจที่ค้างอยู่ (ต้องถามเจ้าของงาน)

1. realtime: **ไฟล์อย่างเดียว** หรือ **+ HTTPS ตรง**? (มีผลกับคีย์)
2. timeout ที่เหมาะกับเน็ตช้า: 300 วิ? หรือปรับตาม state?
3. เลือก tech stack จริง: FastAPI (ตามแผน) หรือ NestJS?
4. แจ้งเตือนช่องไหนก่อน: LINE / Telegram / Discord?
5. APK: build บนเครื่องนี้ (ต้องโหลด SDK ~ใหญ่) หรือ CI?

---

## 10. กติกาเขียนโค้ด (ตามของเดิม)

- Python: type hints, docstring ไทย/อังกฤษปนได้, แยก pure logic ออกจาก I/O
- **watchdog ต้องเป็น pure เสมอ** (รับ `now` เข้า ไม่เรียกเวลาจริง) → เทสต์ได้
- เอกสาร/คอมเมนต์ใช้ไทยได้ตามบริบทโปรเจกต์
- commit message: บรรทัดแรกสั้น + body อธิบาย (ดู `git log`)
