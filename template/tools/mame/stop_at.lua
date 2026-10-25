-- stop_at.lua - end the session after CAPTURE_FRAMES frames, and do nothing else.
--
-- Fork this into your project's tools/mame/; keep this header.
--
-- For a -debugscript session that watches the running game: the debugger's `go` never
-- returns, so a `quit` after it never runs (measured, MAME 0.177, 2026-10-25). Run this
-- alongside it (the runner's --script with --debug) and the session ends on a frame.
-- Also loads MAME_PLUGINS, so a debug session can hold a byte or force input too.
local here = os.getenv("MAME_LUA_DIR")
if not here or here == "" then
  here = debug.getinfo(1, "S").source:match("^@(.*[/\\])") or "./"
end
if not here:match("[/\\]$") then here = here .. "/" end
local C = dofile(here .. "_compat.lua")

C.main(function()
  assert(C.num("CAPTURE_FRAMES"), "stop_at.lua needs CAPTURE_FRAMES (the runner's --frames)")
  C.start()
end)
