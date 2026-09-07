# Layer 0 - toolchain (2026-09-07)

## What the template proves

Every piece of the beeb-port-kit runs once, in one 1,213-byte program (1,036 before the two
palettes came in, later the same day), and the result was measured in jsbeeb (`B-DFS1.2`; the
`MASTER=1` build on `Master`) rather than looked at:

| Piece | Where | Proof |
|---|---|---|
| `boot_stamp.asm` | `!BOOT` at `&7E00` | jsbeeb's screen text: `REM beeb-port-kit template DEV build` / `REM BUILD 07 Sep 2026 03:02:40` / `*RUN Game`; the Master build adds `REM MASTER: Master 128 build`; the RELEASE build's stamp read back from the catalogue carries the version line and no DEV |
| `loader.asm` + `zx02depack.asm` | `PANEL` staged at `&3000`, unpacked to `&4A00` | `&4A00` read back after boot, 2,560 bytes, **identical to `src/data/panel.bin`** (md5 `480a1d5dda14e04ee9eee9637b9983e1`); `zxdst` left at `&5400`. Both models: `B-DFS1.2` and, with the `MASTER=1` disc, `Master` |
| `make_disc.py` on `dfs.py` / `zx02.py` | `build/GAME.SSD` | `PANEL` 2,560 -> 79 bytes via `zx02.exe`, round-tripped through `zx02.decompress`; catalogue load/exec rewritten to `&3000`; layout `!BOOT`, `Game`, `PANEL`; 2,304-byte image, 204,800 padded. The overlap check refuses a stream over its output |
| `irq.asm` | IRQ1V owned, CA1 + T1 | the field counter climbs by exactly 100 in 3,993,600 cycles |
| `keydown.asm` | `keydown_int`, Z = 97, X = 66 | X held 50 fields: `scroll` 0 -> 200 (25 steps of 8). Z held 60 fields: 200 -> 10,200 (30 steps, wrapped by +10,240) |
| the rupture | `src/rupture.asm` | screenshot: 4-row panel with its white edge lines over the 16-row strip; T1 sweep below |
| **two palettes** (decision 4) | `rupt_vsync` (panel), fire 2 (strip) | screenshot: the panel's bars black, red, yellow, white; the strip's bands blue, magenta, cyan, green - all eight MODE 1 colours at once, the straddle line under the panel black end to end, and the strip's palette intact after 50 fields of X. Both builds, both models. The switch's phase measured to the cycle, below |
| `beeb.h.asm` | everything above names its registers through it | |

## The rupture, and how the T1 constants were measured

Frame: cycle A = 4 rows (panel, `&4A00`), cycle B = 35 rows, 16 displayed from the scroll
address, VSync at B row 27 (absolute row 31). R4 written inside its own cycle at each fire; R6
and R12/R13 for the next cycle written inside the previous one; R7 = 27 constant because cycle A
never reaches it; R5 = 0 and R8 = 0 after boot. The rules are the kit's measured table
(`../../docs/hardware-facts.md`, "Write windows").

**And two palettes** (decision 4): the panel's sixteen `&FE21` writes at the end of the VSync
hook, the strip's at the A -> B boundary. Paradroid's design; what is new here is that this
frame has NO blank lines at that boundary - cycle A is four rows, all displayed, and B's first
line is displayed too - so the strip's switch has to hit a phase within a scanline. Sixteen
`lda # : sta &FE21` are 96 cycles; MODE 1 displays 80 of a line's 128 character times, so
blanking is cycles 80-127, 48 wide. The sequence therefore straddles a line boundary, and it is
placed in the panel's LAST scanline (A + 31), which `export_panel.py` keeps all logical 0: the
twelve writes for logicals 1-3 go first, in that line's displayed part, where no pixel looks
them up (the ULA indexes the palette by the pixel's bits, so a line of zero bytes only ever
reads the logical-0 entries); the four writes for logical 0 go last, in the line's blanking.
`T1_TUNE2` is the phase, in 1 MHz ticks.

Design, in scanlines from the VSync edge (handler entry ~4 lines later):

