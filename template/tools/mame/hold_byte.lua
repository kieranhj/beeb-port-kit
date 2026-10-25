-- hold_byte.lua - get the game to a state by HOLDING one byte until it has been taken.
--
-- Fork this into your project's tools/mame/; keep this header.
--
-- From 1942-beeb's stage.lua (2026-09-09, arcade-facts s28). 1942's stage init does
-- `ld a,($E106) : ld ($E103),a` - ($E106) is the PENDING stage - so holding ($E106) at
-- N until the init has run starts the game on stage N+1. And the ATTRACT DEMO plays a
-- real stage with no coin, no input, and no way to lose a life, so any stage could be
-- captured: the recording was never the only way in, and nobody had asked for nine
-- days. Measured: ($E103) follows at frame 638, the map pointers at 639.
--
-- Hold it ONLY until the game has taken it. A harness that keeps writing a byte the
-- game owns hides the transition you are trying to measure.
--
-- Run alone, or as a plugin under a recorder:
--   MAME_PLUGINS=hold_byte  CAPTURE_SPEC=...  ... capture_ram.lua
--
--   HOLD_ADDR    the byte to hold (hex)                      GAME: 1942's e106
--   HOLD_VALUE   the value (hex)
--   HOLD_UNTIL   stop holding after this frame (decimal)     GAME: 1942's 640
--   or HOLD_TAKEN_ADDR + HOLD_TAKEN_VALUE: stop holding HOLD_GRACE frames (default 2)
--                after this byte reads this value - the game has taken it. 1942: e103.
--   HOLD_CPU     default :maincpu
-- Logs hold.txt: the frame the hold was released and why.
local here = os.getenv("MAME_LUA_DIR")
if not here or here == "" then
  here = debug.getinfo(1, "S").source:match("^@(.*[/\\])") or "./"
end
if not here:match("[/\\]$") then here = here .. "/" end
local C = dofile(here .. "_compat.lua")

C.main(function()
  C.note("hold.txt", "-- hold_byte.lua")
  local ADDR = assert(C.hex("HOLD_ADDR"), "HOLD_ADDR is not set")
  local VALUE = assert(C.hex("HOLD_VALUE"), "HOLD_VALUE is not set")
  local UNTIL = C.num("HOLD_UNTIL")
  local TA, TV = C.hex("HOLD_TAKEN_ADDR"), C.hex("HOLD_TAKEN_VALUE")
  local GRACE = C.num("HOLD_GRACE", 2)
  assert(UNTIL or TA, "set HOLD_UNTIL or HOLD_TAKEN_ADDR: a hold with no end hides transitions")
  local mem = C.space(C.env("HOLD_CPU", ":maincpu"))
  local holding, taken_at = true, nil
  C.add_frame(function(n)
    if not holding then return end
    if TA and taken_at == nil and mem:read_u8(TA) == TV then
      taken_at = n
      C.note("hold.txt", string.format("frame %d: $%04X reads %02X - taken", n, TA, TV))
    end
    if (UNTIL and n > UNTIL) or (taken_at and n >= taken_at + GRACE) then
      holding = false
      C.note("hold.txt", string.format("frame %d: released $%04X", n, ADDR))
      return
    end
    mem:write_u8(ADDR, VALUE)
  end, "drive")
  C.start()
end)
