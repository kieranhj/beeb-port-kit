# CLAUDE.md

Guidance for Claude Code when working in this repository. This is a port started from the
beeb-port-kit template; `../PORTING.md` (or the kit's copy) is the method, `PLAN.md` the live
plan, `docs/decisions.md` the record.

## Project overview

A port of *[the original]* to the BBC Micro, in 6502 assembly for [Baron](https://github.com/waitingforvsync/baron) (BeebASM's successor - `../docs/toolchain-baron.md` says what differs). **`PLAN.md` is the
live planning document**: read it before starting work. Completed layers keep their notes in
`docs/`, one file per layer, plus `docs/decisions.md`.

## The four rules

**The original is the specification.** Every feature starts by finding what the original does,
and the port reproduces it, taking code, constants and tables verbatim where the hardware allows.
A transliterated routine and a copied table are faithful by construction; an "equivalent" one is
faithful until the first thing it gets subtly wrong. When the BBC forces a change, port the
*decision* the original made, not just the effect.

**Deviations are agreed before they are built and written down after.** Anything the original does
not have, anything the port drops, any place geometry or timing forces a different arrangement:
raise it as a numbered decision, get an answer from whoever owns the port, then record it with the
reason. Do not quietly substitute a design of your own. Edge Grinder recorded 74 such decisions in
five days; several reverse earlier ones by measurement, which is the system working.

**No hardware abstraction layer. One layer at a time, working and visible in the emulator before
the next starts.** Paradroid began life with a HAL designed up front. It was deleted; the file
that survived from that era sat "for months looking like working code" with `TODO: verify in
emulator` in the middle of it.

**Measure, do not recall.** Set the registers in an emulator, look at the screen, read memory back,
confirm, then build on it. Every hardware fact in this kit says what it was measured on and when.
The one time Edge Grinder inferred a register's behaviour instead of measuring it, the mistake
reached real hardware (its decision 63, corrected by 64). And "the emulator cannot measure this"
is itself a claim to test: the belief that jsbeeb could not emulate the NuLA palette was wrong
(decision 67), and had let the first mistake through.

## Target

| | |
|---|---|
| Machine | **BBC Model B with sideways RAM** (decision 1); `MASTER=1` builds the Master 128 path. The template uses no bank, no shadow RAM, no HAZEL |
| CPU | Plain 6502 (`CPU 0`); no 65C12 opcodes, decide before using any |
| Display | MODE 1, 4 colours, 640 bytes a character row (R1 = 80) |
| Palette | **One per cycle** (decision 4): panel black, red, yellow, white; strip blue, magenta, cyan, green - all eight MODE 1 colours at once. The panel's sixteen `&FE21` writes at the end of `rupt_vsync`, the strip's at fire 2 in the panel's last scanline, which `export_panel.py` keeps all logical 0 because sixteen writes (96 cycles) do not fit blanking (48): logicals 1-3 in the displayed part of that blank line, logical 0 in its blanking. `T1_TUNE2` is the measured phase |
| Panel | 4 rows at `&4A00-&53FF`, static, rupture cycle A |
| Play area | 16 rows, 10K at `&5800-&7FFF` under the **10K hardware wrap** (latch lines 4 and 5 both set), rupture cycle B. 16 rows is the ceiling: the display window must fit ONE wrap |
| Scroll | Horizontal by CRTC start address, one unit (8 bytes, 4 px) a frame; the strip is a ring |
| Frame | 39 rows = 312 lines: cycle A 4 rows, cycle B 35 rows with VSync at B row 27 (absolute 31, `FRAME_DROP_ROWS` = 3 from the OS's 34, Paradroid's eye) |
| Game loop | 25 Hz: the VSync IRQ takes the parked scroll address every `FRAME_LOCK` = 2 fields once the loop has parked one; a slow pass costs whole fields, never a tear |
| Interrupts | IRQ1V owned outright (VSync + System VIA T1); no MOS tick, keyboard read direct (`keydown_int`). **The VSync hook restarts T1 before anything else** (decision 5): the frame-lock take runs on alternate fields and anything before the restart moves every fire |
| Controls | Z (97) left, X (66) right - **measured** internal key numbers (OSBYTE 121), never recalled |
| Loader | One data file, `PANEL`, ZX02-compressed by `tools/make_disc.py`, staged at `LOADER_STAGE` = `&3000` (the blanked screen) and unpacked to `&4A00`. All disc access precedes `install_irq` |

## Build

```powershell
.\build.ps1           # assemble into build/
.\build.ps1 -Run      # and launch b2 (-Beebjit for beebjit); b-em is no longer used
.\build.ps1 -Release  # every DEBUG_ flag off
.\build.ps1 -Master   # MASTER=1
sh tools/build.sh     # the same from bash (RELEASE=1 MASTER=1 in the environment)
```

**`RELEASE` and `MASTER` are `-D` symbols and every build passes both**, so that a build says
what it is. **The build timestamp is not a `-D`**: Baron has no `TIME$`, so the build scripts
write `build/build_time.6502` (one line, `BUILD_TIME = "..."`) and `main.6502` includes it -
assembling by hand without a prior build run fails on that missing file. A bare invocation:

```
C:\Users\khcon\OneDrive\BEEB\Bin\baron.exe -o build\GAME-RAW.SSD --title GAME --opt 3 -D RELEASE=0 -D MASTER=0 -v src\main.6502
python tools\make_disc.py build\GAME-RAW.SSD build\GAME.SSD build\GAME-200K.SSD
```

INCLUDE and INCBIN resolve **relative to the including file**, not the working directory, so
`src/main.6502` says `INCLUDE "lib/irq.6502"`; `-o` and `-p` are relative to the cwd.

**Baron's own image is NOT bootable.** `make_disc.py` compresses `PANEL`, round-trips the
stream through `tools/zx02.py`, rewrites its catalogue load address to `LOADER_STAGE`, refuses a
stream that overlaps its output, lays the files out in boot order and pads to 200K. Hand
`build/GAME-200K.SSD` to an emulator. Baron is silent on success and puts every error, in one
run, on stderr as `file:line:col: error:` - so unlike beebasm there is nothing to trip
PowerShell's `$ErrorActionPreference`; check the exit code. Every compile flag that changes the
disc is stamped in `!BOOT` (`BOOT_FLAG` in `main.6502`); add any new `DEBUG_` flag to
`DEBUG_ANY` and to the stamp.

## Source organisation (`src/`)

| File | Contents |
|---|---|
| `main.6502` | constants, zero page, boot (blank, `VDU 22`, load the panel, fill the strip, `setup_display`, `install_irq`), the main loop, and the four `SECTION`s that become files: `zeropage`, `Game`, `Panel`, `Boot` (`!BOOT` at `BOOT_STAGE` = `&7E00`) |
| `rupture.6502` | `rupt_vsync` and `rupt_timer`, the two-cycle rupture and its write-window rules; the two palettes (`PALWR`/`PALSET`, sixteen entries each) and the three T1 fires |
| `lib/` | forks of the kit's `beeb.h`, `irq`, `keydown`, `loader`, `zx02depack`, `boot_stamp` - identical to `../../lib/` but for one `FORKED` line each. Each header says what was measured and what the includer defines; keep the headers, note changes in them |
| `data/panel.bin` | generated by `tools/export_panel.py`; committed; regenerate rather than edit. **Its last scanline must stay all logical 0** - the palette switch straddles it |
| `tools/probe_shot.mjs`, `tools/scan_png.py` | the instrument for `T1_TUNE2`: a headless jsbeeb screenshot with the panel's last line poked, read by pixel (one character = one cycle) |

## Confirmed hardware facts (measured, not assumed)

Seeded from the template's own Layer 0, jsbeeb `B-DFS1.2` model, 2026-09-07
(`docs/layer-0-toolchain.md` has the procedure and the raw numbers):

- **T1 constants for this geometry, final build.** `T1_I1 = 72*SL - 2` = 4,606: VSync handler
  entry to the fire-1 body = **9,299 / 9,295 cycles** = 72.6 scanlines, fire 1 at A + ~13 lines,
  11 before C4 reaches `PANEL_R4` = 3. `T1_I2 = 19*SL - 2 + T1_TUNE2` = **1,272** with
  **`T1_TUNE2 = 58`**: VSync entry to fire 2's first `lda` = **11,850** = panel line 31 (the last),
  **cycle 18 of the 128-cycle line**, first `sta` complete at 24; the four logical-0 stores
  complete at **96, 102, 108, 114** - in blanking (80-127), 16 cycles before it and 13 after.
  `T1_I3 = 17*SL - 2 - T1_TUNE2` = **1,028**: fire 3 at VSync + **13,915** = B row 1 line 7,
  cycle 35 (design row 2; 32 rows ahead of C4 = 34). `T1_I4` = 16,000, never reached. The phase
  numbers are jsbeeb's, read off the rendered picture with `tools/probe_shot.mjs`; the paint
  anchor of `run_frames` sits at a display start (proved to a cycle by sweeping `T1_TUNE2`).
- **Every fire alternated by ~24 cycles between frame-lock take and non-take fields** until the
  T1 restart moved to the top of `rupt_vsync` (`BUGS.md` #1, decision 5); the first Layer 0's
  9,391 / 9,367 was that.
- **jsbeeb's palette index for MODE 1**: the ULA shifts ones in, so a `&00` byte's four pixels
  read entries 0, 0, 1, 1 and a `&0F` byte's 3, 3, 7, 7 (`table4bpp` in its `video.js`). A line
  of zero bytes therefore only ever reads the logical-0 entries - which is what makes the
  straddle line safe for the other twelve writes.
- **The field is 312 lines**: VSync handler to VSync handler = **39,938 cycles** (39,936 + 2 of
  IRQ-entry jitter).
- **Frame lock holds**: 100 fields (3,993,600 `elapsed_cycles`) advanced `field_count` by exactly
  100 and `frame_count` by exactly 50, idle; with X held 115 fields gave 57 passes. **Count fields
  from `elapsed_cycles`**: `run_for_cycles` ran 4,553,339 for a 3,993,600 request once.
- **The 10K wrap** (latch lines 4/5 = 1/1 -> `&5800`): with `scroll` = 10,200 the strip displays
  from `&7FD8` and wraps to `&5800`; the seam marker shows where the arithmetic says.
- **The depacker's output** at `&4A00` is byte-identical to `src/data/panel.bin` (2,560 bytes,
  `cmp` against a `save_memory` dump); `zxdst` finishes at `&5400`.
- The VSync CA1 interrupt is serviced ~4 scanlines after the edge (Paradroid, reconfirmed in Edge);
  the CRTC write windows are the kit's table (`../docs/hardware-facts.md`). Neither re-measured
  here; both are what the rupture is built on and the picture is clean.
- **Not measured here**: where the picture sits on a real tube (`FRAME_DROP_ROWS` is Paradroid's
  choice by eye), b2/beebjit behaviour, real hardware.

## Memory (Layer 0; take live figures from the listing)

`docs/memory-map.md` has the table. In one line: zero page `&00-&0F` ours, and **allocated by
Baron** from a `&00-&8F` pool rather than laid out by hand - declare a variable with `ZA_AUTO1`
/ `ZA_AUTO2` and read its address off the `-v` listing; never hardcode one, and never let one
decide the shape of the program (`IF v`, `SKIP v`, `org = v` are all refused). A routine the
outside world enters needs `ZA_ENTRY`, an interrupt handler `ZA_INTERRUPT` - without it the
allocator will happily put the handler's state on a byte the main loop is using, and says so
with a warning first.
code `&1900-&1DBD` (1,213 bytes; 1,264 with `MASTER=1`) below the screen at `&3000`, `&3000`
the loader's staging area at boot, panel `&4A00-&53FF`, strip `&5800-&7FFF`. `&0E00-&18FF` is
DFS's on a Model B and is free once the last load has returned; the template leaves it alone.

## Assembly conventions

- Baron syntax: labels `.name`, comments `\` or `;`, hex `&` - BeebASM's, less `ORG`/`SAVE`/
  `GUARD`/`CLEAR` (sections carry those) and `ASSERT` (a macro in `beeb.h.6502`)
- Keep routine and variable names matching the original's where a routine is a transcription
- A local label inside `{}` shadows a global of the same name, silently
- Debug builds are switched by `DEBUG_` constants at the top of `main.6502`; every debug key
  needs CTRL once the game has controls
