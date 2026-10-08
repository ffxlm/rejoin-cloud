--[[
  rejoin_agent.lua — Lua agent (Walking Skeleton)
  ------------------------------------------------------------------
  หน้าที่: เขียน lua_state.json ลง workspace ของ executor ทุก HEARTBEAT_SEC
  หมายเหตุสำคัญ (จาก Phase 0):
    - ต้องใช้ writefile แบบ relative path เท่านั้น (absolute ล้มเหลว)
    - Delta บล็อก localhost HTTP → ใช้ file-based IPC แทน
  ไฟล์ถูกเขียนที่: Delta/Workspace/lua_state.json
]]

local HEARTBEAT_SEC = 10
local STATE_FILE = "lua_state.json"
local TMP_FILE = "lua_state.tmp"

-- ---- เก็บข้อมูล player ----
local function getPlayerInfo()
  local info = { avatar = nil, character = nil }
  pcall(function()
    local Players = game:GetService("Players")
    local lp = Players.LocalPlayer
    if lp then
      info.avatar = tostring(lp.UserId)
      info.character = lp.Name
    end
  end)
  return info
end

local function jsonEscape(s)
  s = tostring(s)
  return (s:gsub('\\', '\\\\'):gsub('"', '\\"'):gsub('\n', '\\n'):gsub('\r', '\\r'):gsub('\t', '\\t'))
end

local function buildState()
  local p = getPlayerInfo()
  local placeId = 0
  local jobId = ""
  pcall(function()
    placeId = game.PlaceId or 0
    jobId = tostring(game.JobId or "")
  end)

  local ts = os.time()
  local parts = {
    '"v":1',
    '"state":"in_game"',
    '"avatar":"' .. jsonEscape(p.avatar or "") .. '"',
    '"character":"' .. jsonEscape(p.character or "") .. '"',
    '"map":"' .. jsonEscape(tostring(placeId)) .. '"',
    '"place_id":' .. tostring(placeId),
    '"job_id":"' .. jsonEscape(jobId) .. '"',
    '"ts":' .. tostring(ts),
  }
  return "{" .. table.concat(parts, ",") .. "}"
end

local function writeAtomic()
  local payload = buildState()
  -- เขียน tmp ก่อน แล้ว rename ทับ (atomic)
  local ok1 = pcall(writefile, TMP_FILE, payload)
  if not ok1 then
    -- fallback: เขียนตรงๆ
    pcall(writefile, STATE_FILE, payload)
    return
  end
  -- ลอง rename (executor บางตัวมี delfile/rename)
  local renamed = false
  if type(rename) == "function" then
    renamed = pcall(rename, TMP_FILE, STATE_FILE)
  end
  if not renamed then
    -- ไม่มี rename → เขียนทับตรงๆ แล้วลบ tmp
    pcall(writefile, STATE_FILE, payload)
    if type(delfile) == "function" then pcall(delfile, TMP_FILE) end
  end
end

-- ---- GUI ยืนยันการทำงาน (ไม่บังคับ) ----
local function makeGui()
  local label = nil
  pcall(function()
    local parent = (type(gethui) == "function" and gethui()) or game:GetService("CoreGui")
    local sg = Instance.new("ScreenGui")
    sg.Name = "RejoinAgent"
    sg.ResetOnSpawn = false
    sg.Parent = parent
    local lbl = Instance.new("TextLabel")
    lbl.Size = UDim2.new(0, 360, 0, 32)
    lbl.Position = UDim2.new(0, 10, 0, 10)
    lbl.BackgroundColor3 = Color3.fromRGB(0, 0, 0)
    lbl.BackgroundTransparency = 0.3
    lbl.TextColor3 = Color3.fromRGB(0, 255, 120)
    lbl.TextScaled = true
    lbl.Font = Enum.Font.Code
    lbl.TextXAlignment = Enum.TextXAlignment.Left
    lbl.Text = "  REJOIN agent | starting..."
    lbl.Parent = sg
    label = lbl
  end)
  return label
end

local lbl = makeGui()
local n = 0

-- ---- loop หลัก ----
task.spawn(function()
  while true do
    local ok, err = pcall(writeAtomic)
    n = n + 1
    if lbl then
      pcall(function()
        lbl.Text = ("  REJOIN agent | beat #%d | %s | %s"):format(n, ok and "OK" or "ERR", os.date("%H:%M:%S"))
      end)
    end
    if type(print) == "function" then
      pcall(print, ("[rejoin_agent] beat #%d ok=%s %s"):format(n, tostring(ok), tostring(err or "")))
    end
    task.wait(HEARTBEAT_SEC)
  end
end)
