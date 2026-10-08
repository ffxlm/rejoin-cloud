# DEPLOY — เอาระบบขึ้นให้ "ใช้ได้ทั่วโลก"

เป้าหมาย: **APK บนคลาวโฟนที่ไหนก็ได้ ยิงเข้าเว็บผ่าน HTTPS สาธารณะ** (ไม่ใช่ LAN/localhost)

---

## สถาปัตยกรรมบน production
```
คลาวโฟน (ที่ไหนก็ได้)                     VPS ของคุณ (มี IP สาธารณะ + โดเมน)
┌──────────────┐   HTTPS (443)   ┌──────────────────────────────────────┐
│ APK Rejoin    │ ───────────────►│ Caddy (auto HTTPS/Let's Encrypt)      │
│ Agent (root)  │                 │   └─► app (FastAPI :8000)             │
└──────────────┘                 │        ├─► Postgres                   │
                                  │        └─► Redis                      │
                                  └──────────────────────────────────────┘
```

## สิ่งที่ต้องมี
1. **VPS** (Ubuntu 22.04/24.04, RAM ≥ 1GB) — เช่น DigitalOcean / Vultr / Hetzner / AWS Lightsail
2. **โดเมน** 1 อัน (เช่น `rejoin.example.com`) → ตั้ง **A record** ชี้ไป IP ของ VPS
3. เปิดพอร์ต **80** และ **443** บน firewall ของ VPS
4. (ตัวเลือก) **Discord OAuth app** — https://discord.com/developers/applications

---

## ขั้นตอน deploy

### 1) เตรียม VPS
```bash
ssh root@<IP-VPS>
# ติดตั้ง Docker + compose plugin
curl -fsSL https://get.docker.com | sh
```

### 2) เอาโค้ดขึ้น VPS
```bash
git clone https://github.com/ffxlm/rejoin-cloud.git
cd rejoin-cloud
```

### 3) ตั้งค่า
```bash
cp deploy/.env.example deploy/.env
nano deploy/.env
```
แก้:
- `DOMAIN=rejoin.example.com`
- `POSTGRES_PASSWORD=<สุ่มยาวๆ>`
- `SESSION_SECRET=<openssl rand -hex 32>`
- `DISCORD_CLIENT_ID/SECRET` (ถ้าใช้ Discord login)
- `DISCORD_REDIRECT_URI=https://rejoin.example.com/auth/discord/callback`

### 4) รัน
```bash
docker compose -f deploy/docker-compose.yml up -d --build
docker compose -f deploy/docker-compose.yml logs -f app   # ดู log
```
Caddy จะขอ certificate ให้เองอัตโนมัติ (รอ ~30 วิ)

### 5) ตรวจว่าใช้ได้
```bash
curl https://rejoin.example.com/health
# → {"ok":true,"redis":true,"db":"postgresql+asyncpg"}
```
เปิดเบราว์เซอร์: `https://rejoin.example.com/` → ล็อกอิน → เพิ่มเครื่อง → ได้รหัส

### 6) ตั้งค่า APK ให้ชี้โดเมนนี้
ในแอป Rejoin Agent → ช่อง "เซิร์ฟเวอร์" ใส่ `https://rejoin.example.com`
(ค่า default ในโค้ดควรแก้เป็นโดเมนคุณใน `Prefs.DEFAULT_SERVER`)

จากนี้ **คลาวโฟนที่ไหนก็ใช้ได้** — ไม่ต้อง adb/ไม่ต้อง LAN

---

## Discord OAuth (ล็อกอินจริง)
1. https://discord.com/developers/applications → New Application
2. แท็บ **OAuth2** → คัดลอก **Client ID** + **Client Secret** ใส่ `deploy/.env`
3. เพิ่ม **Redirect URI**: `https://rejoin.example.com/auth/discord/callback`
4. หลัง deploy → หน้า login จะมีปุ่ม "เข้าสู่ระบบด้วย Discord"

---

## อัปเดตโค้ดใหม่
```bash
cd rejoin-cloud && git pull
docker compose -f deploy/docker-compose.yml up -d --build
```

## ปัญหาที่เจอบ่อย
| อาการ | แก้ |
|---|---|
| Caddy ขอ cert ไม่ได้ | โดเมนยังไม่ชี้ IP / ยังไม่เปิดพอร์ต 80,443 |
| `db: postgresql` แต่ error เชื่อม | ดู `docker compose logs postgres` (รหัสผ่านใน .env) |
| APK register ไม่ผ่าน | URL ในแอปต้องเป็น `https://โดเมน` (ไม่ใช่ http/localhost) |
| ล็อกอินค้าง | `COOKIE_SECURE=true` ต้องเข้าผ่าน https เท่านั้น |
