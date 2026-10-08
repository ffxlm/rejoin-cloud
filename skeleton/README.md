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
├── tests/test_watchdog.py      # unit tests (fake clock)
└── backend/app.py              # FastAPI: heartbeat + event + dashboard
```

## วิธีรัน (ทีละอย่าง)

### 1) เปิด backend
```bash
cd /home/film/Desktop/rejoin
.venv/bin/uvicorn skeleton.backend.app:app --host 0.0.0.0 --port 8000
```
แดชบอร์ด: http://127.0.0.1:8000/  (รีเฟรชทุก 3 วิ)

### 2) ติดตั้ง Lua agent ลงเครื่อง
```bash
ADB=.tools/platform-tools/adb
$ADB push skeleton/lua/rejoin_agent.lua /storage/emulated/0/Delta/Autoexecute/rejoin_agent.lua
```

### 3) รัน agent (จำลอง APK) — มี watchdog + รีเกมเอง
```bash
.venv/bin/python -m skeleton.agent.agent \
  --adb .tools/platform-tools/adb \
  --device 192.168.96.160:5555 \
  --server http://127.0.0.1:8000 \
  --code DEMO-0001 --place 107778070777162
```

### 4) ทดสอบ unit tests
```bash
.venv/bin/python -m unittest discover -s skeleton/tests -v
```

## สิ่งที่พิสูจน์แล้ว
- [x] backend รับ register + heartbeat + event (curl)
- [x] Lua agent เขียน state สดจากในเกมจริง
- [x] **loop เต็ม**: Lua เขียน state → agent อ่าน → แดชบอร์ดขึ้น `lua_active`
- [x] **watchdog 13/13 unit tests ผ่าน** (fake clock)
- [x] **AUTO-REJOIN จริงบนเครื่อง**: เกมดับ → watchdog สั่ง LAUNCH →
      เกมเปิดใหม่ → Lua กลับมา → phase กลับเป็น `armed`, `rejoin_count=1`
      (ยืนยันกับเครื่องจริง + ภาพ GUI)

## ยังไม่ทำ (เฟสถัดไป)
- auth จริง / Discord OAuth
- PostgreSQL + Redis (ตอนนี้ in-memory)
- APK จริงเป็น Kotlin (ตอนนี้ agent.py จำลองผ่าน adb)
- screenshot อัตโนมัติ, alert (LINE/Telegram), WebSocket
- ปรับ timeout ให้เหมาะกับเน็ตช้า (ตอนนี้ rejoin_timeout 90 วิ แต่เกมโหลด 3 นาที)

## หมายเหตุจาก Phase 0
- Lua ต้องเขียนไฟล์แบบ **relative path** เท่านั้น
- Delta **บล็อก** localhost HTTP → ใช้ file-based IPC (ออกแบบตามนี้แล้ว)

