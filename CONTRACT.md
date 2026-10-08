# Contract — สัญญาระหว่างชิ้นส่วน (v0.2)

> ตรึง interface ระหว่าง Lua / APK / เว็บ ก่อนลงมือโค้ด เพื่อให้ทำขนานกันได้
> อ้างอิงจากผลเทสต์ Phase 0 (`PHASE0_RESULTS.md`)

---

## 1. Lua → APK (file-based IPC)

### 1.1 ไฟล์ state
- **path (relative เท่านั้น):** `lua_state.json` (อยู่ที่ `Delta/Workspace/`)
- **เขียนทุก:** 10 วิ
- **atomic:** เขียน `lua_state.tmp` → rename ทับ `lua_state.json`

```json
{
  "v": 1,
  "state": "in_game",
  "avatar": "ชื่อ/รหัส avatar",
  "character": "ชื่อตัวละคร",
  "map": "ชื่อ/รหัสแมพ",
  "place_id": 107778070777162,
  "job_id": "c3a66ec2-900a-46af-a647-bb7a28bae76f",
  "ts": 1730000000
}
```

| ฟิลด์ | ชนิด | บังคับ | ความหมาย |
|---|---|---|---|
| `v` | int | ✅ | เวอร์ชัน schema (กัน format เปลี่ยน) |
| `state` | string | ✅ | `in_game` / `loading` / `menu` / `unknown` |
| `avatar` | string | ❌ | ชื่อ/รูปตัวละคร |
| `character` | string | ❌ | ชื่อตัวละครในเกม |
| `map` | string | ❌ | ชื่อ/รหัสแมพ |
| `place_id` | int | ❌ | PlaceId ปัจจุบัน |
| `job_id` | string | ❌ | JobId ของเซิร์ฟเวอร์ |
| `ts` | int | ✅ | Unix time (วินาที) ตอนเขียน — APK ใช้ตัดสินความเงียบ |

### 1.2 การตัดสินความเงียบ (ฝั่ง APK)
```
age = now - ts
age <= 60s   → alive (lua_active)
age >  60s   → เงียบ → เข้า rejoining
```

### 1.3 ไฟล์ควบคุม APK → Lua (ถ้าจำเป็น)
- APK เขียน `agent_cmd.json` (relative, `Delta/Workspace/`) → Lua อ่าน (เช่น `stop`)
- ไม่บังคับใน MVP

---

## 2. APK → เว็บ (HTTPS + JSON)

### 2.1 header
```
Authorization: Bearer <device_token>
Content-Type: application/json
```

### 2.2 Endpoints

| method | path | หน้าที่ |
|---|---|---|
| POST | `/api/agent/register` | แลก device_code → device_token (ครั้งแรก) |
| POST | `/api/agent/heartbeat` | ส่งสถานะทุก N วิ |
| GET | `/api/device/command` | APK poll คำสั่ง |
| POST | `/api/agent/event` | ส่ง event (rejoin/alert) |

**register (request)**
```json
{ "device_code": "XXXX-XXXX", "apk_version": "0.1.0", "android_id": "..." }
```
**register (response)**
```json
{ "device_token": "tok_...", "device_id": "dev_...", "interval_sec": 15 }
```

**heartbeat (request)**
```json
{
  "v": 1,
  "state": "armed",
  "game_running": true,
  "lua_active": true,
  "lua_age_sec": 3,
  "avatar": "...",
  "character": "...",
  "map": "...",
  "rejoin_count": 3,
  "session_start": 1730000000,
  "ts": 1730000000
}
```
**heartbeat (response)**
```json
{ "ok": true, "command": null }
```
> `command` (ถ้ามี): `arm` / `disarm` / `rejoin_now` / `stop` / `update_lua`

**command (poll response)**
```json
{ "command": "rejoin_now", "id": "cmd_123" }
```

---

## 3. เว็บ → ผู้ใช้ (แดชบอร์ด)

