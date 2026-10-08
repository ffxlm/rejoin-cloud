--[[
  ip_probe.lua — เทสต์ทางเลือกแทน localhost (loopback ถูกบล็อก)
  ทดสอบ:
    A) self-IP 192.168.96.160:8790 (ap0)  -> HTTP ผ่านไหม
    B) self-IP 10.79.67.100:8790 (ccmni2) -> HTTP ผ่านไหม
    C) self-IP 192.168.96.160:8791        -> POST ผ่านไหม
    D) ไฟล์: เขียน command/state ลง Workspace
  รันอัตโนมัติผ่าน Autoexecute
]]

local lines = {}
local function log(fmt, ...)
  local ok, msg = pcall(string.format, fmt, ...)
  if not ok then msg = tostring(fmt) end
  table.insert(lines, msg)
end
local function flush()
  local text = "IP PROBE\n" .. table.concat(lines, "\n") .. "\n"
  if type(writefile) == "function" then pcall(writefile, "ip_probe.log", text) end
  if type(print) == "function" then pcall(print, text) end
end

local httpFuncs = {}
if type(request) == "function" then httpFuncs["request"] = request end
if type(http_request) == "function" then httpFuncs["http_request"] = http_request end
if type(syn) == "table" and type(syn.request) == "function" then httpFuncs["syn.request"] = syn.request end
if type(http) == "table" and type(http.request) == "function" then httpFuncs["http.request"] = http.request end

log("IP PROBE START")

local tests = {
  { name = "selfIP_ap0_8790",  url = "http://192.168.96.160:8790/lua/heartbeat", method = "GET" },
  { name = "selfIP_ccmni_8790", url = "http://10.79.67.100:8790/lua/heartbeat", method = "GET" },
  { name = "selfIP_ap0_8791_POST", url = "http://192.168.96.160:8791/lua/heartbeat", method = "POST", body = '{"state":"in_game","probe":"post"}' },
}

for fname, fn in pairs(httpFuncs) do
  for _, t in ipairs(tests) do
    local ok, res = pcall(fn, {
      Url = t.url, Method = t.method,
      Headers = { ["Content-Type"] = "application/json" },
      Body = t.body,
    })
    if ok and type(res) == "table" then
      local status = res.StatusCode or res.Status or res.status or "?"
      local body = tostring(res.Body or res.body or "")
      if #body > 80 then body = body:sub(1, 80) .. "..." end
      log("[%s] %s -> OK status=%s body=%s", fname, t.name, tostring(status), body)
    else
      log("[%s] %s -> FAIL %s", fname, t.name, tostring(res))
    end
  end
end

-- D) file-based
if type(writefile) == "function" then
  local ok = pcall(writefile, "lua_state.json", '{"state":"in_game","ts":' .. tostring(os.time and os.time() or 0) .. '}')
  log("write lua_state.json ok=%s", tostring(ok))
  local ok2 = pcall(writefile, "command_read_test.txt", "hello-from-lua")
  log("write command_read_test.txt ok=%s", tostring(ok2))
  if type(readfile) == "function" then
    local ok3, c = pcall(readfile, "command_read_test.txt")
    log("read command_read_test.txt ok=%s content=%s", tostring(ok3), tostring(c))
  end
end

flush()
