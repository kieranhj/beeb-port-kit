# tools/cpc - the instrument for an Amstrad CPC original

The Python half of [`docs/cpc-demo-porting.md`](../../../docs/cpc-demo-porting.md): a Z80
original unpacked, run, timed, covered and recorded, so every model and every 6502 routine of the
port has records to be scored against. Taken from the two CPC demo ports (Isometrikum and Square
Roots, Vanity, November 2026) as they stood at the end; **each file is a project's tool with that
project's addresses in it** (entries, wait loops, unit points), meant to be forked into the new
project's `tools/` and adapted, as `template/tools/mame/` is for an arcade board.

Dependencies: kosarev's [`z80`](https://pypi.org/project/z80/) (`pip install z80`; 1.2.0 tested -
`cpcrun.py` and `cpcboot.py` touch its private attributes), SkoolKit 10.1 (`pip install
skoolkit`), numpy, Pillow. `z80` installs to user site-packages: run the tools **without
`python -I`**, which hides it. `winape_shot.ps1` needs Windows (PowerShell 5.1 or 7) and
[WinAPE](http://www.winape.net/) 2.0b2. The tools import each other from this directory
(`cpcboot` -> `cpcvideo`, `fdc`, `disc`, `cpctime`; `pens` -> `cpcvideo`, `rtw`), so keep them
together.

Every tool has a header docstring (`python TOOL.py --help`, or `Get-Help .\winape_shot.ps1`)
with its origin and its **known defects**: read them before a result rests on the tool.

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

### The cycle-exact reference for a raster demo (from phX, 2026-11)

For a demo whose effects are the beam's position (section 14 of the document) and that loads
from its disc as it plays (section 15). Generalised from phX's tools: the boot command, the CRTC
read-back, the part table and the capture geometry are arguments or a JSON config; phX's own
numbers are not here.

| File | What | Inputs -> outputs | Known defects (in each header) |
|---|---|---|---|
| `cpcboot.py` | A CPC 6128 that boots the demo's DSK at CPC timing (was phX's `phxrun.py`): `z80` + `cpcvideo` + `fdc`/`disc`, `&7Fxx` banking, IM 1/2, checkpoints (`--save-state`/`--load-state`: long runs in parallel chunks), `--trace page:addr` | `DSK OUTDIR FIELDS --run NAME` [`--crtc-type 0/1/2`, `--poke ADDR=HEX`, `--load/--exec/--sp/--im`, `--index-phase`, `--rpm`, `--report ADDR`] -> `fNNNNN.png` (312 x 512), `io.npy` (every port access with its beam position), `crtc.npy` (each CRTC write with C0/C9/C4), `cov.npy`, `fields.npy` (each field's us), `fdc.log`, `snap_*.bin`, `state_*.pkl`, `trace.txt`, `run.txt` | No firmware: a loader that calls it needs stubs (`--poke`); the default pokes are phX's loader's, an example; types 1/2's read-back from memory, and the timing is type 0 whatever the type; INT_NOPS is IM 1's in IM 2 too; inherits the three below |
| `cpcvideo.py` | The type-0 6845 at character resolution (Last Line at C0 0-1, R5 adjust, R7 at a line's start and on a write, HSYNC-locked monitor x) and the Gate Array (pens, mode at HSYNC, the 52-line interrupt); `RGB`/`HW` colour tables | library (`Video`); `python cpcvideo.py` prints its docstring | **Gate Array writes half a microsecond early** vs WinAPE (phX BUGS 11); the beam race a line early (fetch lead); **scanline order wrong under per-line R4/R9 reprogramming** (phX decision 63: not located, worked around by building that part's pictures from the source's order); WinAPE's black top line |
| `fdc.py` | The uPD765A polled: specify, sense drive/interrupt status, seek/recalibrate at the step rate, read data (MT/MF/SK), read ID; 300 rpm, the 765's track layout, the ID wait, 32 us bytes, overrun ends the read (ST1 OR), no TC (EN) | library (`FDC(disc, clock)`) | Timing from the data sheet, AMSDOS's SPECIFY from memory; phX's loads came out 1-2.6 s off WinAPE's; no write/format, no head load/motor spin-up, no skew; one disc in every drive |
| `disc.py` | An EXTENDED or standard DSK as tracks of sectors (IDs, ST1/ST2, GAP3), the AMSDOS catalogue and files (DATA format) | `python disc.py DSK` -> the layout and the catalogue | `amsdos_file` reads DATA format on side 0 only; weak sectors kept as one blob |
| `winape_shot.ps1` | WinAPE on the DSK, autorun (`/A`), `PrintWindow` captures of its largest visible window at `-At` seconds or `-Every` s to `-Until`; `-Size W,H` (SetWindowPos) with `__COMPAT_LAYER=HighDpiAware` for an unscaled picture; `-Exe` (default `$env:WINAPE`, then the PATH) | `-Disc D -Out DIR` -> `t<ms>.png`, `log.txt` | The machine is WinAPE.ini's (a 6128, CRTC type 0, no Plus, no PAL filter, no stretch: set in its dialog, keep a copy of WinAPE for this); wall-clock timing; captures during the splash screen are of the splash |
| `winape_match.py` | Finds each capture's field in the reference and diffs it at the CPC's three levels a gun | `CAPDIR REFDIR OUT [--config CFG.json] [--override FILE:FIELD]` -> `match.csv`, `frames/<part>_f<field>.png` (WinAPE's picture of a field: the frames to check the BBC by), `sheet_<part>.png` (WinAPE / reference / difference), a summary a part | Geometry is WinAPE 2.0b2 at `-Size 820,720`: check a capture by eye; a 0.5 s interval cannot see a one-field event (a missed VSYNC) |
| `example_winape_parts.json` | `winape_match.py`'s config, every key documented: the part table (made-up names and fields: list the original's own), capture box, thresholds, t0, overrides | - | - |
| `contact.py` | A contact sheet of a run's `fNNNNN.png`, labelled by field; prints where the picture last changes | `RUNDIR OUT.png [--from --to --step --cols --scale]` | Change detection is by file hash |
| `rtw.py` | A CPC mode-0 frame as BBC MODE 2 by RTW's fixed `(x + y) & 1` checker (the chart in `palette_map.py`); `dither()`, `mode2_bytes()` | `FRAME.png OUT [--x0 --width --y0 --height]` -> `OUT.bin` (character-cell order), `OUT_preview.png` | Needs the reference's 0/128/255 levels; the checker phase is fixed to the picture |
| `pens.py` | The colour budget a line under RTW's chart: from `io.npy` the pens in force each line (an upper bound), or from the frames what is shown (`--frames`); pen writes a line and a field | `RUNDIR [--from --to --bucket]` -> `pens.txt`; `--frames` -> `pens_frames.txt` | Fixed 64 us lines from VSYNC; a mid-line write counts for its line's end; shared physical colours counted twice |

**The pipeline** (phX's order, `docs/cpc-demo-porting.md` sections 13-15):

1. **The reference.** `disc.py DSK` to see the disc; `cpcboot.py DSK work/ref END --run NAME
   --save-state ...` once, then `--every 1` chunks from the checkpoints in parallel. List every
   field in `fields.npy` that is not 19,968 us and decide each; `contact.py` for the part
   boundaries; `pens.py` for the colour budget.
2. **The WinAPE gate**, before any part rests on the reference: `winape_shot.ps1 -Disc DSK -Out
   work/winape/run -Every 0.5 -Until END_S -Size 820,720`, then `winape_match.py work/winape/run
   work/ref work/winape/match --config parts.json`. Read every part's residue: a raster line or a
   byte column is cpcvideo's known Gate Array timing; anything else is a fault of the reference to
   fix (or, as phX's outro, to work around from the source) before the part's expected pictures
   are made. WinAPE's `frames/` are what the BBC is checked by. Vary `--index-phase`/`--rpm` for a
   multi-load demo: the loads are where the two drives differ.
3. **The source review**, last, if the original's source exists: each part's BBC code read
   against it for what the oracles cannot see (the reference's own errors, the fields between two
   parts' checks, data an oracle shares with the code).

Smoke test (2026-11-18, the kit's copies, no original's files): a synthesised two-track
EXTENDED DSK (an AMSDOS DATA track with a 52-byte boot program; a 10 x 512 loader track):
`disc.py` lists it; `cpcboot.py ... 12 --run TEST --every 1 --save-state 6 --trace 1:4031`
boots it (border, pens, mode, a 16K `LDIR`, IM 1 halts: 6 interrupts a field, field 0 15,360 us
then 19,968), and a resume from `state_00006.pkl` gives the same frame byte for byte; `fdc.py`
driven directly seeks (Seek End after one 12 ms step), reads two sectors (ends past EOT, ST1 EN)
and flags an overrun when a byte is 200 us late; `winape_match.py` finds fake captures made
from the run's own frames (WinAPE's levels; a 2 x 20-pixel change reported as 40 pixels in its box)
and runs an override; `contact.py`, `rtw.py`, `pens.py` (both modes) run on the run; and
`winape_shot.ps1` launched WinAPE 2.0b2 on the disc, autorun booted it, and the capture after
the splash screen was the emulator's window resized to 820 x 720.

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
