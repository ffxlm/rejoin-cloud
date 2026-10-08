--[[
  gui_http_probe.lua — GUI ยืนยัน autoexec + เทสต์ HTTP vs HTTPS
  - GUI: กล่องมุมซ้ายบน มีตัวนับวิ่ง (พิสูจน์ autoexec ทำงานจริง)
  - เทสต์: https vs http vs self-IP
  รันอัตโนมัติผ่าน Autoexecute
]]

-- ===== GUI =====
local guiOK = false
pcall(function()
  local parent = (type(gethui) == "function" and gethui()) or game:GetService("CoreGui")
  local sg = Instance.new("ScreenGui")
  sg.Name = "RejoinProbe"
  sg.ResetOnSpawn = false
  sg.IgnoreGuiInset = true
  sg.Parent = parent

  local lbl = Instance.new("TextLabel")
  lbl.Size = UDim2.new(0, 420, 0, 40)
  lbl.Position = UDim2.new(0, 10, 0, 10)
  lbl.BackgroundColor3 = Color3.fromRGB(0, 0, 0)
  lbl.BackgroundTransparency = 0.25
  lbl.TextColor3 = Color3.fromRGB(0, 255, 0)
  lbl.TextScaled = true
  lbl.Font = Enum.Font.Code
  lbl.TextXAlignment = Enum.TextXAlignment.Left
  lbl.Parent = sg

  local n = 0
  task.spawn(function()
    while true do
      n = n + 1
      lbl.Text = ("  REJOIN autoexec OK  |  %ds  |  %s"):format(n, os.date("%H:%M:%S"))
      task.wait(1)
    end
  end)
  guiOK = true
end)

-- ===== HTTP TESTS =====
local lines = {}
local function log(fmt, ...)
  local ok, msg = pcall(string.format, fmt, ...)
  if not ok then msg = tostring(fmt) end
  table.insert(lines, msg)
end
local function flush()
  local text = "GUI_HTTP_PROBE\n" .. table.concat(lines, "\n") .. "\n"
  if type(writefile) == "function" then pcall(writefile, "gui_http_probe.log", text) end
  if type(print) == "function" then pcall(print, text) end
end

local fn = nil
if type(request) == "function" then fn = request
elseif type(http_request) == "function" then fn = http_request
elseif type(syn) == "table" and type(syn.request) == "function" then fn = syn.request
elseif type(http) == "table" and type(http.request) == "function" then fn = http.request
end

log("GUI_HTTP_PROBE START guiOK=%s", tostring(guiOK))

if fn then
  local tests = {
    { name = "https_httpbin", url = "https://httpbin.org/post" },
    { name = "http_httpbin",  url = "http://httpbin.org/post" },
    { name = "http_example",  url = "http://example.com/" },
    { name = "http_selfip",   url = "http://192.168.96.160:8790/" },
  }
  for _, t in ipairs(tests) do
    local ok, res = pcall(fn, { Url = t.url, Method = "GET" })
    if ok and type(res) == "table" then
      log("%s -> OK status=%s", t.name, tostring(res.StatusCode or res.Status or res.status or "?"))
    else
      log("%s -> FAIL %s", t.name, tostring(res))
    end
  end
else
  log("NO HTTP FUNC")
end

flush()
