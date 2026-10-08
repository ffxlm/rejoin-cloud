# RUNBOOK — เริ่มระบบจาก 0 (ทั้งเว็บ + ตัวรีเกม)

> อัปเดต: 2026-10-08 · อ้างอิง `HANDOFF.md`, `android/README.md`
> สถานะ: **เว็บ (backend) ใช้งานได้จริง** · **ตัวรีเกมจริง = `agent.py` (python)**
> · **APK = สเกเลตัน** (UI + Foreground Service เปล่า ยังไม่ทำงานจริง)

---

## ภาพรวม: อะไรทำงานจริง / อะไรยังไม่

| ชิ้น | ทำงานจริง? | หมายเหตุ |
|---|---|---|
| **backend (เว็บ)** | ✅ จริง | ล็อกอิน, เพิ่มเครื่อง, ออก/revoke รหัส, แดชบอร์ด, arm/disarm, events |
| **agent.py (python)** | ✅ จริง | ตัวที่เฝ้าเกม + รีเกมเอง (รันบนคอม ผ่าน adb) |
| **APK Kotlin** | ❌ สเกเลตัน | build/ติดตั้ง/เปิด UI ได้ แต่ยังไม่คุยเว็บ/ไม่แตะเกม |

> ถ้าต้องการ "ระบบรีเกมที่ทำงานจริง" ให้รัน `agent.py` (ข้อ 4)
> APK จะทำงานจริงหลังพอร์ตฟีเจอร์ (ดู `android/README.md`)

---

## 0. สิ่งที่ต้องมี
- Linux + Python 3.12
- adb (อยู่ใน `.tools/platform-tools/adb` — ไม่ขึ้น git)
- เครื่อง Android ที่ root (Magisk) + เกม Delta (`com.roblox.client`)
- ต่อ adb ได้ (USB หรือ wireless)

```bash
cd /home/film/Desktop/rejoin
```

---

## 1. สร้าง Python venv + ติดตั้ง dependency
```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

## 2. ต่อ adb เข้าเครื่อง
```bash
ADB=.tools/platform-tools/adb
$ADB connect 192.168.96.160:5555      # ถ้าใช้ wireless
$ADB devices                          # ต้องเห็น device
```

## 3. เปิด backend (เว็บ)
```bash
# dev: ใช้ SQLite (rejoin.db) + fakeredis อัตโนมัติ — ไม่ต้องตั้งอะไร
.venv/bin/uvicorn skeleton.backend.app:app --host 0.0.0.0 --port 8000
```
- เปิดเบราว์เซอร์: http://127.0.0.1:8000/
- กด **"เข้าสู่ระบบแบบ dev"** (หรือตั้ง Discord OAuth ใน `.env` แล้วใช้ปุ่ม Discord)
- กด **"+ เพิ่มเครื่อง"** → ได้ **รหัสเครื่อง** `RJ-XXXXX-XXXXX` (จดไว้ — โชว์ครั้งเดียว)

> production: คัดลอก `.env.example` → `.env`, ตั้ง `DATABASE_URL`/`REDIS_URL`/`DISCORD_*`
> แล้วรัน `docker compose up -d` (pg/redis/minio) — ดู `.env.example`

## 4. รันตัวรีเกม (agent.py) — ใช้รหัสเครื่องจากข้อ 3
```bash
.venv/bin/python -m skeleton.agent.agent \
  --adb .tools/platform-tools/adb \
  --device 192.168.96.160:5555 \
  --server http://127.0.0.1:8000 \
  --code RJ-XXXXX-XXXXX \
  --place 107778070777162 \
  --interval 8 --silence 60 --timeout 300
```
จะเห็น log: `[agent] registered: {...}` แล้ว `phase=lua_active ...`

## 5. เปิด auto-rejoin (arm)
- บนเว็บ กดปุ่ม **`arm`** ในการ์ดเครื่อง (หรือ `curl -b cookies.txt -X POST .../api/device/1/arm`)
- จากนี้ถ้าเกมหลุด (Lua เงียบ > 60 วิ) มันจะรีเกมเอง

## 6. ทดสอบว่ากู้ได้จริง (จำลองเกมหลุด)
```bash
ADB=.tools/platform-tools/adb
$ADB -s 192.168.96.160:5555 shell su -c "am force-stop com.roblox.client"
# เฝ้า log agent: phase ควรเป็น rejoining → armed และ rejoin_count เพิ่ม
```
> รอเกมโหลดได้ถึง ~3 นาที (เน็ตคลาวโฟนช้า) — อย่าใจร้อน

---

## APK (สเกเลตัน) — build/ติดตั้ง/รัน
```bash
# build ผ่าน GitHub Actions (ไม่ต้องมี SDK ในเครื่อง)
git push origin master        # workflow .github/workflows/android.yml ทำงานเอง
gh run list --workflow=android.yml
gh run download -n rejoin-agent-debug -D /tmp/opencode/apkdl

# ติดตั้ง
.tools/platform-tools/adb -s 192.168.96.160:5555 install -r /tmp/opencode/apkdl/app-debug.apk

# เปิดแอป แล้วกรอกรหัสเครื่อง + กด "เริ่มเฝ้า"
```
> ตอนนี้ APK แค่ขึ้น UI + รัน Foreground Service — **ยังไม่ทำงานรีเกม**

---

## ปิดทั้งหมด
```bash
pkill -f "uvicorn skeleton.backend"      # ปิดเว็บ
pkill -f "skeleton.agent.agent"          # ปิดตัวรีเกม (หยุดรีเอง)
.tools/platform-tools/adb -s 192.168.96.160:5555 shell am force-stop com.rejoin.agent  # ปิดแอป
```

---

## แก้ปัญหาเบื้องต้น
| อาการ | วิธีแก้ |
|---|---|
| `register failed` | รหัสเครื่องผิด/ถูก revoke → สร้างเครื่องใหม่ในเว็บ |
| สถานะ `offline` ตลอด | agent ไม่ได้รัน หรือส่ง heartbeat ไม่ถึง `--server` |
| รีเกมไม่ทำงาน | ยังไม่ arm / Lua ไม่เขียนไฟล์ / เกมโหลดช้ากว่า timeout |
| `adb: device offline` | `adb connect` ใหม่ |
| backend ไม่ขึ้น | พอร์ต 8000 ถูกใช้ → `ss -ltnp \| grep 8000` |
