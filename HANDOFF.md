# HANDOFF — งานต่อไปสำหรับคนที่มารับช่วง

> อัปเดตล่าสุด: 2026-10-09 (เอาระบบแคปภาพหน้าจอออกทั้งวงจร)
> อ่านคู่กับ: `PLAN.md` (ดีไซน์), `CONTRACT.md` (สัญญา/DB), `PHASE0_RESULTS.md` (ผลเทสต์)

---

## 0. สรุปสั้น (TL;DR)

ระบบ **Auto-Rejoin** พิสูจน์แกนหลักครบแล้วบนเครื่องจริง:
**Lua เขียน state → agent อ่าน → watchdog ตัดสิน → สั่งรีเกมเอง → Lua กลับมา → armed**

- ✅ Phase 0 (สมมติฐาน) — ผ่านครบ (มี 1 การเปลี่ยนสถาปัตยกรรม: file-based IPC)
- ✅ Contract + DB schema — ร่างแล้ว
- ✅ Walking Skeleton — รันได้จริง
- ✅ Watchdog + auto-rejoin จริง — ผ่าน (13/13 unit tests + end-to-end บนเครื่อง)
- ✅ **Backend จริง (P1)** — Postgres/Redis + Discord OAuth + รหัสเครื่อง hash (24 tests ผ่าน)
- ✅ **APK Kotlin สเกเลตัน** — build บน GitHub Actions + ติดตั้ง/รันจริงบนเครื่องแล้ว (UI + Foreground Service)
- ✅ **APK ทำงานจริงแล้ว** — พอร์ต agent.py → Kotlin ครบ (register/Lua/watchdog/root rejoin)
  ทดสอบ end-to-end ผ่าน **public HTTPS** (ข้ามเน็ตจริง) สำเร็จ: arm → เปิดเกมเอง → armed
- ✅ **Deploy stack** — Dockerfile + compose (app/pg/redis/Caddy HTTPS) + `DEPLOY.md` พร้อมขึ้น VPS
- ❌ **เอาระบบแคปภาพหน้าจอ (screenshot) ออกทั้งวงจร** — APK/เว็บ/แดชบอร์ด/เอกสาร
- ⏭️ เหลือ: deploy จริงบน VPS + Discord OAuth จริง + P2 ที่เหลือ (alert/WebSocket)

---

## 1. สถานะที่รันอยู่ตอนนี้ (และวิธีปิด)

| อย่าง | pid | คำสั่ง | หมายเหตุ |
|---|---|---|---|
| backend | 10084 | `.venv/bin/uvicorn skeleton.backend.app:app --host 0.0.0.0 --port 8000` | **backend จริง** (dev: SQLite `rejoin.db` + fakeredis) |
| agent | 10144 | `python3 -m skeleton.agent.agent ...` | **ยัง armed อยู่** กำลังเฝ้าเครื่อง (รหัสเครื่องออกจากเว็บ) |

ปิดทั้งหมด:
```bash
pkill -f "uvicorn skeleton.backend"; pkill -f "skeleton.agent.agent"; pkill -f local_listener
```
> ⚠️ **agent ยัง arm อยู่** — ถ้าทิ้งไว้แล้วเกมหลุด มันจะรีเกมเอง
> ℹ️ หลังเปลี่ยน backend: รหัสเครื่องเก่า (`DEMO-0001`) ใช้ไม่ได้แล้ว — ต้องกด "เพิ่มเครื่อง"
>    ในเว็บเพื่อเอารหัสใหม่ (RJ-XXXXX-XXXXX) แล้วรัน agent ด้วย `--code` นั้น

---

## 2. Environment / วิธี setup ตั้งแต่ศูนย์

```bash
cd /home/film/Desktop/rejoin
# 1) adb (อยู่ใน .tools ไม่ขึ้น git)
.tools/platform-tools/adb connect 192.168.96.160:5555
.tools/platform-tools/adb devices          # ต้องเห็น device

# 2) python venv (ไม่ขึ้น git — ต้องสร้างใหม่)
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

# 3) รันเทสต์
.venv/bin/python -m unittest discover -s skeleton/tests -v
```

**ยังไม่มีในเครื่องนี้ (ต้องติดตั้งถ้าจะทำต่อ):**
- Android SDK + Gradle (สำหรับ APK Kotlin จริง) — `ANDROID_HOME` ว่าง
- PostgreSQL, Redis (สำหรับเฟส 1)
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
- [x] **ยืด `rejoin_timeout`** — default 90 → **300 วิ** และปรับได้ผ่าน `--timeout` / `Config.rejoin_timeout_sec`
  - หมายเหตุ: 300 คือค่ากันเน็ตช้า/เกมโหลดนาน (ค่า default) — เน็ตคลาวโฟนปกติลดได้
- [x] **แยก "กำลังโหลด" ออกจาก "ตาย"** — Lua เขียน `state` (`in_game`/`loading`) แล้ว; watchdog มี `Observation.lua_state` + `loading` property
  - ที่แก้: `skeleton/lua/rejoin_agent.lua` (`getState`), `skeleton/agent/watchdog.py`, `skeleton/agent/agent.py`
  - เทสต์: `TestSlowNetwork` 4 เคส (loading = alive, โหลดช้าทัน timeout ไม่ alert)