| method | path | หน้าที่ |
|---|---|---|
| GET | `/auth/discord` | เริ่ม OAuth |
| GET | `/auth/discord/callback` | callback → session cookie |
| GET | `/api/me` | ข้อมูลผู้ใช้ |
| GET | `/api/me/devices` | รายการเครื่อง + สถานะ |
| POST | `/api/me/devices` | เพิ่มเครื่อง → คืน device_code |
| DELETE | `/api/me/devices/:id` | ลบ/revoke |
| GET | `/api/download/apk` | ดาวน์โหลด APK |
| GET | `/api/download/lua` | ดาวน์โหลด Lua (ตาม device_token) |
| POST | `/api/device/:id/arm` | เริ่ม auto-rejoin |
| POST | `/api/device/:id/disarm` | หยุด auto-rejoin |
| POST | `/api/device/:id/rejoin_now` | สั่งกู้เกมทันที |
| WS | `/ws` | อัปเดตสถานะสด |

---

## 4. สถานะ (state enum)

```
offline | connected | game_running | lua_active | armed | rejoining | alert
```
- "พร้อม" = `game_running` **และ** `lua_active`
- ปุ่ม Start enable เมื่อ = `lua_active`

---

## 5. Data Model (PostgreSQL)

```sql
-- ผู้ใช้
CREATE TABLE users (
  id           BIGSERIAL PRIMARY KEY,
  discord_id   TEXT UNIQUE NOT NULL,
  username     TEXT,
  avatar       TEXT,
  created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- เครื่อง
CREATE TABLE devices (
  id            BIGSERIAL PRIMARY KEY,
  user_id       BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  name          TEXT NOT NULL,
  game_pkg      TEXT NOT NULL DEFAULT 'com.roblox.client',
  status        TEXT NOT NULL DEFAULT 'offline',
  armed         BOOLEAN NOT NULL DEFAULT false,
  armed_at      TIMESTAMPTZ,
  session_start TIMESTAMPTZ,
  lua_version   TEXT,
  apk_version   TEXT,
  last_seen     TIMESTAMPTZ,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- รหัสเครื่อง (เก็บ hash เท่านั้น)
CREATE TABLE device_tokens (
  id          BIGSERIAL PRIMARY KEY,
  device_id   BIGINT NOT NULL REFERENCES devices(id) ON DELETE CASCADE,
  token_hash  TEXT NOT NULL,            -- Argon2/bcrypt ของ device_token
  label       TEXT,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  revoked_at  TIMESTAMPTZ
);

-- state ล่าสุดจาก Lua (denormalized เพื่อโชว์เร็ว)
CREATE TABLE device_state (
  device_id   BIGINT PRIMARY KEY REFERENCES devices(id) ON DELETE CASCADE,
  avatar      TEXT,
  character   TEXT,
  map         TEXT,
  place_id    BIGINT,
  job_id      TEXT,
  lua_age_sec INT,
  updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- เหตุการณ์ (connect/rejoin/alert/arm/disarm) — ใช้คำนวณ runtime/rejoin_count
CREATE TABLE events (
  id         BIGSERIAL PRIMARY KEY,
  device_id  BIGINT NOT NULL REFERENCES devices(id) ON DELETE CASCADE,
  type       TEXT NOT NULL,
  detail     JSONB,
  ts         TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_events_device_ts ON events(device_id, ts DESC);
```

**หมายเหตุ:**
- `rejoin_count` = `COUNT(events WHERE type='rejoin')` — ไม่เก็บซ้ำ
- `last_seen` เก็บเร็วใน Redis (TTL) สำหรับ watchdog
- ห้ามเก็บ device_token เป็น plaintext

---

## 6. สัญญาเรื่องเวลา (time)
- ทุก timestamp = Unix วินาที (UTC) — ฝั่ง APK ใช้เวลาจาก Lua (`ts`) เป็นหลัก
- APK เทียบ `now` ของเครื่องกับ `ts` ของ Lua → ต้องอยู่ใน timezone เดียวกัน (Unix time ปลอดภัย)
- ฝั่งเว็บรับ `ts` จาก APK แต่ใช้ `last_seen` ของตัวเองตัดสิน offline

---

## 7. เวอร์ชัน
| ชิ้น | เวอร์ชัน | เปลี่ยนอะไร |
|---|---|---|
| schema (v) | 1 | เริ่มต้น |
| contract | 0.1 | ร่างแรกหลัง Phase 0 |
| contract | 0.2 | เอาระบบแคปภาพหน้าจอ (screenshot) ออกทั้งวงจร |
