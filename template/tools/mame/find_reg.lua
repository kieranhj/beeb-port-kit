-- find_reg.lua - find a hardware register BY CAUSE: write every candidate value to every
-- candidate address and see which one changes what you can read.
--
-- Fork this into your project's tools/mame/; keep this header.
--
-- From 1942-beeb's bankreg.lua (2026-09-08, arcade-facts s7). 1942's $8000-$BFFF window
-- holds one of three ROMs and nothing said where the bank select was. Writing 0-3 to
-- every address in $C000-$CFFF and reading the window back named $C806 and nothing
-- else, and the mapping was then byte-exact against the ROM images (0 = srb-05,
-- 1 = srb-06 with $A000-$BFFF reading $FF, 2 = srb-07, 3 = unmapped). Recalled, the
-- register would have been a guess; found by cause it is a measurement.
--
-- This WRECKS the running game - fine: the session is thrown away. Each address's
-- original value is written back after its test, but a write can have side effects
-- (a watchdog kick, a sound latch, a coin counter) that no restore undoes.
--
--   FIND_AT       frame to probe at (decimal, default 1000 - past the boot)
--   FIND_LO, FIND_HI   the candidate address range (hex)       GAME: 1942: c000, cfff
--   FIND_VALUES   values to write (hex list, default 0,1,2,3)
--   FIND_WATCH    addresses whose bytes make the fingerprint (hex list or ranges)
--                 GAME: 1942: one byte every $400 of the window, 8000,8400,...,bc00
--   FIND_SKIP     ranges never to write (hex list of LO-HI): RAM the game needs to
--                 survive the probe, the sprite or tile RAM you would only scribble on
--   FIND_CPU      default :maincpu
-- Writes find_reg.txt: the baseline fingerprint and every (address, value) that changed it.
local here = os.getenv("MAME_LUA_DIR")
if not here or here == "" then
  here = debug.getinfo(1, "S").source:match("^@(.*[/\\])") or "./"
end
if not here:match("[/\\]$") then here = here .. "/" end
local C = dofile(here .. "_compat.lua")

C.main(function()
  local f = C.open("find_reg.txt", "w")                    -- open first
  local AT = C.num("FIND_AT", 1000)
  local LO, HI = assert(C.hex("FIND_LO"), "FIND_LO not set"), assert(C.hex("FIND_HI"), "FIND_HI not set")
  local VALUES = C.hexlist(C.env("FIND_VALUES", "0,1,2,3"))
  local WATCH = C.hexlist(assert(C.env("FIND_WATCH"), "FIND_WATCH not set"))
  local skip = {}
  for lo, hi in string.gmatch(C.env("FIND_SKIP", ""), "(%x+)-(%x+)") do
    skip[#skip + 1] = {C.parse_hex(lo), C.parse_hex(hi)}
  end
  local mem = C.space(C.env("FIND_CPU", ":maincpu"))
  local function fp()
    local t = {}
    for i = 1, #WATCH do t[#t + 1] = string.format("%02X", mem:read_u8(WATCH[i])) end
    return table.concat(t)
  end
  local function skipped(a)
    for _, r in ipairs(skip) do if a >= r[1] and a <= r[2] then return true end end
    return false
  end
  C.add_frame(function(n)
    if n ~= AT then return end
    local base = fp()
    f:write("baseline " .. base .. "\n")
    local hits = 0
    for a = LO, HI do
      if not skipped(a) then
        local old = mem:read_u8(a)
        for _, v in ipairs(VALUES) do
          mem:write_u8(a, v)
          local now = fp()
          if now ~= base then
            f:write(string.format("CHANGE $%04X <- %02X : %s\n", a, v, now))
            hits = hits + 1
          end
        end
        mem:write_u8(a, old)
      end
    end
    f:write(string.format("final %s   %d change(s)\n", fp(), hits))
    C.done("FINDREG")
  end, "record")
  C.start()
end)