- [ ] **`adb reverse`/listener ของเก่า** — ลบทิ้งได้ ไม่ใช้ในดีไซน์ใหม่
  - ยังรันค้างอยู่: `phase0/local_listener.py` (pid 2535) — `pkill -f local_listener`
  - หมายเหตุ: ไฟล์ `phase0/` เก็บไว้เป็นหลักฐาน Phase 0 ก่อน (ลบโปรเซสได้ แต่ยังไม่ต้องลบไฟล์)

### 🟠 P1 — เฟส 1 จริง: APK Kotlin (แทน agent.py) — ✅ ทำงานจริงแล้ว (commit `2cf8ef1`)
- [x] สร้าง Android project (Kotlin, Gradle) — `android/` (AGP 8.5.2, Gradle 8.7, compileSdk 34)
- [x] **build บน GitHub Actions** (ไม่ต้องติดตั้ง Android SDK บนเครื่อง) — `.github/workflows/android.yml`
- [x] **ติดตั้ง + รันจริงบนเครื่อง**: UI ขึ้น, Foreground Service, กดเริ่ม/หยุดได้
- [x] **Foreground Service** ทำงานตลอด (กัน Doze/ระบบฆ่า) — `RejoinService`
- [x] หน้า UI กรอกรหัสเครื่อง + เซิร์ฟเวอร์ + placeId + สถานะ + log สด — `MainActivity`
- [x] เก็บ token เข้ารหัส — `Prefs` (EncryptedSharedPreferences/Keystore)
- [x] ลงทะเบียนด้วยรหัสเครื่อง → ได้ device_token — `Api.register`
- [x] ดึง Lua จากเว็บ (`GET /api/download/lua`) แล้วเขียนลง `Delta/Autoexecute` (atomic+backup) — `LuaInstaller`
- [x] อ่าน `lua_state.json` → คำนวณความเงียบ — `RootShell` + `LuaState`
- [x] watchdog state machine (พอร์ตจาก `watchdog.py`) — `Watchdog.kt` + 17 unit tests
- [x] สั่งรีเกมผ่าน root (`su -c am force-stop / am start`) — `RootShell`
- [x] ส่ง heartbeat ไปเว็บ (OkHttp) + รับคำสั่ง arm/disarm/rejoin_now — `Api`
- [x] **ทดสอบ end-to-end ผ่าน public HTTPS สำเร็จ** (register→Lua→arm→เปิดเกมเอง→armed)

### 🟠 P1 — Backend จริง (แทน in-memory) — ✅ เสร็จแล้ว (commit `68beb0b`)
- [x] **Discord OAuth2** login (session cookie) + `/auth/dev` สำหรับ dev
- [x] **Discord OAuth2 ตั้งค่าจริงแล้ว** — `.env` (Client ID/Secret) + โหลด `.env` อัตโนมัติ
      (python-dotenv) + จัดการ error เป็นภาษาไทย + โชว์ avatar จริง (6 เทสต์ใหม่)
- [x] **PostgreSQL** — 5 ตารางตาม `CONTRACT.md` (SQLAlchemy async; dev = SQLite)
- [x] **Redis** — เก็บ `last_seen` (TTL) + คิวคำสั่ง (dev = fakeredis)
- [x] ออก/จัดการ **รหัสเครื่อง** (Argon2 + lookup sha256 — ไม่เก็บ plaintext) + revoke
- [x] `/api/agent/register` ตรวจ device_code จริง (ไม่รับมั่วแล้ว)
- [x] ย้าย event log จาก memory → ตาราง `events`
- [x] แดชบอร์ด Jinja2 + ปุ่ม arm/disarm/rejoin_now + เพิ่มเครื่อง
- [x] **ระบบหลังบ้าน (admin)** — หน้า `/admin` (ภาพรวม + ผู้ใช้ + เครื่องทั้งหมด)
      ปุ่มในเมนูโชว์เฉพาะแอดมิน · ผู้ใช้คนแรกเป็นแอดมินอัตโนมัติ · จัดการสิทธิ์ผ่าน
      `python -m skeleton.backend.cli list|grant|revoke <discord_id>` (5 เทสต์ใหม่)
- [x] **Deploy stack** — `deploy/` (Dockerfile + compose app/pg/redis/Caddy) + `DEPLOY.md`
- [ ] deploy จริงบน VPS (ต้องมี VPS + โดเมนของคุณ)
- [ ] ยืนยัน Discord OAuth กับ app จริงบน production (ตั้ง `DISCORD_REDIRECT_URI=https://...` + `COOKIE_SECURE=true`)

