-- orient.lua - the RAM a screen is built from, and a screenshot, ON THE SAME FRAME, so
-- the cabinet's rotation can be measured rather than reasoned about.
--
-- Fork this into your project's tools/mame/; keep this header.
--
-- From 1942-beeb's orient.lua (2026-09-07, decision 13). The tilemap RAM and the
-- scroll counter were captured with a snapshot of the same frame; the visible
-- tilemap was rebuilt in raw space and beeb_port_kit.mame.orient.score_rotations
-- compared it under all four rotations: ROT270 96.3%, the others 46-48%. Pick a
-- frame with ASYMMETRIC content - 1942's sea tile is diagonally hatched, which is
-- what made the test discriminate; a symmetric scene passes a broken rotation.
--
-- The snapshot works under -video none (measured, MAME 0.177, 2026-10-25), and MAME
-- writes it to ITS OWN snap/<game>/NNNN.png, not CAPTURE_DIR: move it out afterwards,
-- and note which number it took.
-- To get into play first, load force_input as a plugin with a coin/start schedule
-- (MAME_PLUGINS=force_input FORCE_FIELDS="Coin 1@60-80;1 Player Start@150-170").
--
--   ORIENT_FRAME  the frame (decimal, default 4000). If your capture elsewhere samples
--                 every Nth frame, pick a multiple of N (arcade-facts s5)
--   ORIENT_SPEC   REQUIRED: what to dump, in records.py's grammar
--                 GAME: 1942: scroll:bytes@e0d2,e0d3;tiles:bytes@d800-dbff
--   ORIENT_CPU    default :maincpu
-- Writes orient.bin (one record) + schema.txt, and one MAME snapshot.
local here = os.getenv("MAME_LUA_DIR")
if not here or here == "" then
  here = debug.getinfo(1, "S").source:match("^@(.*[/\\])") or "./"
end
if not here:match("[/\\]$") then here = here .. "/" end
local C = dofile(here .. "_compat.lua")

C.main(function()
  local f = C.open("orient.bin", "wb")                     -- open first
  local SPEC = assert(C.env("ORIENT_SPEC"), "ORIENT_SPEC is not set")
  local CPU = C.env("ORIENT_CPU", ":maincpu")
  local items = C.parse_spec(SPEC)
  C.write_schema(SPEC, "orient.bin", CPU)
  local mem = C.space(CPU)
  local AT = C.num("ORIENT_FRAME", 4000)
  C.add_frame(function(n)
    if n ~= AT then return end
    f:write(C.pack(items, mem, n))
    C.video():snapshot()
    C.done("ORIENTDONE")
  end, "record")
  C.start()
end)
