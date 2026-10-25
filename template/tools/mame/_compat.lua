-- _compat.lua - the shared half of every harness in this folder.
--
-- Fork this into your project's tools/mame/; keep this header.
--
-- From 1942-beeb's tools/mame/*.lua (2026-09-07 to 10-14, MAME 0.177), where every
-- harness repeated the same dozen lines and three of them were traps:
--
--   * TWO LUA APIs. 0.177 is the OLD one - manager:machine(), mach:memory(),
--     mach:ioport(), emu.register_frame_done, no install_write_tap - and current
--     MAME documentation describes the NEW one (manager.machine, .memory, .ioport,
--     emu.add_machine_frame_notifier). Each accessor here tries the old form and then
--     the new under pcall, so one harness runs on both.
--   * THE SILENT HANG. A Lua error in an autoboot script does not stop MAME: it runs
--     on with no output and no message until something kills it. 1942's upclamp.lua
--     threw on `mach.memory` (a method in 0.177) BEFORE it had opened its output,
--     and the session ran for ever (arcade-facts s8). So: open the output first, and
--     C.main() / the frame dispatcher catch every error, write it to lua_error.txt in
--     CAPTURE_DIR, and EXIT - which the runner (beeb_port_kit.mame.runner) reports.
--   * ROM PATCHES THAT HIT THE WRONG BYTES. C.patch() asserts the original bytes
--     before writing, logs every patch to patches.txt, and keeps a running XOR and
--     8-bit sum delta - because a game that checksums its ROM in play halts minutes
--     after an unbalanced patch (1942: a task at $7112, halt at $7166; see
--     invincible.lua's checklist).
--
-- And one frame dispatcher, so harnesses compose: MAME_PLUGINS="hold_byte,force_input"
-- loads those templates INTO the running one. Handlers registered as "drive" (holding
-- a byte, forcing input, patching) run before those registered as "record", every frame.
--
-- Environment, read by everything:
--   CAPTURE_DIR      where output goes (the runner makes it absolute; MAME's cwd is its own)
--   CAPTURE_FRAMES   stop after this many frames (unset: the harness's own stop rule)
--   MAME_PLUGINS     comma-separated templates to load alongside this one
--   MAME_LUA_DIR     this folder (the runner sets it; otherwise found from the script path)
--
-- Every address and byte string in an environment variable is HEX.

if _G.BEEB_MAME_COMPAT then return _G.BEEB_MAME_COMPAT end
local C = {}
_G.BEEB_MAME_COMPAT = C

C.DIR = os.getenv("CAPTURE_DIR") or "."
C.HERE = os.getenv("MAME_LUA_DIR")
if not C.HERE or C.HERE == "" then
  local ok, src = pcall(function() return debug.getinfo(1, "S").source end)
  C.HERE = (ok and src and src:match("^@(.*[/\\])")) or "./"
end
if not C.HERE:match("[/\\]$") then C.HERE = C.HERE .. "/" end
C.files, C.drive, C.record, C.patches = {}, {}, {}, {}
C.n, C.started, C.exiting = 0, false, false
C.xor_delta, C.sum_delta = 0, 0

-- --- environment ----------------------------------------------------------------------
function C.env(name, default)
  local v = os.getenv(name)
  if v == nil or v == "" then return default end
  return v
end

function C.num(name, default)           -- DECIMAL: frame counts and the like
  local v = C.env(name)
  if v == nil then return default end
  return assert(tonumber(v), name .. " is not a number: " .. v)
end

function C.parse_hex(s)
  s = s:lower():gsub("^%s+", ""):gsub("%s+$", ""):gsub("^0x", ""):gsub("^%$", ""):gsub("^&", "")
  return assert(tonumber(s, 16), "not hex: '" .. s .. "'")
end

function C.hex(name, default)           -- HEX: addresses and byte values
  local v = C.env(name)
  if v == nil then return default end
  return C.parse_hex(v)
end

function C.hexlist(s)                   -- "e103,e102,cc00-cc03" -> {...}
  local out = {}
  for part in string.gmatch(s or "", "[^,]+") do
    local lo, hi = part:match("^%s*([^-]+)-([^-]+)%s*$")
    if lo then
      for a = C.parse_hex(lo), C.parse_hex(hi) do out[#out + 1] = a end
    elseif part:match("%S") then
      out[#out + 1] = C.parse_hex(part)
    end
  end
  return out
end

function C.bytestr(s)                   -- "CD352D" -> {0xCD, 0x35, 0x2D}
  s = s:gsub("%s", "")
  assert(#s % 2 == 0, "odd-length byte string: " .. s)
  local out = {}
  for i = 1, #s, 2 do out[#out + 1] = C.parse_hex(s:sub(i, i + 1)) end
  return out
end

-- --- the machine, both APIs -------------------------------------------------------
local function try(f)
  local ok, v = pcall(f)
  if ok and v ~= nil and type(v) ~= "function" then return v end
  return nil
end

function C.machine()
  if not C._mach then
    C._mach = try(function() return manager:machine() end)        -- 0.177..0.226
           or try(function() return manager.machine end)          -- 0.227+
    assert(C._mach, "no machine: neither manager:machine() nor manager.machine")
  end
  return C._mach
end

function C.space(cpu, name)
  local d = assert(C.machine().devices[cpu or ":maincpu"], "no device " .. tostring(cpu))
  return assert(d.spaces[name or "program"], "no space " .. tostring(name) .. " on " .. cpu)
end

function C.region(tag)
  local m = C.machine()
  local r = try(function() return m:memory().regions[tag] end)
         or try(function() return m.memory.regions[tag] end)
  return assert(r, "no memory region " .. tostring(tag))
end

function C.ioport()
  local m = C.machine()
  return assert(try(function() return m:ioport() end) or try(function() return m.ioport end),
                "no ioport manager")
end

function C.video()
  local m = C.machine()
  return assert(try(function() return m:video() end) or try(function() return m.video end),
                "no video manager")
end

function C.reg(cpu, name)               -- a CPU register: C.reg(":maincpu", "PC")
  return C.machine().devices[cpu].state[name].value
end

function C.field(name)                  -- an input field by its name, on any port
  for tag, port in pairs(C.ioport().ports) do
    for fname, f in pairs(port.fields) do
      if fname == name then return f, port, tag end
    end
  end
  error("no input field named '" .. name .. "'")
end

-- --- output ---------------------------------------------------------------------------
function C.open(name, mode)
  local f = assert(io.open(C.DIR .. "/" .. name, mode or "wb"),
                   "cannot open " .. C.DIR .. "/" .. name .. " - is CAPTURE_DIR absolute?")
  C.files[#C.files + 1] = f
  return f
end

function C.note(name, text)             -- append a line to a text log in CAPTURE_DIR
  C._notes = C._notes or {}
  local f = C._notes[name]
  if not f then f = C.open(name, "w"); C._notes[name] = f end
  f:write(text .. "\n")
  f:flush()
end

function C.done(msg)
  if C.exiting then return end
  C.exiting = true
  for _, f in ipairs(C.files) do pcall(function() f:close() end) end
  print((msg or "DONE") .. string.format(" frames=%d", C.n))
  C.machine():exit()
end

function C.fail(err)
  local f = io.open(C.DIR .. "/lua_error.txt", "w")
  if f then f:write(tostring(err) .. "\n"); f:close() end
  print("LUA ERROR " .. tostring(err))
  C.done("FAILED")
end

function C.main(fn)                     -- run a script body; any error exits, named
  local ok, err = pcall(fn)
  if not ok then C.fail(err) end
end

-- --- ROM patches ------------------------------------------------------------------------
-- expect/new are byte tables or hex strings. Asserts every original byte first.
function C.patch(region_tag, addr, expect, new, why)
  if type(expect) == "string" then expect = C.bytestr(expect) end
  if type(new) == "string" then new = C.bytestr(new) end
  local r = C.region(region_tag or ":maincpu")
  for i, b in ipairs(expect) do
    local got = r:read_u8(addr + i - 1)
    assert(got == b, string.format("patch $%04X+%d reads %02X, expected %02X: wrong ROM, " ..
           "wrong address, or already patched", addr, i - 1, got, b))
  end
  for i, b in ipairs(new) do
    local old = r:read_u8(addr + i - 1)
    C.xor_delta = C.xor_delta ~ old ~ b
    C.sum_delta = (C.sum_delta + b - old) & 0xFF
    r:write_u8(addr + i - 1, b)
  end
  C.patches[#C.patches + 1] = {addr = addr, expect = expect, new = new, why = why}
  C.note("patches.txt", string.format("frame %d  $%04X  %s -> %s  %s   (running XOR delta %02X, sum delta %02X)",
         C.n, addr, table.concat((function() local t = {} for _, b in ipairs(expect) do t[#t+1] = string.format("%02X", b) end return t end)()),
         table.concat((function() local t = {} for _, b in ipairs(new) do t[#t+1] = string.format("%02X", b) end return t end)()),
         why or "", C.xor_delta, C.sum_delta))
end

-- "ADDR:EXPECT:NEW,ADDR:EXPECT:NEW" -> {{addr, expect, new}, ...}
function C.patch_list(s)
  local out = {}
  for item in string.gmatch(s or "", "[^,]+") do
    local a, e, n = item:match("^%s*(%x+):(%x+):(%x+)%s*$")
    assert(a, "patch item is not ADDR:EXPECT:NEW - " .. item)
    out[#out + 1] = {C.parse_hex(a), e, n}
  end
  return out
end

-- --- records (beeb_port_kit/mame/records.py parses the SAME spec) -----------------------
function C.parse_spec(spec)
  local items = {}
  for raw in string.gmatch(spec, "[^;]+") do
    local item = raw:gsub("^%s+", ""):gsub("%s+$", "")
    if item ~= "" then
      local head, args = item:match("^([^@]+)@?(.*)$")
      local name, kind = head:match("^%s*([^:%s]+)%s*:%s*(%a+)%s*$")
      assert(name, "spec item is not name:kind[@args] - " .. item)
      local it = {name = name, kind = kind}
      if kind == "frame" then
      elseif kind == "bytes" then
        it.addrs = C.hexlist(args)
        assert(#it.addrs > 0, "bytes field " .. name .. " has no addresses")
      elseif kind == "slots" then
        local v = C.hexlist(args)
        assert(#v >= 4 and #v <= 6, "slots wants BASE,N,STRIDE,LEN[,OFF[,MASK]] - " .. item)
        it.base, it.n, it.stride, it.len = v[1], v[2], v[3], v[4]
        it.off, it.mask = v[5] or 0, v[6] or 0xFF
      else
        error("unknown kind " .. kind .. " (frame, bytes, slots)")
      end
      items[#items + 1] = it
    end
  end
  assert(#items > 0, "empty spec")
  return items
end

function C.pack(items, mem, n)
  local t = {}
  for _, it in ipairs(items) do
    if it.kind == "frame" then
      t[#t + 1] = string.char(n & 0xff, (n >> 8) & 0xff, (n >> 16) & 0xff, (n >> 24) & 0xff)
    elseif it.kind == "bytes" then
      for _, a in ipairs(it.addrs) do t[#t + 1] = string.char(mem:read_u8(a)) end
    else
      local live = {}
      for s = 0, it.n - 1 do
        local b = it.base + s * it.stride
        if (mem:read_u8(b + it.off) & it.mask) ~= 0 then
          local o = { string.char(s) }
          for k = 0, it.len - 1 do o[#o + 1] = string.char(mem:read_u8(b + k)) end
          live[#live + 1] = table.concat(o)
        end
      end
      t[#t + 1] = string.char(#live)
      t[#t + 1] = table.concat(live)
    end
  end
  return table.concat(t)
end

function C.write_schema(spec, data_file, cpu, schema_file)
  local f = assert(io.open(C.DIR .. "/" .. (schema_file or "schema.txt"), "w"))
  f:write(spec .. "\n")
  f:write(string.format("# data=%s cpu=%s - beeb_port_kit.mame.records.load_capture reads this\n",
                        data_file, cpu or ":maincpu"))
  f:close()
end

-- --- the dispatcher ---------------------------------------------------------------------
function C.add_frame(fn, phase)          -- phase "drive" (default) or "record"
  if phase == "record" then C.record[#C.record + 1] = fn else C.drive[#C.drive + 1] = fn end
end

local function tick()
  if C.exiting then return end
  C.n = C.n + 1
  local ok, err = pcall(function()
    for _, h in ipairs(C.drive) do h(C.n) end
    for _, h in ipairs(C.record) do h(C.n) end
  end)
  if not ok then C.fail(err); return end
  if C._cap and C.n >= C._cap then C.done("CAPTURE_FRAMES reached") end
end

function C.load_plugins()
  for name in string.gmatch(C.env("MAME_PLUGINS", ""), "[^,%s]+") do
    C.main(function() dofile(C.HERE .. name .. ".lua") end)
  end
end

function C.start()
  if C.started then return end           -- a plugin's own C.start() is a no-op
  C.started = true
  C._cap = C.num("CAPTURE_FRAMES")
  C.load_plugins()
  if emu.add_machine_frame_notifier then
    C._sub = emu.add_machine_frame_notifier(tick)    -- keep the subscription alive
  else
    emu.register_frame_done(tick)
  end
end

return C
