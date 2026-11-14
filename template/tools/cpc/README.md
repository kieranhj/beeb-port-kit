# tools/cpc - the instrument for an Amstrad CPC original

The Python half of [`docs/cpc-demo-porting.md`](../../../docs/cpc-demo-porting.md): a Z80
original unpacked, run, timed, covered and recorded, so every model and every 6502 routine of the
port has records to be scored against. Taken from the two CPC demo ports (Isometrikum and Square
Roots, Vanity, November 2026) as they stood at the end; **each file is a project's tool with that
project's addresses in it** (entries, wait loops, unit points), meant to be forked into the new
project's `tools/` and adapted, as `template/tools/mame/` is for an arcade board.

Dependencies: kosarev's [`z80`](https://pypi.org/project/z80/) (`pip install z80`), SkoolKit 10.1
(`pip install skoolkit`), numpy. `z80` installs to user site-packages: run the tools **without
`python -I`**, which hides it.

| File | From | What | Generic? |
|---|---|---|---|
| `dsk_extract.py` | Square Roots | AMSDOS files from a standard (`MV - CPCEMU`) or EXTENDED DSK, header stripped and kept as `.hdr`; a library (`read_dsk_bytes`, `read_file`, `header`) | Yes. The kit's `py/beeb_port_kit/cpc/dsk.py` reads the same formats |
| `depack.py` | Square Roots | Runs the original's own depack stub on `z80` (`TXT OUTPUT` made a `RET`) and saves the 64K at the entry: `depack.py FILE OUT LOAD EXEC ENTRY` | Yes, for any packed CPC binary whose stub needs no firmware but `&BB5A` |
| `cpcrun.py` | Square Roots (Isometrikum's, plus 6128 banking and CPC timing) | The picture machine: one scanline at a time, Gate Array (pens, mode, 52-HSYNC interrupts), 6845 (R5 adjust, R7, R12/R13 latched per CRTC frame), PPI VSYNC, AY log, `&7Fxx` RAM configurations `&C0-&C7`. `frames.npy`, `ay.log`, `out.log`, `regs.log`. `RAW=1`: raw Z80 T; `ENTRY=hex`: the entry (Square Roots' `164B` by default) | Mostly: the stack and the modelled ports are the demos' |
| `cpctime.py` | Square Roots | Each instruction's CPC length in microseconds: `ceil(T/4)` plus the exceptions. **From memory, not measured on a CPC**: anything depending on it is PROVISIONAL | Yes |
| `cpccov_raw.py` | Square Roots | Coverage under `cpcrun` at raw timing with real interrupts, before any reference exists: `cov.txt` and the field each start was first hit | Yes (`ENTRY=hex`) |
| `cpccov.py` | Square Roots | The same under CPC timing | Yes |
| `covdis.py` | both | Disassembles **only along executed starts**, with gap markers; drops kosarev's DD/FD prefix stop. Use it, not a linear listing: players enter handlers mid-instruction | Yes |
| `z80dis.py` | both | `sna2skool` over the image, for orientation | Yes |
| `cpcref_fieldlocked.py` | Isometrikum | The logical reference for a **field-locked** main loop: Z80 4x fast, VSYNC as an edge, interrupts queued to the wait loop, a fixed 312-line clock; `passes.bin` (64K XOR-zlib records at every field-done call), `ticks.npy`, `ay.log`, `r.log`, `songs.log`, `crtc.log` | Pattern: the wait loop, record hook and player addresses are Isometrikum's. Checked 2026-11-14: on Isometrikum's image over 200 fields every output is byte-identical to that project's own `cpcref.py` |
| `cpcref_units.py` | Square Roots | The logical reference for a **free-running** main loop: CPC timing, main-loop *units*, the world-work interrupt held out of non-commuting regions, records at the first unit after each world work; `world.log` (the port's schedule), `trees.log`, `deferred.log`, `boot.bin`. `NODEFER=1` measures what holding back changes | Pattern: units and regions are Square Roots' |
| `palette_map.py` | Isometrikum | RTW's 27-colour CPC -> BBC checker chart, the per-face re-dither, the CPC -> NuLA level map; its cache builder imports Isometrikum's `fx_world` | The chart and `face()` yes; the rest is the pattern |
| `ring_size.py` | Isometrikum | Sizes a software screen ring by replaying every write of the reference into a ring of R cells and checking every displayed byte | Pattern: the method is the point (1,440 cells -> 1,218 fields wrong, 1,446 -> 0) |

Not here, because they are each demo's own: the models (`fx_music.py`, `fx_world.py` - the
original's routines in Python, over its own 64K image), `ideal_ref.py`/`stock_ref.py` (the model
run on an ideal schedule or on re-dithered data), `make_sched.py` (`world.log` -> the port's
schedule) and `boot_model.py` (world works replayed inside the boot's `LDIR`). The document
describes each; the ports have them.

The rest of the CPC port's tools are in `template/tools/`: `shrinkler.py`, `shrinklersrc/`,
`size_report.py`, `grind_bytes.py`, `verify_image.mjs` (the crunch) and `ay2sn_model.py`,
`make_ay2sn_tables.py` (the 6502 `lib/ay2sn.6502` in Python, and its tables).

Smoke test (2026-11-14, from the kit's copies): `dsk_extract.py` + `depack.py ... 8000 8E50 2D0A`
on Isometrikum's disc gives that project's 64K image byte for byte; `ENTRY=2D0A RAW=1
cpccov_raw.py` and `covdis.py` disassemble its boot; `cpcrun.py` runs it at CPC timing.
