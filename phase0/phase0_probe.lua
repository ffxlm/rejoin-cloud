--[[
  phase0_probe.lua — สคริปต์ตรวจสมมติฐาน Phase 0
  ------------------------------------------------------------------
  วิธีใช้:
    1) push ไปเป็น  /storage/emulated/0/Delta/Autoexecute/rejoin_agent.lua
    2) เปิด listener บน PC + `adb reverse tcp:8787 tcp:8787`
    3) เปิดเกม (Roblox) ทิ้งไว้ ~60-120 วิ
    4) ดูผลจาก:
         - หน้าจอ listener (ถ้า HTTP ผ่าน)
         - ไฟล์ phase0_probe.log ใน workspace ของ executor (ดึงผ่าน adb)

  สคริปต์นี้ตรวจ 3 อย่าง:
    A) Delta รัน Lua อัตโนมัติไหม (ถ้ารัน = มี log/HTTP)
    B) Lua เขียน/อ่านไฟล์ได้ไหม
    C) Lua ยิง HTTP ไป localhost (127.0.0.1) ได้ไหม
  ทุกอย่างห่อ pcall — สคริปต์ต้องไม่ error จนเกมพัง
]]

local PORT = 8787
local lines = {}
local t0 = nil
pcall(function() t0 = os.time() end)
if not t0 then t0 = 0 end

local function log(fmt, ...)
  local ok, msg = pcall(string.format, fmt, ...)
  if not ok then msg = tostring(fmt) end
  table.insert(lines, string.format("[t=%s] %s", tostring(t0), msg))
end

local function flush()
  local text = "PHASE0 PROBE\n" .. table.concat(lines, "\n") .. "\n"
  -- executor ส่วนใหญ่ใช้ writefile แบบ path สัมพัทธ์ (workspace)
  if type(writefile) == "function" then
    pcall(writefile, "phase0_probe.log", text)
    pcall(writefile, "phase0_probe_" .. tostring(t0) .. ".log", text)
  end
  -- เผื่อบางตัวให้ absolute path
  if type(writefile) == "function" then
    pcall(writefile, "/sdcard/Delta/phase0_probe.log", text)
  end
  -- เผื่อ print ออกคอนโซล executor
  if type(print) == "function" then
    pcall(print, text)
  end
  return text
end

-- ---------- A) ตัวตน executor / เกม ----------
log("PROBE START")
if type(identifyexecutor) == "function" then
  local ok, id = pcall(identifyexecutor)
  log("identifyexecutor=%s (ok=%s)", tostring(id), tostring(ok))
end
if type(getexecutorname) == "function" then
  local ok, id = pcall(getexecutorname)
  log("getexecutorname=%s (ok=%s)", tostring(id), tostring(ok))
end
pcall(function()
  if game then
    log("game.PlaceId=%s JobId=%s", tostring(game.PlaceId), tostring(game.JobId))
    log("game.Name=%s", tostring(game.Name))
  end
end)

-- ---------- B) ไฟล์ ----------
if type(writefile) == "function" then
  local ok, err = pcall(writefile, "phase0_wrote.txt", "hello " .. tostring(t0))
  log("writefile(rel) ok=%s err=%s", tostring(ok), tostring(err))
  local ok2, err2 = pcall(writefile, "/sdcard/Delta/phase0_abs.txt", "abs " .. tostring(t0))
  log("writefile(abs) ok=%s err=%s", tostring(ok2), tostring(err2))
else
  log("writefile = MISSING")
end

if type(isfile) == "function" and type(readfile) == "function" then
  local exists = pcall(isfile, "phase0_wrote.txt")
  local ok, content = pcall(readfile, "phase0_wrote.txt")
  log("readfile ok=%s content=%s", tostring(ok), tostring(content))
  log("isfile ok=%s", tostring(exists))
else
  log("readfile/isfile = MISSING")
end

-- ---------- C) HTTP ไป localhost ----------
local httpFuncs = {}
if type(request) == "function" then httpFuncs["request"] = request end
if type(http_request) == "function" then httpFuncs["http_request"] = http_request end
if type(syn) == "table" and type(syn.request) == "function" then httpFuncs["syn.request"] = syn.request end
if type(http) == "table" and type(http.request) == "function" then httpFuncs["http.request"] = http.request end

if next(httpFuncs) == nil then
  log("HTTP request function = MISSING (executor ไม่มี request/http_request/syn/http)")
end

for name, fn in pairs(httpFuncs) do
  local url = string.format("http://127.0.0.1:%d/lua/heartbeat", PORT)
  local ok, res = pcall(fn, {
    Url = url,
    Method = "POST",
    Headers = { ["Content-Type"] = "application/json" },
    Body = string.format('{"state":"in_game","probe":"%s","ts":%d}', name, t0),
  })
  if ok and type(res) == "table" then
    local status = res.StatusCode or res.Status or res.status or "?"
    local body = res.Body or res.body or ""
    log("http[%s] OK status=%s body=%s", name, tostring(status), tostring(body))
  else
    log("http[%s] FAIL ok=%s res=%s", name, tostring(ok), tostring(res))
  end
end

-- ---------- เขียนผลลง log ----------
flush()
