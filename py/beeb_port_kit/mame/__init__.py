"""beeb_port_kit.mame - MAME as a measuring instrument, for a port with no source.

Distilled from the 1942 arcade port (1942-beeb, 2026-09-07 to 10-23), where the original
was a ROM set and nothing else, and every rule the port shipped was a Python model of a
ROM routine scored frame by frame against a MAME RAM capture. docs/arcade-porting.md is
the method; this package is its generic half. Nothing in it knows a 1942 address: those
are parameters, and the 1942 values appear only in the provenance headers and the tests.

    runner   drive MAME from Python: one-instance guard, absolute output, outputs
             checked for existence AND freshness, exit code, timeout kill,
             -playback/-record, a -debugscript mode, cfg DIP overrides reported
    records  per-frame binary records described by ONE spec string, which the Lua
             writer (template/tools/mame/_compat.lua) and the Python reader both parse
    romset   a MAME ROM zip checked against a ROM list (or -listxml), regions,
             banked windows, a gfx_layout decoder, PROM palettes and colour lookups
    orient   ROT0/90/180/270 for screens, cells and flip bits, and the "score all
             four rotations" test that measures which one a cabinet uses
    z80sub   a headless Z80 sub-CPU (the `z80` pip package, imported lazily): MMIO
             callbacks, a held IRQ at N Hz with lateness accounting, a disassembler
    probe    Score: match / wrong / excluded{reason} / torn, coverage, and a
             non-zero exit on any residual that is not named

The modules are forkable one at a time, like the rest of beeb_port_kit: copy what you
need into the project's tools/ and keep its header. Only z80sub needs a package beyond
the standard library, and it imports it when first used.
"""
