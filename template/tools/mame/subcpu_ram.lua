-- subcpu_ram.lua - a sub-CPU's RAM every frame, with commands INJECTED, so a headless
-- model of it (beeb_port_kit/mame/z80sub.py) can be scored RAM for RAM.
--
-- Fork this into your project's tools/mame/; keep this header.
--
-- From 1942-beeb's snd_ram.lua (Layer 8, 2026-09-10). 1942's sound Z80 does all its
-- work in an IRQ whose first instruction is `inc ($4000)`, so ($4000) counts IRQs and
-- its step per frame IS the IRQ rate (4 a frame, measured). Everything it writes to
-- its two AYs is a function of its 2K of RAM, so a headless model is exact if its RAM
-- matches this capture at the same IRQ: probe_sound.py scored 2,859 frames matching,
-- 146 torn (MAME sampled mid-IRQ, each followed by a match), 0 wrong.
--
-- INJECTION. Attract mode sends no sound commands, so commands are pushed into the
-- MAIN CPU's own request ring, exactly as its sender does (1942: $1178 writes ($E222)'s
-- pointer into the ring at $E200-$E21F; its IRQ pops one a frame into the latch) -
-- the command then travels the real path, timing included. Or poke the latch directly
-- (INJECT_MODE=poke) if the game has no ring - and say so where you report it.
--
-- RUN IT ON A CLONE if the parent is busy: MAME will not run two instances of one
-- machine, but a clone that shares the sub-CPU's ROM runs beside an interactive
-- session. Confirm the share by CRC (-listxml) and the sender's bytes by disassembly
-- first: 1942a's sr-01.c11 has the parent's CRC bd87f06b and the same $1178/$0172.
--
--   SUB_SPEC      REQUIRED record spec on the SUB CPU (records.py's grammar)
--                 GAME: 1942: f:frame;latch:bytes@6000;ram:bytes@4000-47ff
--   SUB_CPU       default :audiocpu
--   INJECT        "11@100,05@600": command (hex) @ frame (decimal)
--   INJECT_MODE   ring (default) or poke
--   INJECT_RING_PTR   address of the ring's 16-bit write pointer (hex)   GAME: e222
--   INJECT_RING_MASK  the pointer's low-byte wrap mask (hex)             GAME: 1f
--   INJECT_ADDR   for poke: the latch address on INJECT_CPU (hex)
--   INJECT_CPU    default :maincpu
-- Writes subcpu.bin + schema.txt.
local here = os.getenv("MAME_LUA_DIR")
if not here or here == "" then
  here = debug.getinfo(1, "S").source:match("^@(.*[/\\])") or "./"
end
if not here:match("[/\\]$") then here = here .. "/" end
local C = dofile(here .. "_compat.lua")

C.main(function()
  local f = C.open("subcpu.bin", "wb")                     -- open first
  local SPEC = assert(C.env("SUB_SPEC"), "SUB_SPEC is not set")
  local SUB = C.env("SUB_CPU", ":audiocpu")
  local items = C.parse_spec(SPEC)
  C.write_schema(SPEC, "subcpu.bin", SUB)
  local sub = C.space(SUB)
  local main = C.space(C.env("INJECT_CPU", ":maincpu"))
  local cmds = {}
  for c, at in string.gmatch(C.env("INJECT", ""), "(%x+)@(%d+)") do
    cmds[tonumber(at)] = tonumber(c, 16)
  end
  local MODE = C.env("INJECT_MODE", "ring")
  local PTR, MASK, ADDR = C.hex("INJECT_RING_PTR"), C.hex("INJECT_RING_MASK", 0xFF), C.hex("INJECT_ADDR")
  if next(cmds) then
    assert((MODE == "ring" and PTR) or (MODE == "poke" and ADDR),
           "INJECT needs INJECT_RING_PTR (ring) or INJECT_ADDR (poke)")
  end
  C.add_frame(function(n)
    local c = cmds[n]
    if not c then return end
    if MODE == "ring" then
      local p = main:read_u8(PTR) | (main:read_u8(PTR + 1) << 8)
      main:write_u8(p, c)
      p = (p & 0xFF00) | (((p & 0xFF) & ~MASK) | (((p & 0xFF) + 1) & MASK))
      main:write_u8(PTR, p & 0xFF)
      main:write_u8(PTR + 1, p >> 8)
    else
      main:write_u8(ADDR, c)
    end
    C.note("inject.txt", string.format("frame %d: command %02X (%s)", n, c, MODE))
  end, "drive")
  C.add_frame(function(n) f:write(C.pack(items, sub, n)) end, "record")
  if not C.env("CAPTURE_FRAMES") then
    C.add_frame(function(n) if n >= 3000 then C.done("SUBCPU default cap") end end, "record")
  end
  C.start()
end)
