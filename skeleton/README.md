# Walking Skeleton — Rejoin

เส้นทางบางที่สุดที่วิ่งครบทุกชั้น เพื่อพิสูจน์ loop หลักก่อนทำของจริง

```
Lua เขียน lua_state.json
   → agent อ่านไฟล์ (จำลอง APK) → watchdog ตัดสิน
   → REJOIN/LAUNCH → heartbeat + event → แดชบอร์ด
```

## โครงสร้าง
```
skeleton/
├── lua/rejoin_agent.lua        # Lua เขียน state ลง Delta/Workspace/lua_state.json ทุก 10 วิ
├── agent/
│   ├── watchdog.py             # ★ state machine (pure, testable) — หัวใจของระบบ
│   ├── device.py               # กระทำกับเครื่องผ่าน adb (force-stop/launch/push Lua)
│   └── agent.py                # orchestrator: device + watchdog + backend
├── agent_stub/agent_stub.py    # (เก่า) จำลอง APK แบบอ่านอย่างเดียว
├── tests/
│   ├── test_watchdog.py        # unit tests (fake clock)
│   └── test_backend.py         # เทสต์ backend (SQLite + fakeredis)
└── backend/                    # ★ Backend จริง (Phase 1)
    ├── app.py                  # FastAPI: สร้าง app, lifespan, แดชบอร์ด
    ├── config.py               # อ่าน env (Postgres/Redis/Discord)
    ├── db.py / models.py       # SQLAlchemy async + 5 ตาราง (CONTRACT §5)
    ├── security.py             # รหัสเครื่อง (Argon2 + lookup sha256)
    ├── redis_store.py          # last_seen TTL + คิวคำสั่ง (fakeredis ใน dev)
    ├── serializers.py          # แปลง model → view + คำนวณ status (dead-man's switch)
    └── routers/                # auth (Discord), me (แดชบอร์ด), agent, device
```

## วิธีรัน (ทีละอย่าง)

### 0) ติดตั้ง dependency
```bash
.venv/bin/pip install -r requirements.txt
```

### 1) เปิด backend
```bash
cd /home/film/Desktop/rejoin
.venv/bin/uvicorn skeleton.backend.app:app --host 0.0.0.0 --port 8000
```
- แดชบอร์ด: http://127.0.0.1:8000/
- **dev**: ใช้ SQLite (`rejoin.db`) + fakeredis อัตโนมัติ + ปุ่ม "เข้าสู่ระบบแบบ dev"
- **production**: ตั้ง env ตาม `.env.example` (Postgres/Redis/Discord) — ดู `docker-compose.yml`

### 2) ติดตั้ง Lua agent ลงเครื่อง
```bash
ADB=.tools/platform-tools/adb
$ADB push skeleton/lua/rejoin_agent.lua /storage/emulated/0/Delta/Autoexecute/rejoin_agent.lua
```

### 3) รัน agent (จำลอง APK) — มี watchdog + รีเกมเอง
```bash
# สร้างเครื่องในเว็บก่อน → ได้รหัสเครื่อง (RJ-XXXXX-XXXXX) → ใส่ --code
.venv/bin/python -m skeleton.agent.agent \
  --adb .tools/platform-tools/adb \
  --device 192.168.96.160:5555 \
  --server http://127.0.0.1:8000 \
  --code RJ-XXXXX-XXXXX --place 107778070777162
```

### 4) ทดสอบ unit tests
```bash
.venv/bin/python -m unittest discover -s skeleton/tests -v
```

## สิ่งที่พิสูจน์แล้ว
- [x] backend รับ register + heartbeat + event (curl)
- [x] Lua agent เขียน state สดจากในเกมจริง
- [x] **loop เต็ม**: Lua เขียน state → agent อ่าน → แดชบอร์ดขึ้น `lua_active`
- [x] **watchdog 17/17 unit tests ผ่าน** (fake clock)
- [x] **AUTO-REJOIN จริงบนเครื่อง**: เกมดับ → watchdog สั่ง LAUNCH →
      เกมเปิดใหม่ → Lua กลับมา → phase กลับเป็น `armed`, `rejoin_count=1`
      (ยืนยันกับเครื่องจริง + ภาพ GUI)
- [x] **Backend จริง**: Postgres-first (dev = SQLite) + Redis (dev = fakeredis) +
      Discord OAuth + รหัสเครื่องแบบ hash (Argon2) + revoke + event ลง DB
      — 24 tests ผ่าน + end-to-end กับเครื่องจริง

## ยังไม่ทำ (เฟสถัดไป)
- APK จริงเป็น Kotlin (ตอนนี้ agent.py จำลองผ่าน adb)
- alert (LINE/Telegram/Discord webhook)
- WebSocket อัปเดตแดชบอร์ดสด (ตอนนี้รีเฟรชหน้า)
- เปิดใช้ Postgres/Redis จริง (ต้องมีสิทธิ์ docker หรือติดตั้งในเครื่อง)

## หมายเหตุจาก Phase 0
- Lua ต้องเขียนไฟล์แบบ **relative path** เท่านั้น
- Delta **บล็อก** localhost HTTP → ใช้ file-based IPC (ออกแบบตามนี้แล้ว)

