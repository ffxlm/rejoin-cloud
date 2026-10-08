--[[
  http_probe.lua — แยกให้ชัดว่า Delta ยิง HTTP ได้แบบไหน
  เทสต์:
    1) external HTTPS  (api.ipify.org)      → เน็ตออกได้ไหม
    2) external POST   (httpbin.org/post)   → POST ได้ไหม
    3) localhost 127.0.0.1:8787             → loopback ผ่านไหม (ต้องมี adb reverse + listener)
    4) localhost 10.0.2.2:8787              → เผื่อ emulator-style
  รันอัตโนมัติผ่าน Autoexecute — ไม่ต้องกดอะไรในเกม
]]

local lines = {}
local function log(fmt, ...)
  local ok, msg = pcall(string.format, fmt, ...)
  if not ok then msg = tostring(fmt) end
  table.insert(lines, msg)
end

local function flush()
  local text = "HTTP PROBE\n" .. table.concat(lines, "\n") .. "\n"
  if type(writefile) == "function" then
    pcall(writefile, "http_probe.log", text)
  end
  if type(print) == "function" then pcall(print, text) end
end

-- รวบรวมฟังก์ชัน http ที่ executor มี
local httpFuncs = {}
if type(request) == "function" then httpFuncs["request"] = request end
if type(http_request) == "function" then httpFuncs["http_request"] = http_request end
if type(syn) == "table" and type(syn.request) == "function" then httpFuncs["syn.request"] = syn.request end
if type(http) == "table" and type(http.request) == "function" then httpFuncs["http.request"] = http.request end

log("HTTP PROBE START")
log("available http funcs: %s", (next(httpFuncs) and table.concat((function()
  local t = {}
  for k in pairs(httpFuncs) do table.insert(t, k) end
  return t
end)(), ",")) or "NONE")

local tests = {
  { name = "external_https", url = "https://api.ipify.org?format=json", method = "GET" },
  { name = "external_post",  url = "https://httpbin.org/post", method = "POST", body = '{"x":1}' },
  { name = "localhost_8787", url = "http://127.0.0.1:8787/lua/heartbeat", method = "POST", body = '{"probe":"localhost"}' },
  { name = "localhost_8788", url = "http://127.0.0.1:8788/lua/heartbeat", method = "POST", body = '{"probe":"8788"}' },
}

for fname, fn in pairs(httpFuncs) do
  for _, t in ipairs(tests) do
    local ok, res = pcall(fn, {
      Url = t.url,
      Method = t.method,
      Headers = { ["Content-Type"] = "application/json" },
      Body = t.body,
    })
    if ok and type(res) == "table" then
      local status = res.StatusCode or res.Status or res.status or "?"
      local body = tostring(res.Body or res.body or "")
      if #body > 120 then body = body:sub(1, 120) .. "..." end
      log("[%s] %s -> OK status=%s body=%s", fname, t.name, tostring(status), body)
    else
      log("[%s] %s -> FAIL %s", fname, t.name, tostring(res))
    end
  end
end

flush()
