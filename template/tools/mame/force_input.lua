-- force_input.lua - drive the game where no recording went.
--
-- Fork this into your project's tools/mame/; keep this header.
--
-- From 1942-beeb's upclamp.lua and enemy.lua's FORCE_STICK (patching the input read in
-- ROM) and orient.lua (setting ioport fields). Two ways, and why there are two:
--
-- 1. PATCH THE INPUT READ IN ROM. 1942 reads the stick into ($E0A0) every frame at
--    $1BFB, so poking ($E0A0) from Lua is always overwritten before the mover looks at
--    it. Instead the CALL is patched:  $1BFB  CD 35 2D  call $2D35  ->  3E xx 00  ld a,xx : nop
--    and the stick reads xx for ever, nothing else about the frame disturbed. That is
--    how the UP clamp the recording never reached was measured, and how the player
--    was flown into the traffic to measure a death that kieran.inp (which never dies)
--    could not show (1942 BUGS.md #12: the death had been written from the
--    disassembly, and was wrong).
--      FORCE_PATCH   ADDR:EXPECT:NEW, NEW may contain {v}     GAME: 1bfb:cd352d:3e{v}00
--      FORCE_VALUE   the byte {v} becomes (hex)              GAME: 1942: 08 = up, 10 = fire
--      FORCE_FROM    first frame to patch (default 1). Replay an .inp to get into a
--                    game first, then take over
--      FORCE_REGION  default :maincpu
--    A ROM patch changes the ROM's checksum: see invincible.lua's checklist.
--
-- 2. SET INPUT FIELDS, by the names MAME gives them (dips.lua lists every one):
--      FORCE_FIELDS  "Coin 1@60-80;1 Player Start@150-170;P1 Button 1@260-*/4:2"
--                    NAME@FROM-TO (TO may be *), optionally /PERIOD:ON - pressed for
--                    the first ON frames of every PERIOD. Frames are decimal.
--    Gentler than a patch and checksum-safe, but the game sees only what the real
--    input path sees, debounce and all.
--
-- Logs force.txt. Works alone or as a plugin (MAME_PLUGINS=force_input).
local here = os.getenv("MAME_LUA_DIR")
if not here or here == "" then
  here = debug.getinfo(1, "S").source:match("^@(.*[/\\])") or "./"
end
if not here:match("[/\\]$") then here = here .. "/" end
local C = dofile(here .. "_compat.lua")

C.main(function()
  C.note("force.txt", "-- force_input.lua")
  local P = C.env("FORCE_PATCH")
  if P then
    local a, e, nw = P:match("^%s*(%x+):(%x+):([%x{}v]+)%s*$")
    assert(a, "FORCE_PATCH is not ADDR:EXPECT:NEW - " .. P)
    local v = assert(C.env("FORCE_VALUE") or not nw:find("{v}", 1, true) and "00",
                     "FORCE_PATCH has {v} but FORCE_VALUE is not set")
    nw = nw:gsub("{v}", string.format("%02X", C.parse_hex(v)))
    local FROM, done = C.num("FORCE_FROM", 1), false
    C.add_frame(function(n)
      if not done and n >= FROM then
        C.patch(C.env("FORCE_REGION", ":maincpu"), C.parse_hex(a), e, nw, "force_input")
        C.note("force.txt", string.format("frame %d: patched $%s -> %s", n, a, nw))
        done = true
      end
    end, "drive")
  end
  local F = C.env("FORCE_FIELDS")
  if F then
    local sched = {}
    for item in string.gmatch(F, "[^;]+") do
      local name, from, to, per, on = item:match("^%s*(.-)@(%d+)-([%d%*]+)/?(%d*):?(%d*)%s*$")
      assert(name, "FORCE_FIELDS item is not NAME@FROM-TO[/PERIOD:ON] - " .. item)
      sched[#sched + 1] = {field = C.field(name), name = name, from = tonumber(from),
                           to = (to == "*") and math.huge or tonumber(to),
                           per = tonumber(per), on = tonumber(on)}
    end
    C.add_frame(function(n)
      for _, s in ipairs(sched) do
        local v = 0
        if n >= s.from and n <= s.to then
          v = 1
          if s.per then v = ((n - s.from) % s.per < s.on) and 1 or 0 end
        end
        s.field:set_value(v)
      end
    end, "drive")
    C.note("force.txt", string.format("%d field schedule(s)", #sched))
  end
  assert(P or F, "set FORCE_PATCH or FORCE_FIELDS")
  C.start()
end)
