--[[
  http_vs_https.lua — แยกสาเหตุ: cleartext HTTP ถูกบล็อก หรือ เฉพาะ IP ภายใน
  เทสต์:
    https://httpbin.org/post   (control, ควรผ่าน)
    http://httpbin.org/post    (cleartext external)
    http://example.com/        (cleartext external อีกตัว)
    http://192.168.96.160:8790/ (self-IP cleartext)
  รันอัตโนมัติผ่าน Autoexecute
]]
local lines = {}
local function log(fmt, ...)
  local ok, msg = pcall(string.format, fmt, ...)
  if not ok then msg = tostring(fmt) end
  table.insert(lines, msg)
end
local function flush()
  local text = "HTTPVSHTTPS\n" .. table.concat(lines, "\n") .. "\n"
  if type(writefile) == "function" then pcall(writefile, "http_vs_https.log", text) end
  if type(print) == "function" then pcall(print, text) end
end

local fn = nil
if type(request) == "function" then fn = request
elseif type(http_request) == "function" then fn = http_request
elseif type(syn) == "table" and type(syn.request) == "function" then fn = syn.request
elseif type(http) == "table" and type(http.request) == "function" then fn = http.request
end

log("HTTPVSHTTPS START")
if not fn then
  log("NO HTTP FUNC")
  flush()
  return
end

local tests = {
  { name = "https_httpbin",  url = "https://httpbin.org/post" },
  { name = "http_httpbin",   url = "http://httpbin.org/post" },
  { name = "http_example",   url = "http://example.com/" },
  { name = "http_selfip",    url = "http://192.168.96.160:8790/" },
}

for _, t in ipairs(tests) do
  local ok, res = pcall(fn, { Url = t.url, Method = "GET" })
  if ok and type(res) == "table" then
    local status = res.StatusCode or res.Status or res.status or "?"
    log("%s -> OK status=%s", t.name, tostring(status))
  else
    log("%s -> FAIL %s", t.name, tostring(res))
  end
end

flush()
