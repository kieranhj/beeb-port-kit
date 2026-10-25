-- invincible.lua - make the player unkillable so a long capture reaches the whole game.
--
-- Fork this into your project's tools/mame/; keep this header.
--
-- From 1942-beeb's fullgame.lua (2026-09-16): 242,100 frames, all 32 stages, all four
-- bosses fought and shot down, the ending and back to attract - the capture most of
-- that port's later work was scored against. Two things made it work, and both are
-- the pattern, not 1942's addresses:
--
-- THE PATTERN: REDIRECT INTO THE GAME'S OWN "ALREADY HIT" PATH. Both of 1942's
-- player-hit tests open by reading the "already hit" latch and skip the test while it
-- is set:   $2E8E / $3396   3A A5 E0   ld a,($E0A5)   ->   3E 01 00   ld a,1 : nop
-- so the tests take the game's own skip while the latch itself stays 0 - which is what
-- the kill-scoring reads, so kills still score. Do NOT poke the lives counter or the
-- death state: that is a different game, and the capture would measure it.
-- CHECK IT HELD: the lives byte must never fall in the output (fullgame.py check).
--
-- THE CHECKSUM CHECKLIST. A game may checksum its own ROM IN PLAY. 1942 has a task at
-- $7112 that XORs a stretch of ROM, compares it with ($001C) and on a mismatch prints
-- a message and halts at $7166 (`di : halt`) - minutes after the patch, which is what
-- makes it hard to see. 1942's two invincibility patches happened to cancel each
-- other's XOR and ran 400,000 frames; the autopilot's per-frame stick byte did not,
-- and the first autopilot run froze at frame 69,428 with PC = $7167.
--   1. Before a long run, read patches.txt: every patch logs the running XOR and 8-bit
--      sum delta. Zero for both means a simple XOR or SUM check cannot see the set.
--   2. If either is non-zero, or the game freezes, run with TRACE_FROM a little before
--      the freeze: trace.txt gets the CPU's PC and SP every frame, and a PC parked on
--      a `halt` names the check.
--   3. Disassemble round it (debugscript.txt's dasm) and patch the COMPARE'S BRANCH:
--      1942: $7137  28 2F  jr z,$7168  ->  18 2F  jr $7168  ("the sum matched").
--   4. Grep the ROM for other checks before calling it done; a second one may sit in
--      the attract cycle or the stage init.
--
--   INV_PATCHES   ADDR:EXPECT:NEW[,...] hex               GAME: 1942's whole set:
--                 2e8e:3aa5e0:3e0100,3396:3aa5e0:3e0100,7137:282f:182f
--   INV_REGION    default :maincpu
--   INV_FROM      frame to apply (default 1: before the game has run a frame)
--   TRACE_FROM    log PC and SP to trace.txt every frame from here (decimal)
--   TRACE_CPU     default :maincpu
local here = os.getenv("MAME_LUA_DIR")
if not here or here == "" then
  here = debug.getinfo(1, "S").source:match("^@(.*[/\\])") or "./"
end
if not here:match("[/\\]$") then here = here .. "/" end
local C = dofile(here .. "_compat.lua")

C.main(function()
  local TRACE_FROM = C.num("TRACE_FROM")
  local ft = TRACE_FROM and C.open("trace.txt", "w")          -- open first
  local list = C.patch_list(assert(C.env("INV_PATCHES"), "INV_PATCHES is not set"))
  local REGION, FROM = C.env("INV_REGION", ":maincpu"), C.num("INV_FROM", 1)
  local CPU = C.env("TRACE_CPU", ":maincpu")
  local applied = false
  local function apply(n)
    for _, p in ipairs(list) do C.patch(REGION, p[1], p[2], p[3], "invincible") end
    applied = true
    C.note("patches.txt", string.format("-- %d patch(es) applied at frame %d; XOR delta %02X, " ..
           "sum delta %02X%s", #list, n, C.xor_delta, C.sum_delta,
           (C.xor_delta ~= 0 or C.sum_delta ~= 0) and " - CHECK FOR A ROM CHECKSUM" or ""))
  end
  if FROM <= 0 then apply(0) end
  C.add_frame(function(n)
    if not applied and n >= FROM then apply(n) end
    if ft and n >= TRACE_FROM then
      ft:write(string.format("%d PC %04X SP %04X\n", n, C.reg(CPU, "PC"), C.reg(CPU, "SP")))
      ft:flush()
    end
  end, "drive")
  C.start()
end)
