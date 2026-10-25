-- capture_ram.lua - per-frame RAM records, laid out by a spec the Python reader shares.
--
-- Fork this into your project's tools/mame/; keep this header.
--
-- From 1942-beeb's fullgame.lua (all 32 stages, 242,100 frames, the capture most of the
-- port's later work was scored against), enemy.lua, capture_play.lua and map.lua, which
-- each hard-coded a layout that a Python reader then had to repeat by hand. Here the
-- layout is CAPTURE_SPEC, written beside the data as schema.txt, and read back by
-- beeb_port_kit.mame.records.load_capture - one schema for writer and reader.
--
--   CAPTURE_SPEC   REQUIRED. e.g. (1942's whole-game record, shortened):
--                  f:frame;g:bytes@e103,e102,e101,e0d2,e0d3;spr:bytes@cc00-cc7f;obj:slots@e400,10,30,30
--   CAPTURE_FILE   data file in CAPTURE_DIR (default ram.bin)
--   CAPTURE_CPU    device tag (default :maincpu)    CAPTURE_SPACE  (default program)
--   CAPTURE_FROM   first frame to record (default 1)
--   CAPTURE_EVERY  record every Nth frame (default 1). A capture sampled every 4th frame
--                  compared with a screenshot of a frame in between is up to one scroll
--                  step out: 97% collapsed to 25% in 1942 (arcade-facts s5). Compare only
--                  on sampled frames.
--   CAPTURE_FRAMES stop after this many frames (default 3000 here)
--   STOP_ADDR, STOP_VALUE   also stop when this byte reads this value (hex both)
--
-- Keep large captures OUTSIDE the repository (1942's whole game was 92 MB).
-- And remember: a state byte that is constant in the capture has not been measured
-- (1942 BUGS.md #12) - drive it (hold_byte, force_input, invincible, autopilot).
local here = os.getenv("MAME_LUA_DIR")
if not here or here == "" then
  here = debug.getinfo(1, "S").source:match("^@(.*[/\\])") or "./"
end
if not here:match("[/\\]$") then here = here .. "/" end
local C = dofile(here .. "_compat.lua")

C.main(function()
  local FILE = C.env("CAPTURE_FILE", "ram.bin")
  local f = C.open(FILE, "wb")                       -- OPEN FIRST: see _compat.lua
  local SPEC = assert(C.env("CAPTURE_SPEC"), "CAPTURE_SPEC is not set")
  local CPU = C.env("CAPTURE_CPU", ":maincpu")
  local items = C.parse_spec(SPEC)
  C.write_schema(SPEC, FILE, CPU)
  local mem = C.space(CPU, C.env("CAPTURE_SPACE", "program"))
  local FROM, EVERY = C.num("CAPTURE_FROM", 1), C.num("CAPTURE_EVERY", 1)
  local STOP_ADDR, STOP_VALUE = C.hex("STOP_ADDR"), C.hex("STOP_VALUE")
  if not C.env("CAPTURE_FRAMES") and not STOP_ADDR then
    C.add_frame(function(n) if n >= 3000 then C.done("CAPTURE default cap") end end, "record")
  end
  local written = 0
  C.add_frame(function(n)
    if n >= FROM and (n - FROM) % EVERY == 0 then
      f:write(C.pack(items, mem, n))
      written = written + 1
    end
    if STOP_ADDR and mem:read_u8(STOP_ADDR) == STOP_VALUE then
      C.done(string.format("CAPTURE stop: $%04X = %02X, %d records", STOP_ADDR, STOP_VALUE, written))
    end
  end, "record")
  C.start()
end)
