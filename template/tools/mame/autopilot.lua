-- autopilot.lua - SKELETON: play the game where the recording stops, so a capture
-- reaches content no human run reached.
--
-- Fork this into your project's tools/mame/; keep this header. The steering rule is
-- GAME-SPECIFIC and every line marked GAME: is a placeholder to rewrite.
--
-- From 1942-beeb's fullgame.lua. A boss stage never ends until the boss is shot down,
-- and the first whole-game run sat 355,000 frames on stage 7 with an idle ship once
-- kc2.inp's input ran out. So from AUTO_FROM the input read is REWRITTEN EVERY FRAME
-- (force_input.lua's patch, with the value byte changing), fire pulsed four frames on
-- and four off, steering under the nearest live enemy. Run it with invincible.lua as
-- a plugin, and remember the per-frame byte changes the ROM's checksum every frame:
-- that is exactly what froze 1942's first autopilot run (invincible.lua's checklist).
--
--   AUTO_FROM     first frame (decimal; 1942: 42300, where kc2.inp's input ends)
--   AUTO_PATCH    ADDR:EXPECT:NEW with {v} - the input read  GAME: 1bfb:cd352d:3e{v}00
--   AUTO_REGION   default :maincpu
--   AUTO_FIRE     the fire bit (hex)                         GAME: 1942: 10
--   AUTO_LEFT, AUTO_RIGHT  stick bits (hex)                  GAME: 1942: 02, 01
--   AUTO_HOLD     bits ORed in every frame (hex, default 0)  GAME: 1942: 08 held UP
--   AUTO_PLAYER   the player's position byte on the steering axis (hex)  GAME: e10e
--   AUTO_SLOTS    BASE,N,STRIDE,LIVEOFF,POSOFF of the object table (hex)  GAME: e400,10,30,0,e
--   PARK=1        neither steer nor fire: a ship that sits where it started
local here = os.getenv("MAME_LUA_DIR")
if not here or here == "" then
  here = debug.getinfo(1, "S").source:match("^@(.*[/\\])") or "./"
end
if not here:match("[/\\]$") then here = here .. "/" end
local C = dofile(here .. "_compat.lua")

C.main(function()
  C.note("autopilot.txt", "-- autopilot.lua")
  local FROM = C.num("AUTO_FROM", 1)
  local P = assert(C.env("AUTO_PATCH"), "AUTO_PATCH is not set")
  local a, e, nw = P:match("^%s*(%x+):(%x+):([%x{}v]+)%s*$")
  assert(a and nw:find("{v}", 1, true), "AUTO_PATCH is not ADDR:EXPECT:NEW with {v} - " .. P)
  local addr = C.parse_hex(a)
  local vpos = (nw:find("{v}", 1, true) - 1) // 2          -- byte offset of the value
  local REGION = C.env("AUTO_REGION", ":maincpu")
  local FIRE, LEFT, RIGHT = C.hex("AUTO_FIRE", 0), C.hex("AUTO_LEFT", 0), C.hex("AUTO_RIGHT", 0)
  local HOLD, PARK = C.hex("AUTO_HOLD", 0), C.env("PARK") == "1"
  local PLAYER = C.hex("AUTO_PLAYER")
  local slots = C.hexlist(C.env("AUTO_SLOTS", ""))
  local mem = C.space(":maincpu")
  local region, patched = nil, false

  -- GAME: the steering rule. 1942's: aim under the live enemy nearest the ship
  -- on the axis the stick moves along. Replace with whatever reaches your content.
  local function choose(n)
    local v = HOLD
    if not PARK and (n // 4) % 2 == 0 then v = v | FIRE end
    if PARK or not PLAYER or #slots < 5 then return v end
    local px, best, bd = mem:read_u8(PLAYER), nil, 1e9
    for s = 0, slots[2] - 1 do
      local b = slots[1] + s * slots[3]
      if mem:read_u8(b + slots[4]) ~= 0 then
        local ex = mem:read_u8(b + slots[5])
        if math.abs(ex - px) < bd then best, bd = ex, math.abs(ex - px) end
      end
    end
    if best and best > px + 3 then v = v | RIGHT elseif best and best < px - 3 then v = v | LEFT end
    return v
  end

  C.add_frame(function(n)
    if n < FROM then return end
    local v = choose(n) & 0xFF
    if not patched then
      C.patch(REGION, addr, e, (nw:gsub("{v}", string.format("%02X", v))), "autopilot")
      region, patched = C.region(REGION), true
    else
      region:write_u8(addr + vpos, v)   -- after the asserted first patch, the value only
    end
  end, "drive")
  C.start()
end)