### 🟡 P2 — ฟีเจอร์ใช้งานจริง
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
├── requirements.txt      # dependency ของ backend
├── .env.example          # ตัวอย่าง env (Postgres/Redis/Discord)
├── docker-compose.yml    # pg + redis (dev infra)
├── DEPLOY.md             # ★ คู่มือ deploy ขึ้น VPS (ใช้ได้ทั่วโลก)
├── deploy/               # ★ stack production
│   ├── Dockerfile
│   ├── docker-compose.yml  # app + postgres + redis + caddy(HTTPS)
│   ├── Caddyfile
│   └── .env.example
├── .github/workflows/
│   └── android.yml       # ★ CI: build APK บน GitHub Actions
├── android/              # ★ APK Kotlin (ทำงานจริง — ดู android/README.md)
│   └── app/src/main/java/com/rejoin/agent/
│       ├── MainActivity.kt     # UI กรอกรหัส + log สด
│       ├── RejoinService.kt    # Foreground Service → AgentLoop
│       ├── AgentLoop.kt        # orchestrator (register→Lua→เฝ้า→รีเกม)
│       ├── Watchdog.kt         # dead-man's switch (pure)
│       ├── RootShell.kt        # su -c (pidof/force-stop/launch/push Lua)
│       ├── Api.kt              # OkHttp (register/heartbeat/event/lua)
│       └── Prefs.kt            # EncryptedSharedPreferences
├── phase0/               # สคริปต์ probe + listener (ของ Phase 0)
└── skeleton/
    ├── README.md         # วิธีรัน skeleton
    ├── lua/rejoin_agent.lua      # Lua เขียน state (autoexec)
    ├── agent/
    │   ├── watchdog.py           # ★ state machine (พอร์ตเป็น Kotlin ทีหลัง)
    │   ├── device.py             # adb actions
    │   └── agent.py              # orchestrator
    ├── tests/
    │   ├── test_watchdog.py      # 17 tests (fake clock)
    │   └── test_backend.py       # tests (SQLite + fakeredis; event retention)
    └── backend/                  # ★ backend จริง (Phase 1)
        ├── app.py                # FastAPI + lifespan + แดชบอร์ด
        ├── config.py             # อ่าน env
        ├── db.py / models.py     # SQLAlchemy async + 5 ตาราง
        ├── security.py           # Argon2 + lookup sha256
        ├── redis_store.py        # last_seen TTL + คิวคำสั่ง
        ├── serializers.py        # view + status (dead-man's switch)
        ├── routers/              # auth / me / agent / device
        └── templates/            # login.html + dashboard.html
```

**ไม่ขึ้น git (ตาม `.gitignore`):** `.venv/`, `.tools/`, `phase0/artifacts/`, `*.png`, `*.apk`, `*.db`, `.env`

---

## 8. วิธีทดสอบ auto-rejoin (ทำซ้ำได้)

```bash
# 1) เปิด backend
.venv/bin/uvicorn skeleton.backend.app:app --host 0.0.0.0 --port 8000

# 2) รัน agent (background) — ใช้รหัสเครื่องที่ออกจากเว็บ (RJ-XXXXX-XXXXX)
.venv/bin/python -m skeleton.agent.agent \
  --adb .tools/platform-tools/adb --device 192.168.96.160:5555 \
  --server http://127.0.0.1:8000 --code RJ-XXXXX-XXXXX --place 107778070777162

# 3) สั่ง arm ผ่าน API (จำลองกดปุ่มบนเว็บ) — device id ดูจาก /api/me/devices
curl -X POST http://127.0.0.1:8000/api/device/1/arm

# 4) ฆ่าเก่าเพื่อจำลองหลุด
.tools/platform-tools/adb shell su -c "am force-stop com.roblox.client"

# 5) เฝ้าดู log: ควรเห็น phase เปลี่ยน connected -> rejoining -> armed
#    และ rejoin_count เพิ่ม
curl -b cookies.txt http://127.0.0.1:8000/api/me/devices
```
> รอเกมโหลดได้ถึง 3 นาที (เน็ตช้า) — อย่าใจร้อน

---

## 9. การตัดสินใจที่ค้างอยู่ (ต้องถามเจ้าของงาน)

1. realtime: **ไฟล์อย่างเดียว** หรือ **+ HTTPS ตรง**? (มีผลกับคีย์)
2. timeout ที่เหมาะกับเน็ตช้า: 300 วิ? หรือปรับตาม state?
3. ~~เลือก tech stack จริง: FastAPI (ตามแผน) หรือ NestJS?~~ → **เลือก FastAPI แล้ว**
4. แจ้งเตือนช่องไหนก่อน: LINE / Telegram / Discord?
5. ~~APK: build บนเครื่องนี้ หรือ CI?~~ → **เลือก build บน GitHub Actions แล้ว** (ไม่ต้องลง SDK ในเครื่อง)

---

## 10. กติกาเขียนโค้ด (ตามของเดิม)

- Python: type hints, docstring ไทย/อังกฤษปนได้, แยก pure logic ออกจาก I/O
- **watchdog ต้องเป็น pure เสมอ** (รับ `now` เข้า ไม่เรียกเวลาจริง) → เทสต์ได้
- เอกสาร/คอมเมนต์ใช้ไทยได้ตามบริบทโปรเจกต์
- commit message: บรรทัดแรกสั้น + body อธิบาย (ดู `git log`)
