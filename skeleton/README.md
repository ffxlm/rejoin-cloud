# Walking Skeleton — Rejoin

เส้นทางบางที่สุดที่วิ่งครบทุกชั้น เพื่อพิสูจน์ loop หลักก่อนทำของจริง

```
Lua เขียน lua_state.json
   → agent_stub อ่านไฟล์ (จำลอง APK) → คำนวณความเงียบ
   → POST /api/agent/heartbeat → backend เก็บสถานะ
   → แดชบอร์ดขึ้น alive
```

## โครงสร้าง
```
skeleton/
├── lua/rejoin_agent.lua       # Lua เขียน state ลง Delta/Workspace/lua_state.json ทุก 10 วิ
├── agent_stub/agent_stub.py   # จำลอง APK: อ่านไฟล์ผ่าน adb → ส่ง heartbeat ไป backend
└── backend/app.py             # FastAPI: รับ heartbeat + แดชบอร์ด (in-memory)
```

## วิธีรัน (ทีละอย่าง)

### 1) เปิด backend
```bash
cd /home/film/Desktop/rejoin
.venv/bin/uvicorn skeleton.backend.app:app --host 0.0.0.0 --port 8000
```
เปิดดูแดชบอร์ด: http://127.0.0.1:8000/  (รีเฟรชทุก 3 วิ)

### 2) ติดตั้ง Lua agent ลงเครื่อง
```bash
ADB=.tools/platform-tools/adb
$ADB push skeleton/lua/rejoin_agent.lua /storage/emulated/0/Delta/Autoexecute/rejoin_agent.lua
```
เปิดเกม (Delta จะ auto-execute เอง) → agent เริ่มเขียน `lua_state.json`

### 3) รัน agent stub (จำลอง APK)
```bash
python3 skeleton/agent_stub/agent_stub.py \
  --adb .tools/platform-tools/adb \
  --device 192.168.96.160:5555 \
  --server http://127.0.0.1:8000 \
  --code DEMO-0001
```

## สิ่งที่พิสูจน์แล้ว
- [x] backend รับ register + heartbeat ได้ (ทดสอบด้วย curl)
- [x] agent_stub อ่าน `lua_state.json` ผ่าน adb + คำนวณ age + POST ได้
- [x] **loop เต็ม**: เกมรัน → Lua เขียน state สด (`ts` ใหม่ทุก 10 วิ) →
      agent_stub อ่านได้ age=1s → แดชบอร์ดขึ้น `lua_active` ✅
      (ยืนยันกับเครื่องจริง: `character=ffxlmzz99`, `map=107778070777162`)

## ยังไม่ทำ (เฟสถัดไป)
- auth จริง / Discord OAuth
- PostgreSQL + Redis (ตอนนี้ in-memory)
- APK จริง (ตอนนี้ agent_stub จำลอง)
- screenshot, alert, WebSocket
- watchdog รีเกมเอง (retry/backoff)

## หมายเหตุจาก Phase 0
- Lua ต้องเขียนไฟล์แบบ **relative path** เท่านั้น
- Delta **บล็อก** localhost HTTP → ใช้ file-based IPC (ออกแบบตามนี้แล้ว)
