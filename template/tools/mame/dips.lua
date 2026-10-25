-- dips.lua - what the cabinet's DIP switches ARE SET TO, out of the running driver.
--
-- Fork this into your project's tools/mame/; keep this header.
--
-- From 1942-beeb's dips.lua and dipnames.lua (2026-09-10, arcade-facts s34, decision 36).
-- MAME's cfg/1942.cfg had been edited by hand to five lives and EASY, MAME applies the
-- cfg to -playback too, and so every capture, every probe and every threshold that
-- port had measured for three weeks was Easy - while its docs said "MAME's default".
-- The driver's defaults (-listxml) are not the cabinet you captured; this is.
--
-- Then, by hand: scan the ROM for every read of the DIP ports, list what each changes,
-- decide which setting the port hard-codes, and mark every dependent constant
-- `DIPSWITCH:` in the source (1942's game.6502 does; decision 36 is the record).
--
--   DIPS_AT       frame to read at (decimal, default 120 - after the boot)
--   DIPS_ADDRS    also read these addresses on DIPS_CPU (hex list) - where the game
--                 sees the ports                          GAME: 1942: c000-c004
--   DIPS_CPU      default :maincpu
-- Writes dips.txt: every input port, its live value, and each field's mask, default,
-- live setting and the names MAME gives the settings; then DIPS_ADDRS.
local here = os.getenv("MAME_LUA_DIR")
if not here or here == "" then
  here = debug.getinfo(1, "S").source:match("^@(.*[/\\])") or "./"
end
if not here:match("[/\\]$") then here = here .. "/" end
local C = dofile(here .. "_compat.lua")

C.main(function()
  local f = C.open("dips.txt", "w")                        -- open first
  local AT = C.num("DIPS_AT", 120)
  local ADDRS = C.hexlist(C.env("DIPS_ADDRS", ""))
  local mem = C.space(C.env("DIPS_CPU", ":maincpu"))
  C.add_frame(function(n)
    if n < AT then return end
    local tags = {}
    for tag in pairs(C.ioport().ports) do tags[#tags + 1] = tag end
    table.sort(tags)
    for _, tag in ipairs(tags) do
      local port = C.ioport().ports[tag]
      local okv, live = pcall(function() return port:read() end)
      f:write(string.format("PORT %s  reads %s\n", tag, okv and string.format("%02X", live) or "?"))
      local names = {}
      for name in pairs(port.fields) do names[#names + 1] = name end
      table.sort(names)
      for _, name in ipairs(names) do
        local fld = port.fields[name]
        local setting = okv and (live & fld.mask) or nil
        local line = string.format("  %-28s mask=%02X default=%02X", name, fld.mask, fld.defvalue)
        if setting then
          line = line .. string.format(" SET=%02X%s", setting,
                                       setting ~= (fld.defvalue & fld.mask) and "  <- NOT THE DRIVER'S DEFAULT" or "")
        end
        f:write(line .. "\n")
        local oks, settings = pcall(function() return fld.settings end)
        if oks and settings then
          local vs = {}
          for v in pairs(settings) do vs[#vs + 1] = v end
          table.sort(vs)
          for _, v in ipairs(vs) do
            f:write(string.format("      %02X %s%s\n", v, settings[v], v == setting and "   <- live" or ""))
          end
        end
      end
    end
    for _, a in ipairs(ADDRS) do
      f:write(string.format("ADDR $%04X = %02X\n", a, mem:read_u8(a)))
    end
    C.done("DIPSDONE")
  end, "record")
  C.start()
end)