| | Where | Writes |
|---|---|---|
| VSync hook | B row 27 + ~4 lines | **T1C = `T1_I1`, T1L = `T1_I2` FIRST** (decision 5); R6 = 4, R12/13 = `&4A00/8` for A (8 rows away); take `crtc_park` if `FRAME_LOCK` fields have passed; the panel's sixteen palette writes |
| fire 1 | A + 12 lines (row 1 + 4) | R4 = 3 (A's own, 12 lines before C4 = 3); R6 = 16 and R12/13 = `crtc_live` for B; T1L = `T1_I3` |
| fire 2 | A + 31, the panel's last line, phased by `T1_TUNE2` | the strip's sixteen palette writes, logicals 1, 2, 3 then 0; T1L = `T1_I4`. Nothing else: this is still cycle A |
| fire 3 | B row 2 | R4 = 34 (B's own, 32 rows early) |

`T1_I1 = ((35 - 27) * 8 + 12) * SL - 4*SL - 2` = **4,606**; `T1_I2 = (31 - 12) * SL - 2 +
T1_TUNE2` = **1,272** with `T1_TUNE2 = 58`; `T1_I3 = (32 + 16 - 31) * SL - 2 - T1_TUNE2` =
**1,028**; `T1_I4 = 250 * SL` = 16,000, never reached (VSync restarts T1 long before).

### Measured (final build, 2026-09-07)

`../../docs/verification.md` procedure 4: execute breakpoints on `rupt_vsync` (`&1A8F`), the
fire-1 body (`&1B39`), fire 2's first `lda` (`&1B72`), the `lda` of its first logical-0 write
(`&1BAE`) and the fire-3 body (`&1BD3`); `elapsed_cycles` from `read_registers` at each stop;
plus a `run_frames` paint as the line anchor (it sits at a display start, proved below).

| Interval | Cycles | Scanlines (128) | Where the fire lands |
|---|---|---|---|
| VSync handler entry -> fire 1 body | 9,299 (9,295 on another field) | 72.6 | A + ~13 lines, 11 ahead of C4 = 3 |
| VSync entry -> fire 2's first `lda` | 11,850 | 92.6 | **line 31 of the panel, cycle 18**: the first `sta` completes at cycle 24 |
| VSync entry -> the logical-0 `lda` | 11,922 | | cycle 90; its four stores complete at **96, 102, 108, 114** - inside blanking (80-127) with 16 cycles before and 13 after |
| VSync entry -> fire 3 body | 13,915 | 108.7 | B row 1, line 7, cycle 35 - one line short of the design's row 2 and 32 rows ahead of C4 = 34 |
| VSync entry -> VSync entry | 39,934 / 39,936 | 312.0 | |
| paint anchor -> VSync entry | 328 | 2.6 | |
| paint anchor -> fire 2's first `lda` | 12,178 = 95 x 128 + 18 | | the same line 31, cycle 18 |

The 0.6-line excess on the first interval is IRQ entry plus the handler's prologue before the T1
restart; it was 1.3 lines when the restart came after the CRTC writes and the take. Jitter
between fields is 4 cycles (the main loop spins on a 6-cycle `lda`/`bne`; the SEI window
around the park runs just after a take, 300 lines from any fire).

### How the phase was found, and what went wrong on the way

The breakpoint numbers say where a write is in the CPU's time; whether that is a displayed
character or blanking needs a line anchor, and the two eyeballed readings from MCP screenshots
disagreed with each other by 27 cycles. The instrument that settled it is
`tools/probe_shot.mjs` + `tools/scan_png.py`: boot the disc headless in jsbeeb's own
`MachineSession`, poke the panel's last scanline with a probe pattern, save the PNG, and print
each row as 80 x 4 colour letters, one per MODE 1 pixel - one character time per cycle. The
`half` probe (units 0-39 logical 1, 40-79 logical 0) shows both palette groups in one frame:
logical-1 pixels read entries 3 and 7 (jsbeeb's `table4bpp`: the ULA shifts ones in, so
pixels 0-1 of a `&0F` byte index entry 3 and pixels 2-3 entry 7; zero bytes index 0, 0, 1, 1),
so the red -> dashed -> magenta steps are entry 3's and entry 7's writes, six and eighteen
cycles after the first; the right half goes blue-dashed where entry 0 lands if it lands in the
displayed part at all.

Sweeping `T1_TUNE2` moved the steps by two characters a tick, exactly, and put the paint anchor
at a display start to within a cycle: the final build's first `sta` is at paint + 95 lines + 24
and the probe shows entry 3's step at character 31 = 24 + 6 + 1. **The zero half stays black
at 58 and the top line of the strip is intact** on both fields of a pair one field apart.

Two things it caught:

1. **The frame-lock take moved every fire by ~24 cycles on every second field** (`BUGS.md` #1,
   decision 5). The same build gave entry 0's write at character 51 in one boot and 75 in
   another; the original Layer 0's 9,391 / 9,367 for VSync -> fire 1 was the same thing,
   recorded and not asked about. The T1 restart is now the first thing in `rupt_vsync`.
2. **The `PALSET` index arithmetic** had `(L AND 1)` where it needed `(L AND 1) * 2` (logical bit
   0 is entry bit 1): two of the four colours came out as stripes in the first screenshot.
   Hardware-facts.md section 2's rule - all sixteen entries, four per logical colour - is
   exactly what the screen shows when it is broken.

Not measured: where the write lands on real hardware relative to the picture, which depends on
the ULA's and the CRTC's own pipelines; jsbeeb applies a palette write to the next character it
renders. The 13-16-cycle margins are for the emulator. A port that needs more can only get it by
blanking a second scanline, because the four logical-0 writes are 24 of blanking's 48 whatever
else moves.

The frame lock: `field_count` `&25` -> `&89` and `frame_count` `&0092` -> `&00C4` across exactly
3,993,600 `elapsed_cycles`: 100 fields, 50 passes, idle; with X held, 115 fields -> 57 passes over
4,553,339 (`run_for_cycles` overran its request that time - **count from `elapsed_cycles`, not
from the request**, the kit's rule again). `scroll` 0 -> 200 in 50 fields of X.

## Build facts

- **The assembler changed on 2026-09-07: BeebASM 1.11 -> Baron 0.3.0** at
  `C:\Users\khcon\OneDrive\BEEB\Bin\baron.exe`. Gated on byte-identity, both models:
  `Game` (1,087 bytes DEV, 1,138 MASTER) and `PANEL` came out **identical to the BeebASM
  build**, `!BOOT` differing only in its timestamp, and both discs boot in jsbeeb with `&4A00`
  identical to `src/data/panel.bin` and `zxdst` at `&5400`. All of RELEASE=0/1 and MASTER=0/1
  assemble, from `build.ps1` and `tools/build.sh`. Why, and the whole BeebASM delta:
  `../../docs/toolchain-baron.md`.
- `RELEASE` and `MASTER` passed every time (Baron has `DEFINED()`, so this is now a choice, not
  BeebASM's no-`IFDEF` workaround). The `!BOOT` timestamp comes from the generated
  `build/build_time.6502`, not `TIME$`: **Windows PowerShell cannot pass a quoted string with
  spaces to a native exe** - three forms tried, all mangled - so it is a file, not a `-D`.
  Keeping that file makes a rebuild byte-identical.
- Baron resolves `INCLUDE`/`INCBIN` **relative to the including file**, where BeebASM used the
  working directory: every include path in `src/` changed. A wrong path surfaced once as a
  confusing parse error at the first macro call, not as "could not read".
- The zero-page slots no longer have to be declared before the file that uses them: a
  forward-referenced zero-page symbol still assembles as zero page (measured). BeebASM's
  pass-1 sizing trap is gone with it.
- Code `&1900-&1D3F` (1,087 bytes; 1,138 under `MASTER=1`), 4,801 free to `&3000`. Zero page
  high water `&1A`. `build.ps1` and `tools/build.sh` both run, both builds. (Was 1,213 bytes
  and `&1D` before the ZX0 -> ZX02 change: 126 bytes of depacker and three zero-page slots.)
- The scratch `ORG` bookkeeping (`code_p%`, `boot_p%`) and the `CLEAR` for `PANEL` are gone:
  `PANEL` and `!BOOT` are `SECTION`s of their own, and two sections may share an address.
- `dfs.py` forked with two changes: `import zx02` for the package-relative import, and the ZX0
  codec dropped (this is a ZX02 port; the kit's copy still carries both). Its API needed no
  adapting (`read_image`, `compress`, `check_stream`, `build_image`, `pad`).
- **The compressor changed on 2026-09-07: ZX0 -> ZX02.** 131 bytes of depacker against 257 and
  2.14x the decode speed for +0.11% on the packed size (`PANEL` 54 -> 79 bytes here, this file
  being nearly all one repeated run - the worst case for ZX02's 8-bit gamma, and 25 bytes on a
  2,304-byte image). Measured over 43 real files from both shipping ports in py65, then end to
  end by booting this disc; `../../lib/zx02depack.asm` has the numbers. The earlier row's md5
  (`991304905c7b...`) never matched `panel.bin` on disc; the value above is what both models
  read back.
- `run_for_cycles` from a PC already on a breakpoint returns 0 and the next call moves on,
  exactly as the kit's notes say; a three-breakpoint sweep costs two runs a stop.

## Not done

- An aligned switch into the rupture (`RuptAlign`); decision 3.
- The palette switch's phase on real hardware (above): jsbeeb only.
- `FRAME_DROP_ROWS` on a real tube; b2 and beebjit; real hardware. `build.ps1 -Run` launches b2
  with no model flag because the flag for a Model B was not measured.
- `swram_probe.asm` is not forked: nothing here uses a sideways bank. Fork it from the kit when
  the first bank arrives.
