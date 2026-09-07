# BBC Micro hardware facts, measured

*Part of the beeb-port-kit by Kieran Connell (KC), MIT licence. For an experienced 6502
programmer starting a BBC game port.*

This is a reference of facts about the BBC Micro's hardware, the MOS, DFS, the beebasm
assembler and the emulators, collected during two C64-to-BBC ports: **Paradroid** on a BBC Model B
([paradroid-beeb](https://github.com/kieranhj/paradroid-beeb)) and **Edge Grinder** on a BBC
Master 128 ([edge-beeb](https://github.com/kieranhj/edge-beeb)). Every entry states the fact,
then how and when it was established, then links the file in the port where the measurement is
written up. Nothing here comes from recall or from a manual alone; where a port recorded something
as inferred, emulator-only, or untested on real hardware, the entry says so. The two ports use
jsbeeb (through an MCP that can set breakpoints, read memory and registers, and count cycles) as
the primary instrument, with b-em and b2 as cross-checks and a real Master 128 where noted. Dates
are the ports' own; a fact whose write-up carries no date is marked with the layer it came from.

The rule the whole document exists to serve is **measure, do not recall**. Paradroid's `CLAUDE.md`
tells the story: an early file, `src/hal_video.asm`, was written from remembered CRTC arithmetic,
with `TODO: verify in emulator` comments and a half-finished derivation in the middle of it, and it
survived in the tree for months looking like working code. It was deleted, and the replacement was
built one register at a time with the emulator open: set the registers, look at the screen, read
memory back, confirm, then build on it. Several of the facts below contradict what either port's
author believed beforehand (a scanline is 128 CPU cycles, not 64; `R6 = 0` is not a blank; the
display wrap sizes are not powers of two; jsbeeb does boot an unpadded disc image). Each of those
cost a wrong build before it cost a measurement. ([Paradroid CLAUDE.md](https://github.com/kieranhj/paradroid-beeb/blob/main/CLAUDE.md))

---

## 1. The 6845 CRTC

### Start address and pixel arithmetic

- **CRTC start address = screen address / 8.** A buffer at `&5800` is `R12/R13 = &0B00`.
  Measured: Layer 3 (August 2026), jsbeeb, by programming R12/R13 and checking what displayed. [Paradroid CLAUDE.md](https://github.com/kieranhj/paradroid-beeb/blob/main/CLAUDE.md)
- **One CRTC address unit is 8 bytes, which is one byte per scanline of an 8-scanline cell.** In
  MODE 0 that is 8 pixels, in MODE 1 4 pixels, in MODE 2 2 pixels. Horizontal hardware scroll
  granularity is therefore half a MODE 1 character (4 px), not a whole one, and a quarter of a
  MODE 2 character.
  Measured: Layer 3, jsbeeb, horizontal scroll stepping 10 steps in 10 frames at 4 px. [Paradroid layer-3-scroll.md](https://github.com/kieranhj/paradroid-beeb/blob/main/docs/layer-3-scroll.md)
- **A hardware-scrolled area is a one-dimensional ring through memory, not a 2-D grid.** A
  character leaving the left edge reappears one row up on the right. Drawn as a flat grid it is
  corruption that scales with the offset; treated as a circular strip the redraw per step
  collapses to one column or one row.
  Measured: Layer 3, jsbeeb (at 80 px offset the right quarter showed the wrong rows). [Paradroid layer-3-scroll.md](https://github.com/kieranhj/paradroid-beeb/blob/main/docs/layer-3-scroll.md)
- **R12/R13 form one 14-bit value across two writes**; if the CRTC samples between them the display
  shows one frame at a half-updated address. Write both in vertical blanking.
  Measured: Layer 3, jsbeeb. [Paradroid layer-3-scroll.md](https://github.com/kieranhj/paradroid-beeb/blob/main/docs/layer-3-scroll.md)

### Write windows per register

A frame built from several CRTC cycles (a "rupture") has to write each register inside a
particular cycle. These are the rules that held after two wrong builds:

| Register | Write it | Symptom when wrong |
|---|---|---|
| R4 | inside its own cycle, before C4 reaches the new value | the previous cycle trips over it (a stretched cycle; the tail cycle of Edge Grinder's titles hung `field_wait` with the field counter frozen) |
| R7 | before the counter reaches the row it names: inside the current cycle if C4 has not yet passed that row, otherwise the previous cycle (KC, 2026-09-07; the ports wrote "previous cycle", which is the safe form of the same rule) | that row's compare has already happened, **VSync never fires**, the chip free-runs on the last cycle's shape and the picture rolls |
| R6 | the same rule as R7: before C4 reaches the row (KC, 2026-09-07) | display enable is a flip-flop cleared on match; raising R6 afterwards does not bring the cycle's display back |
| R12/R13 | inside the **previous** cycle | latched at cycle start |
| R5 | anywhere in the cycle, but **not near a boundary** | see the R5 trap below |

Measured: Layer 3 (August 2026), jsbeeb; reconfirmed on the Master 2026-09-02, where R7 can also
be left constant if only one cycle ever reaches it.
[Paradroid layer-3-scroll.md](https://github.com/kieranhj/paradroid-beeb/blob/main/docs/layer-3-scroll.md),
[Edge CLAUDE.md](https://github.com/kieranhj/edge-beeb/blob/master/CLAUDE.md),
[Edge layer-2-display.md](https://github.com/kieranhj/edge-beeb/blob/master/docs/layer-2-display.md),
[Edge layer-6e-titles.md](https://github.com/kieranhj/edge-beeb/blob/master/docs/layer-6e-titles.md)

- **A cycle's total rows must sum to 39 (312 scanlines) or the picture rolls.** `38 x 8 + 8 = 312`
  was confirmed by counting VSyncs: 1,000 fields in 39,936,000 cycles exactly.
  Measured: Layer 3, jsbeeb. [Paradroid layer-3-scroll.md](https://github.com/kieranhj/paradroid-beeb/blob/main/docs/layer-3-scroll.md)
- **R7 written for the panel cycle must go in at VSync, not at the first timer fire.** With VSync
  moved to tail row 4 or 5, a 7-row panel cycle reached the stale R7 before fire 1 and fired a
  second VSync of its own, re-entering the handler mid-frame; the play area went black.
  Measured: 2026-08-21, jsbeeb, found by building it. [Paradroid layer-3-scroll.md](https://github.com/kieranhj/paradroid-beeb/blob/main/docs/layer-3-scroll.md)
- **Where VSync falls in the frame decides where the picture sits on the tube.** Moving VSync
  earlier in your frame moves the picture down; only the front/back porch split changes.
  Measured: 2026-08-21, by eye on b-em and jsbeeb (`FRAME_DROP_ROWS`). [Paradroid layer-3-scroll.md](https://github.com/kieranhj/paradroid-beeb/blob/main/docs/layer-3-scroll.md)

### The R5 trap

- **Never write R5 near a cycle boundary.** The vertical adjust counts up and compares against R5;
  change it after the count has passed the new value and the match never happens, so the adjust
  runs on to its 5-bit wrap, about 29 extra scanlines. In Paradroid it stretched a 64-scanline
  panel cycle to 85. R5's legal window is the whole cycle: use the middle of it.
  Measured: Layer 3, jsbeeb. [Paradroid layer-3-scroll.md](https://github.com/kieranhj/paradroid-beeb/blob/main/docs/layer-3-scroll.md)
- **R5 is sampled at each cycle's end**, so a value must be in place between the sample it must not
  disturb and the one it serves.
  Measured: Layer 3, jsbeeb (three-cycle smooth vertical scroll). [Paradroid layer-3-scroll.md](https://github.com/kieranhj/paradroid-beeb/blob/main/docs/layer-3-scroll.md)
- **Timer fires that must land in a cycle should overshoot the boundary by a few rows.** Sized to
  reach the boundary exactly, IRQ latency alone carried them into the previous cycle.
  Measured: Layer 3, jsbeeb, with a `DEBUG_RASTER` tint at each interrupt entry. [Paradroid layer-3-scroll.md](https://github.com/kieranhj/paradroid-beeb/blob/main/docs/layer-3-scroll.md)

### R8: blanking, skew, the cursor, interlace

- **R8's display-skew bits (`&30`) blank the display; `&00` turns it on.** It is the chip's own
  display enable, so there is no ULA serialiser artefact at the transition, and a write takes
  effect immediately: one landing in the displayed part of a scanline cuts that scanline part-way
  across.
  Measured: Layer 3, jsbeeb. [Paradroid layer-3-scroll.md](https://github.com/kieranhj/paradroid-beeb/blob/main/docs/layer-3-scroll.md)
- **`R6 = 0` is NOT a blank: it leaks one row.** The row counter is compared at the end of a row,
  so row 0 displays whatever R6 says. Paradroid showed a 640-byte stripe of play buffer for the
  3.7 s of a screen transition, and a top row full of a ZX0 stream at boot. Use R8.
  Measured: 2026-08-31, jsbeeb, twice (boot and teardown), screenshotted. [Paradroid loader-compression.md](https://github.com/kieranhj/paradroid-beeb/blob/main/docs/loader-compression.md) [Paradroid raster-timing.md](https://github.com/kieranhj/paradroid-beeb/blob/main/docs/raster-timing.md)
- **`R1 = 0` also blanks, and kills the row itself**, so it does not leak; Paradroid used it at boot
  before every blank moved to R8.
  Measured: 2026-08-31, jsbeeb. [Paradroid loader-compression.md](https://github.com/kieranhj/paradroid-beeb/blob/main/docs/loader-compression.md)
- **R8 blanking does not hide the CRTC cursor.** A one-frame white dash appeared during loading
  with `R8 = &30`: the MODE 7 prompt cursor blinking. `R10 = &20` alongside the blank fixes it.
  `VDU 22` resets both R8 and R10.
  Measured: 2026-09-02, jsbeeb. [Edge layer-2-display.md](https://github.com/kieranhj/edge-beeb/blob/master/docs/layer-2-display.md)
- **Interlace must be off (`R8 = 0`) for a rupture.** The OS leaves MODE 1 at `R8 = 1` (interlace
  sync), which offsets VSync by half a scanline on alternate fields; timer intervals from VSync then
  land the split in a different place every other field, an intermittent glitch along the top of
  the play area.
  Measured: Layer 3, jsbeeb: consecutive fields render identically with interlace off. [Paradroid layer-3-scroll.md](https://github.com/kieranhj/paradroid-beeb/blob/main/docs/layer-3-scroll.md)

### The display window and the hardware wrap

- **The display window must fit inside ONE hardware wrap.** The address translator subtracts its
  mode amount once, when MA12 goes high; it does not iterate. A window larger than the wrap span
  fetches from `&8000` upwards (ROM) at some scroll positions and shows garbage on the last rows.
  With the 10K wrap and 80-unit rows the strip is exactly 16 rows, so 16 displayed rows is the
  ceiling, and 1-scanline vertical scrolling costs one row of play area.
  Measured: Layer 3, jsbeeb: at `scrollS = 10200` the model predicted garbage from unit 5 of the
  bottom row onward, and that is where it started. [Paradroid layer-3-scroll.md](https://github.com/kieranhj/paradroid-beeb/blob/main/docs/layer-3-scroll.md)
- **A 16K play buffer with 640-byte rows does not wrap on a row boundary** (16,384 / 640 = 25.6), so
  a sprite's columns can straddle `&8000` and stop being 8 bytes apart.
  Established: 2026-09-03, by arithmetic and a sprite test in jsbeeb (decision 21). [Edge decisions.md](https://github.com/kieranhj/edge-beeb/blob/master/docs/decisions.md)

### Switching between frame shapes

- **Writing a new R4/R5/R6/R7 set mid-frame costs malformed fields.** Paradroid measured
  38,378 / 49,154 / 6,168-cycle fields (300, 384 and 48 lines) across a switch into the rupture, and
  one 376-line field on the way out. Aligning the writes to row 0 of a fresh frame (wait for VSync,
  spin 8 rows) made every field 39,93x.
  Measured: 2026-08-31, jsbeeb, `run_frames(1)` stepping with `cycles_run` per field. [Paradroid raster-timing.md](https://github.com/kieranhj/paradroid-beeb/blob/main/docs/raster-timing.md)
- **A field of the right length can still be misplaced.** With the CRTC free-running in a 13-row
  tail shape whose VSync is at row 5, it VSyncs every 104 lines; the first VSync after an aligned
  switch came at line 104 instead of 312, one short field and one roll. **jsbeeb showed no fault;
  b2 rolled and KC photographed it.** The fix suppresses VSync (`R7 = 255`) across the intermediate
  cycles.
  Measured: 2026-08-31, b2 (photograph), then arithmetic; jsbeeb cannot see this one. [Paradroid raster-timing.md](https://github.com/kieranhj/paradroid-beeb/blob/main/docs/raster-timing.md)
- **Changing between a two-cycle and a four-cycle rupture from main-loop code costs one malformed
  field** (272 lines against 312) when R7 and the display wrap are written outside the VSync handler.
  Measured: 2026-09-04, jsbeeb, stepping fields. [Edge layer-6e-titles.md](https://github.com/kieranhj/edge-beeb/blob/master/docs/layer-6e-titles.md)
- **Leaving the CRTC in a rupture shape with nobody servicing the timers** runs the picture at
  roughly double rate: 14 CRTC frames of ~18,500 cycles in a 258,364-cycle window between
  `SetupRupture` and `InstallIrq`. Switch the CRTC on next to the IRQ that drives it.
  Measured: 2026-08-31, jsbeeb, `elapsed_cycles` and `frame_count` (which counts CRTC frames). [Paradroid raster-timing.md](https://github.com/kieranhj/paradroid-beeb/blob/main/docs/raster-timing.md)

---

## 2. Video ULA and the palette

- **Palette register `&FE21` takes `(logical << 4) OR (physical EOR 7)`.** The logical field is a
  content-addressable match: in a 4-colour mode only bits 7 and 5 are compared, so bits 6 and 4 must
  be written in every combination (four entries per logical colour) or the colour comes out split.
  Measured: Layer 3, jsbeeb; output identical to the `VDU 19` version. [Paradroid layer-3-scroll.md](https://github.com/kieranhj/paradroid-beeb/blob/main/docs/layer-3-scroll.md)
- **The MOS's default MODE 2 palette is logical n to physical n for all sixteen**, and
  `(n << 4) OR (n EOR 7)` reproduces it exactly. Logical 8-15 can be mapped back onto 0-7 without
  the flash bit, giving a second black that a sprite engine using 0 as its transparency key can use.
  Measured: 2026-09-05, jsbeeb. [Edge layer-8b-nula.md](https://github.com/kieranhj/edge-beeb/blob/master/docs/layer-8b-nula.md) [Edge layer-2-display.md](https://github.com/kieranhj/edge-beeb/blob/master/docs/layer-2-display.md)
- **A `&FE21` write from main-loop code lands wherever the raster is.** If a panel has its own
  palette applied at VSync, a mid-frame write leaves the panel in the wrong palette for the rest of
  the field: a one-frame flash, about one transition in three in Paradroid.
  Measured: 2026-08-31, jsbeeb, stepping a field at a time. [Paradroid raster-timing.md](https://github.com/kieranhj/paradroid-beeb/blob/main/docs/raster-timing.md)
- **A palette write can glitch a few displayed pixels at the beam position on the write line**
  (short dashes at flash peaks, over black). Stated in the intro's write-up as real-hardware
  behaviour shared with every mid-frame palette split; not separately measured. [Paradroid intro.md](https://github.com/kieranhj/paradroid-beeb/blob/main/docs/intro.md)
- **A per-scanline loop that opens with a write to `&FE21` is stable**, stated in Edge Grinder's
  titles write-up as being because the write is on the 1 MHz bus and stalls the CPU to the same
  phase each iteration. **KC disputes the reason (2026-09-07): writes to the Video ULA's palette
  register are NOT cycle-stretched to 1 MHz.** The loop's stability is observed; its explanation
  is unmeasured and probably wrong. To measure: time `STA &FE21` against `STA &FE4F` with a
  breakpoint pair. [Edge layer-6e-titles.md](https://github.com/kieranhj/edge-beeb/blob/master/docs/layer-6e-titles.md)
- **Why a palette write glitches pixels, and why all sixteen entries must always be programmed**
  (KC, 2026-09-07, from the ULA's design rather than a measurement): pixels are shifted out one
  bit at a time at the 16 MHz pixel clock, and the resulting bits are masked and looked up in
  the palette registers. A write that lands mid-pixel changes the lookup part way through, and
  because the lookup is always through all sixteen entries the whole table has to be set
  whatever the bits per pixel.

### Byte layouts

- **MODE 1**: pixel n takes bit `7-n` (high colour bit) and bit `3-n` (low bit). Solid colour
  0/1/2/3 = `&00`/`&0F`/`&F0`/`&FF`. A character is 16 bytes: the left half's 8 scanlines then the
  right half's. Within a row-aligned buffer,
  `addr = base + (y DIV 8)*640 + (x DIV 4)*8 + (y MOD 8)`. **Adjacent 4-pixel columns are 8 bytes
  apart, not 1**; consecutive bytes within a column are consecutive scanlines. This cost a build.
  Measured: Layer 3, jsbeeb. [Paradroid CLAUDE.md](https://github.com/kieranhj/paradroid-beeb/blob/main/CLAUDE.md)
- **MODE 2**: 2:1 pixels, two per byte, 640 bytes per character row (`R1 = 80`), 32 bytes per
  character cell; a CRTC unit is 2 px. The right-hand pixel of a byte lives in bits 6, 4, 2, 0
  (the four bits of its logical colour), the left in 7, 5, 3, 1.
  Established: Layer 1 (2026-09-02), by exporting column planes and checking the plot in jsbeeb. [Edge layer-1-graphics-pipeline.md](https://github.com/kieranhj/edge-beeb/blob/master/docs/layer-1-graphics-pipeline.md) [Edge CLAUDE.md](https://github.com/kieranhj/edge-beeb/blob/master/CLAUDE.md)

### VideoNuLA (Edge Grinder's `-Nula` build)

- **By default the NuLA composes both tables**: logical -> `&FE21` -> physical -> `&FE23` -> 12-bit
  RGB. `&FE22 = &11` (control 1, parameter 1) selects logical colour mapping and makes `&FE21`
  ignored. Without it, a title screen's per-scanline `&FE21` pulses wrecked the game's colours
  (a blue background instead of black).
  Measured: 2026-09-05, **real hardware first** (KC ran the CPC build), then jsbeeb; encoding
  cross-checked against the VideoNuLA User Guide's worked example. [Edge layer-8b-nula.md](https://github.com/kieranhj/edge-beeb/blob/master/docs/layer-8b-nula.md)
- **Palette entries go to `&FE23` as two bytes each, `[index<<4 | red]` then `[green<<4 | blue]`,
  in that order.** `&FE22 = &40` resets extended features first.
  Measured: 2026-09-05, jsbeeb, against the reference library's default table byte for byte. [Edge layer-8b-nula.md](https://github.com/kieranhj/edge-beeb/blob/master/docs/layer-8b-nula.md)

---

## 3. The System VIA

### The display wrap (addressable latch lines 4 and 5)

The hardware wrap is what is added back when the display address passes `&8000`. The four sizes
are **not powers of two**:

| Line 4 | Line 5 | Wraps `&8000` to | Size | Notes |
|---|---|---|---|---|
| 0 | 0 | `&4000` | 16K | |
| 1 | 0 | `&6000` | 8K | |
| 0 | 1 | `&3000` | 20K | the MOS's own setting for MODE 2 |
| 1 | 1 | `&5800` | 10K | Paradroid's play strip |

Written as `lda #4` / `lda #12` to `&FE40` for line 4 clear/set, `#5` / `#13` for line 5.
Measured: 2026-09-04, jsbeeb (the 10K case independently in Paradroid's Layer 3).
[Edge layer-6e-titles.md](https://github.com/kieranhj/edge-beeb/blob/master/docs/layer-6e-titles.md),
[Edge CLAUDE.md](https://github.com/kieranhj/edge-beeb/blob/master/CLAUDE.md),
[Paradroid layer-3-scroll.md](https://github.com/kieranhj/paradroid-beeb/blob/main/docs/layer-3-scroll.md)

### Timers

- **T1 in continuous mode, not T2, for raster timing.** T2 is one-shot only, so the interval
  starts when the handler writes `T2C-H` and every interrupt's service latency feeds into the next
  interval. T1 auto-reloads from its latch at underflow, so the period is exact however late the
  service; restart it at VSync and the fires stay phase-locked. A latch write takes effect one
  reload later, so intervals are set one fire ahead.
  Established: Layer 3 (August 2026), jsbeeb, after T2 was tried first. [Paradroid layer-3-scroll.md](https://github.com/kieranhj/paradroid-beeb/blob/main/docs/layer-3-scroll.md)
- **T1 ticks at 1 MHz; a scanline is 64 ticks (`SL = 64`).**
  Measured: 2026-09-02, jsbeeb (see the timing constants in section 8). [Edge CLAUDE.md](https://github.com/kieranhj/edge-beeb/blob/master/CLAUDE.md)
- **A `&FE44` read at a fixed point in a VSync-locked loop is NOT random.** Under the MOS, System
  VIA T1 runs the 100 Hz tick: 20,000 cycles, exactly half a frame, so the sampled byte is
  near-constant and drifts only with interrupt jitter. It cost Paradroid's loading intro its
  lightning randomness. Use a stepped PRNG with the timer as seed only.
  Measured: 2026-08-26, jsbeeb (KC saw near-constant flashes; logging the trigger confirmed it). [Paradroid intro.md](https://github.com/kieranhj/paradroid-beeb/blob/main/docs/intro.md) [Paradroid CLAUDE.md](https://github.com/kieranhj/paradroid-beeb/blob/main/CLAUDE.md)
- **User VIA T1C-L is only a usable seed if it is free-running.** Code that had retuned it to
  continuous mode with a `&00FF` latch handed the game a counter that spanned 0-255 every 257 us,
  phase-locked to a deterministic boot: the same value every time.
  Measured: 2026-08-30, jsbeeb. [Paradroid intro.md](https://github.com/kieranhj/paradroid-beeb/blob/main/docs/intro.md)
- **A T1 difference used as a stopwatch is only modular while the counter does not pass zero
  between the reads.** When it does, that sample gains ~65,536 ticks (131,000 cycles), and because
  the reload point drifts slowly the bad readings come in consecutive runs. Paradroid's
  `DEBUG_TIME` reported 2,903 cycles for code measured at 1,009 by breakpoints.
  Measured: 2026-08-26, jsbeeb. [Paradroid raster-timing.md](https://github.com/kieranhj/paradroid-beeb/blob/main/docs/raster-timing.md)
- **T2's two bytes are read one after the other and the counter can roll between them**, so an
  elapsed reading can come out 256 us smaller than the mark before it; an unsigned maximum then
  stores a ~65,000 us junk value. A frame longer than 65.5 ms wraps the counter outright. Reject a
  sample whose subtraction borrows.
  Measured: 2026-09-04, jsbeeb; three readings of three were junk before the fix. [Edge performance.md](https://github.com/kieranhj/edge-beeb/blob/master/docs/performance.md)

### VSync

- **The VSync CA1 interrupt is serviced about 4 scanlines after the VSync edge.** The timer chain
  itself is exact (breakpoint bisection put fire 1 at 78.3-79.3 scanlines after handler entry
  against a design figure of 78); the whole error is in where VSync itself sits.
  Measured: Layer 3, jsbeeb. Note the scanline component cannot be read from screenshots better
  than +/-2; it was KC spotting two wrong lines on b-em that pinned it. [Paradroid layer-3-scroll.md](https://github.com/kieranhj/paradroid-beeb/blob/main/docs/layer-3-scroll.md)
- **Polling `&FE4D` bit 1 for VSync races the MOS**, whose own handler clears the flag when it
  services VSync; chain on IRQ1V instead while the MOS is alive. Stated as the reason for the
  design; not separately measured. [Paradroid layer-3-scroll.md](https://github.com/kieranhj/paradroid-beeb/blob/main/docs/layer-3-scroll.md)
- **With interrupts down, polling the System VIA's VSync flag directly works** (Edge Grinder's
  memorial fade does exactly that before `install_irq`).
  Measured: Layer 9d (2026-09-05), jsbeeb. [Edge CLAUDE.md](https://github.com/kieranhj/edge-beeb/blob/master/CLAUDE.md)
- **Taking IRQ1V outright**: disable every interrupt source on both VIAs except System VIA CA1 and
  T1, or anything unserviced holds the IRQ line asserted forever. The MOS saves the interrupted A in
  `&FC` but not X or Y.
  Established: Layer 3, jsbeeb. [Paradroid layer-3-scroll.md](https://github.com/kieranhj/paradroid-beeb/blob/main/docs/layer-3-scroll.md)

### Reading the keyboard direct

- **The sequence**: port B's low nibble is the addressable latch, `(value << 3) | line`. Drop line
  3 (the keyboard write-enable) and the hardware's free-running column scan stops. `DDRA = &7F`
  makes PA0-PA6 outputs carrying the internal key number (PA0-PA3 column, PA4-PA6 row) and leaves
  PA7 an input carrying the answer. Write the key number to **`&FE4F`** (the no-handshake register;
  `&FE41` strobes CA2), read PA7 back. Testing Z (internal `&61`): key up reads `&61`, key down
  reads `&E1`. It tests one named key; there is no iteration.
  Measured: 2026-08-26, jsbeeb, ported from Thrust's `test_inkey`. [Paradroid raster-timing.md](https://github.com/kieranhj/paradroid-beeb/blob/main/docs/raster-timing.md)
- **69 cycles direct against 243 through `OSBYTE &81`**, `JSR` to `RTS` inclusive. The OSBYTE
  figure was taken twice by different routes (a poll-loop rate and a `DEBUG_TIME` bracket, 238 and
  237); the direct figure is a breakpoint pair differencing `elapsed_cycles`.
  Measured: 2026-08-26, jsbeeb. [Paradroid raster-timing.md](https://github.com/kieranhj/paradroid-beeb/blob/main/docs/raster-timing.md)
- **The 26 masked cycles (`PHP`/`SEI`/`PLP` round the sequence), twelve times a pass, cost a
  T1-driven rupture nothing**: 25.0 Hz before and after, panel boundary clean while scrolling.
  Measured: 2026-08-26, jsbeeb. [Paradroid raster-timing.md](https://github.com/kieranhj/paradroid-beeb/blob/main/docs/raster-timing.md)
- **Port A is shared with the SN76489 write path.** A sound write from the IRQ that saves and
  restores DDRA and ORA around its strobe does not disturb a foreground keyboard poll: key up,
  0 of 8,192 polls read down with 225 IRQ writes interleaved; key held, 8,192 of 8,192 with 192
  interleaved. The sound strobe touches only latch bit 0, never the keyboard-enable bit.
  Measured: 2026-08-21, jsbeeb, `tools/sndtest.asm`. [Paradroid layer-11e-sound.md](https://github.com/kieranhj/paradroid-beeb/blob/main/docs/layer-11e-sound.md)
- **Phantom keys.** The matrix has no diodes, so five keys held at once can phantom a sixth, and
  asking about one key at a time does not save you from it: Z, X, K, M and L together triggered a
  debug key on C. Reported by KC on real hardware; addressed by gating every debug key on CTRL.
  A phantom that lands on a play control is still open. [Paradroid human-notes-status.md](https://github.com/kieranhj/paradroid-beeb/blob/main/docs/human-notes-status.md)
- **`DDRA` need not be restored** after a direct read while nothing else assumes it; the MOS sets
  it in its own scan and the sound driver saves what it finds. Stated with the reason; not
  measured as a fault. [Paradroid raster-timing.md](https://github.com/kieranhj/paradroid-beeb/blob/main/docs/raster-timing.md)

---

## 4. Master 128 only

### Shadow RAM and ACCCON (`&FE34`)

- **The shadow display bit (D, bit 0) flips cleanly inside the VSync handler**, so a main/shadow
  double buffer can be swapped in vertical blanking with the scroll address.
  Measured: 2026-09-02, jsbeeb: 10 game frames in 20 fields with `FRAME_LOCK = 2`. [Edge layer-2-display.md](https://github.com/kieranhj/edge-beeb/blob/master/docs/layer-2-display.md)
- **The display bank can be switched INSIDE a frame**, taking effect at the next character fetch: a
  VSync-synced delay loop flipping D put main RAM above the switch and shadow below it, with a step
  part way along the scanline the write landed in. Place the write in horizontal blanking, or in a
  row nobody fetches. **jsbeeb only; b-em has NOT been checked.**
  Measured: 2026-09-04, jsbeeb. [Edge CLAUDE.md](https://github.com/kieranhj/edge-beeb/blob/master/CLAUDE.md) [Edge layer-6e-titles.md](https://github.com/kieranhj/edge-beeb/blob/master/docs/layer-6e-titles.md)
- **The hardware wrap applies inside whichever bank is displayed.** With D = 1 and the wrap at 8K, a
  display crossing `&8000` lands on shadow `&6000`, not main. One ring per bank.
  Measured: 2026-09-04, jsbeeb. [Edge CLAUDE.md](https://github.com/kieranhj/edge-beeb/blob/master/CLAUDE.md)
- **Nothing displayed may live below `&3000`.** jsbeeb displayed a panel at `&2000` under both
  shadow states; b-em showed garbage on alternate frames. The two emulators disagree about what
  the video fetches there with D set, and **real hardware is untested either way**. KC's
  hypothesis (2026-09-07), worth checking: with the shadow bit set, a CRTC address below `&3000`
  reads ANDY and HAZEL rather than main RAM, which would explain b-em's alternate-frame garbage.
  Measured: 2026-09-02, jsbeeb and b-em (KC), decision 17. [Edge layer-2-display.md](https://github.com/kieranhj/edge-beeb/blob/master/docs/layer-2-display.md) [Edge decisions.md](https://github.com/kieranhj/edge-beeb/blob/master/docs/decisions.md)
- **The shadow screen is 20K of RAM nobody is looking at while main is displayed**, so with
  D = 0 and X = 1 (CPU sees shadow) it is a free staging area for compressed streams at boot.
  Measured: 2026-09-04, jsbeeb. [Edge layer-9-loader.md](https://github.com/kieranhj/edge-beeb/blob/master/docs/layer-9-loader.md)

### ANDY

- **ANDY is 4K at `&8000-&8FFF`, selected by ROMSEL bit 7, and overlays ONLY that 4K.** Writing
  `&AA` to `&8000` with bank 4 selected and `&55` to `&8000` with `&84` selected gives back `&55`
  under `&84` and `&AA` under `4`; `&9000` is the selected bank either way. **The test has to be
  machine code**: BASIC is itself the ROM at `&8000`, so paging ANDY in from a BASIC session removes
  the interpreter mid-statement and hangs.
  Measured: 2026-09-04, jsbeeb, from 6502 in main RAM. [Edge layer-7-music.md](https://github.com/kieranhj/edge-beeb/blob/master/docs/layer-7-music.md) [Edge CLAUDE.md](https://github.com/kieranhj/edge-beeb/blob/master/CLAUDE.md)
- **The loader cannot write into ANDY while the filing system is running**; Edge Grinder loads the
  ANDY stream before its last file and unpacks it afterwards.
  Established: Layer 7 (2026-09-04), jsbeeb. [Edge CLAUDE.md](https://github.com/kieranhj/edge-beeb/blob/master/CLAUDE.md)

### HAZEL

- **HAZEL (`&C000-&DFFF`, ACCCON bit 3, Y) is the filing system's workspace.** Take it and BREAK
  must clear memory: a soft BREAK out of the game gave `Acorn MOS` with no DFS banner and `*CAT`
  returned nothing. `OSBYTE 200, X=3` at the top of the program makes BREAK a power-on reset (bit 1)
  and disables ESCAPE (bit 0); afterwards BREAK gave a clean `Acorn 1770 DFS` and SHIFT+BREAK
  reloaded the game. Load HAZEL's contents LAST and touch the disc no more.
  Measured: 2026-09-04, jsbeeb, before and after. [Edge layer-7-music.md](https://github.com/kieranhj/edge-beeb/blob/master/docs/layer-7-music.md)
- **OSFILE cannot write into HAZEL** (the MOS would be overwriting its own workspace from
  underneath itself); stage in RAM and copy or unpack up with Y set. Stated as the reason for the
  staging design. [Edge layer-7-music.md](https://github.com/kieranhj/edge-beeb/blob/master/docs/layer-7-music.md)
- **`&FFFE` on this Master reads `&E59E`**, above HAZEL's `&DFFF`, so paging HAZEL in cannot break
  interrupt dispatch.
  Measured: 2026-09-04, jsbeeb, read out of the machine. [Edge layer-7-music.md](https://github.com/kieranhj/edge-beeb/blob/master/docs/layer-7-music.md)
- **Sideways bank `&BFFF` and HAZEL `&C000` are adjacent and both visible at once** (different
  registers, different windows), so a pointer walking off the end of a bank lands in HAZEL and a
  data stream can lie across the join. Two of Edge Grinder's eleven music streams do.
  Measured: 2026-09-04, jsbeeb: SN76489 captures match the reference VGM across the join. [Edge layer-7-music.md](https://github.com/kieranhj/edge-beeb/blob/master/docs/layer-7-music.md)
- **The MOS user-font page `&0C00` and `&0800-&0BFF` (sound, serial, soft keys) are yours once the
  MOS interrupt is gone**; `&0400-&07BF` (language workspace) once `*RUN` has handed over. Both
  verified by sentinel.
  Measured: Layer 2 onward (September 2026), jsbeeb. [Edge CLAUDE.md](https://github.com/kieranhj/edge-beeb/blob/master/CLAUDE.md)

### Real hardware

- **A real Master 128 runs the Paradroid port** (shadow RAM, a different `PAGE`, the 65C12 the port
  does not use), the first time either port ran on hardware rather than an emulator. Real B, B+,
  DFS 2.26 and second processors remain untested.
  Reported: 2026-09-06, KC, real Master 128. [Paradroid layer-13-compatibility.md](https://github.com/kieranhj/paradroid-beeb/blob/main/docs/layer-13-compatibility.md)

---

## 5. Model B sideways RAM

- **Do not assume banks 4-7.** KC's own emulator had sideways RAM in slots 0-3; a game that assumed
  4-7 unpacked its banks into slots that were not there, every `*LOAD` appeared to succeed, and the
  first call into bank code crashed. On a machine that has 4-7 (jsbeeb, the development desk) the
  assumption is right by coincidence.
  Measured: 2026-08-29, KC's emulator configuration. [Paradroid intro.md](https://github.com/kieranhj/paradroid-beeb/blob/main/docs/intro.md)
- **Probe at boot, with stnicc-beeb's method**: sixteen DISTINCT values, because a board decoding
  three select bits answers for N and N+8 with the same RAM (bank aliasing); a second, latched pass
  for Solidisk boards, which want the index in the User VIA and `&FE32` too, run only when the first
  pass found fewer than four. **Probe only banks the MOS found no ROM in** (`&02A1`, the ROM type
  table): the probe writes a byte at `&8008`, and doing that to a live utility ROM or a sideways-RAM
  filing system hangs a working machine. Select the bank (`STY ROMSEL`) before reading the byte you
  save, or stage 3 restores bank 0's byte into every RAM bank.
  Built and measured: 2026-08-29, jsbeeb `B-DFS1.2` (eight RAM banks, picks 4-7) and a Master. [Paradroid layer-13-compatibility.md](https://github.com/kieranhj/paradroid-beeb/blob/main/docs/layer-13-compatibility.md)
- **Take the four highest-numbered RAM banks**: the banks that matter to other people sit low, and
  on a machine with exactly 4-7 the answer is unchanged.
  Decided: 2026-08-29 (KC). [Paradroid layer-13-compatibility.md](https://github.com/kieranhj/paradroid-beeb/blob/main/docs/layer-13-compatibility.md)
- **A bank-number handover at `&0A00` (the printer buffer) survives BASIC dispatching the next
  exec line, DFS loading over `&1100-&2FFF`, and MODE 1's clear of `&3000-&7FFF`.** It does NOT
  survive a program that unpacks tables over `&0400-&1BFF`; that is how the 4-7 assumption crept
  back in.
  Measured: 2026-08-29, jsbeeb (`&0A00` reads `FF` after both refusal paths; the trap found on
  KC's emulator). [Paradroid layer-13-compatibility.md](https://github.com/kieranhj/paradroid-beeb/blob/main/docs/layer-13-compatibility.md) [Paradroid intro.md](https://github.com/kieranhj/paradroid-beeb/blob/main/docs/intro.md)
- **Only one bank is visible at a time, and the IRQ fires with whatever the foreground has
  paged.** An IRQ that needs a bank must save the ROMSEL shadow (`&F4`), page, and restore both;
  writing the shadow first is what keeps the claim consistent.
  Established: 2026-08-21, jsbeeb (Paradroid's sound tick, ~60-80 cycles of overhead). [Paradroid layer-11e-sound.md](https://github.com/kieranhj/paradroid-beeb/blob/main/docs/layer-11e-sound.md)
- **Bank code may call main RAM freely; main RAM may call into a bank only with that bank paged**,
  and a bank routine may not call main-RAM code that pages a different bank and restores somebody
  else's. Both ports broke the second rule within a day of writing it down.
  Established: 2026-08-29 (Paradroid's resident depacker) and 2026-09-06 (Edge's `bank_call`). [Paradroid loader-compression.md](https://github.com/kieranhj/paradroid-beeb/blob/main/docs/loader-compression.md) [Edge layer-9h-keyredef.md](https://github.com/kieranhj/edge-beeb/blob/master/docs/layer-9h-keyredef.md)

---

## 6. The MOS and DFS: workspace you can reclaim, and the traps

| Range | What it is | Yours when | Trap |
|---|---|---|---|
| `&0100-&017F` | bottom half of the stack page | measured untouched through play, deck load, console and game over including `*LOAD`s | not loadable from disc; paths not exercised invalidate the measurement |
| `&0400-&07FF` | language workspace | after `*RUN` (Edge, verified by sentinel) | Paradroid's briefing lives here; the ceiling is `&0800` |
| `&0800-&08FF` | MOS sound: `&800-&83F` workspace, `&840-&87F` channel queues, `&8C0-&8FF` envelopes | only while you own IRQ1V | see below |
| `&0800-&0BFF` | sound, serial, soft keys | once the MOS interrupt is gone (Edge, sentinel) | |
| `&0A00` | printer buffer | survives BASIC exec, DFS loads, `VDU 22` | inside pdloader's tables |
| `&0C00-&0CFF` | user-defined characters | once the MOS is not printing | |
| `&0D00-&0D5F` | NMI routine (DFS) | never while the disc is in use | |
| `&0D9F+` | extended vector table; DFS 1.2's FILEV route into its ROM | after the last filing call | trample it and the next call crashes |
| `&0DF0-&0DFF` | ROM private workspace | excluded | |
| `&0E00-&10FF` | DFS shared workspace | dead from the last `*LOAD` on | nothing may be LOADED there |
| `&1100-&18FF` | DFS random-access buffers, untouched by `*LOAD`/OSFILE | immediately; worth 2K below `PAGE = &1900` | `!BOOT`'s exec buffer, while the exec file is open |

Measured: Paradroid Layers 3, 11e, 13 (2026-08 to 2026-08-31), jsbeeb; Edge Layer 2 onward.
[Paradroid CLAUDE.md](https://github.com/kieranhj/paradroid-beeb/blob/main/CLAUDE.md),
[Paradroid layer-11e-sound.md](https://github.com/kieranhj/paradroid-beeb/blob/main/docs/layer-11e-sound.md),
[Paradroid layer-13-compatibility.md](https://github.com/kieranhj/paradroid-beeb/blob/main/docs/layer-13-compatibility.md),
[Edge CLAUDE.md](https://github.com/kieranhj/edge-beeb/blob/master/CLAUDE.md)

- **The MOS plays your data as notes.** Hand IRQ1V back with a charset over `&0800-&08FF` and the
  MOS's 100 Hz sound driver finds its queue pointers and buffers full of bitmaps: a quiet, rising
  sequence that a game's own mute cannot touch (chip read CH0 att 14, CH1 att 13, periods falling
  401 -> 146 -> 95). Zeroing `&0800-&087F` stopped it instantly. **Sound suppression (`OSBYTE &D2`)
  does NOT stop it**: it gates new `SOUND` commands, not a draining queue. `OSBYTE &0F, X=0` (flush
  every buffer) BEFORE uninstalling the IRQ is the fix.
  Measured: 2026-08-26, jsbeeb. [Paradroid layer-11e-sound.md](https://github.com/kieranhj/paradroid-beeb/blob/main/docs/layer-11e-sound.md)
- **The MOS's 100 Hz IRQ writes `&0800-&08FF` while it owns the machine**, so a compressed stream
  staged there at boot is corrupted mid-decode: one byte changed sends the depacker off a wrong
  offset (542 wrong bytes across the credits, found by diffing the depacked screen, not by looking
  at it). `&1100` is the safe staging address.
  Measured: 2026-08-30, jsbeeb. [Paradroid intro.md](https://github.com/kieranhj/paradroid-beeb/blob/main/docs/intro.md)
- **`VDU 22` clears `&3000-&7FFF`**, what the OS thinks is its screen, so data loaded above `&3000`
  is wiped before it can be read; it also re-enables R8 and the cursor.
  Measured: Layer 3 (Paradroid), 2026-09-02 (Edge), jsbeeb. [Paradroid CLAUDE.md](https://github.com/kieranhj/paradroid-beeb/blob/main/CLAUDE.md) [Edge layer-9-loader.md](https://github.com/kieranhj/edge-beeb/blob/master/docs/layer-9-loader.md)
- **OSFILE writes a file's catalogue addresses back into its parameter block after a load**, so
  reset load/exec before every call or the second file lands wherever the first said.
  Measured: Layer 2 (2026-09-02), jsbeeb. [Edge CLAUDE.md](https://github.com/kieranhj/edge-beeb/blob/master/CLAUDE.md)
- **Every `*LOAD`/OSFILE must happen before you take IRQ1V**: taking it stops the MOS servicing the
  filing system.
  Established: Layer 3, jsbeeb. [Paradroid layer-3-scroll.md](https://github.com/kieranhj/paradroid-beeb/blob/main/docs/layer-3-scroll.md)
- **The MOS's disc code needs VSync.** With the CRTC's R7 parked where VSync never fires, the second
  `*LOAD` hung forever in DFS's 8271 status poll at `&ACAE`; bisecting the CRTC writes one at a time
  showed R7 was the trigger.
  Measured: Layer 3 (August 2026), jsbeeb. [Paradroid bug-map-corruption.md](https://github.com/kieranhj/paradroid-beeb/blob/main/docs/bug-map-corruption.md)
- **The DFS ROM is paged in at `&8000` during a filing-system call**, so a bank cannot be loaded
  at `&8000` even uncompressed; stage below and copy or unpack.
  Established: Layer 13d (2026-08), jsbeeb. [Paradroid CLAUDE.md](https://github.com/kieranhj/paradroid-beeb/blob/main/CLAUDE.md)
- **DFS throughput is about 0.07 s a sector, plus about 0.7 s once per path for the first access
  after the drive has been idle** (motor spin-up). The same 368-byte file cost 0.181 s or 0.902 s
  depending on nothing but context; every non-first load sat in 0.046-0.091 s/sector with no
  measurable per-file overhead, so merging files buys nothing. Effective raw rate ~5.6 KB/s,
  ~14 sectors/s. **This is jsbeeb's disc model**; the port flagged that a faster reader's gain is
  only real if the model is faithful.
  Measured: 2026-08-29, jsbeeb, breakpoints on the `JSR &FFF7` sites and `elapsed_cycles`. [Paradroid loader-compression.md](https://github.com/kieranhj/paradroid-beeb/blob/main/docs/loader-compression.md)
- **OSFILE loading 21K on the emulated 1770 DFS takes ~130 fields**, with the PC sitting in the DFS
  NMI routine at `&0D50` for most of it. That is not a crash.
  Measured: 2026-09-02, jsbeeb (Master). [Edge layer-2-display.md](https://github.com/kieranhj/edge-beeb/blob/master/docs/layer-2-display.md)
- **beebasm lays files on the disc in SAVE order**, which put `!BOOT` and the main executable
  physically last; every boot read the end of the disc and seeked back to track 0. Reordering into
  boot access order was the whole of a 6.01M -> 4.33M cycle saving on the first boot phase.
  Measured: 2026-08-21, jsbeeb. [Paradroid loader-compression.md](https://github.com/kieranhj/paradroid-beeb/blob/main/docs/loader-compression.md)
- **While `!BOOT` is being EXECed, INKEY and OSRDCH read the exec stream, not the keyboard.** An
  intro's INKEY(0) consumed the `*` of the next `*RUN` line. Use the `OSBYTE &7A` keyboard scan for
  "any key". A program that `*TAPE`s must close the exec file first.
  Measured: 2026-08-26 and 2026-08-29, jsbeeb. [Paradroid intro.md](https://github.com/kieranhj/paradroid-beeb/blob/main/docs/intro.md)
- **`*FX 4,1` stops the cursor keys doing cursor editing; `*FX 229,1` stops BASIC eating ESCAPE**
  when measuring keys from a BASIC session.
  Measured: Layer 3 (Paradroid), 2026-09-06 (Edge). [Paradroid layer-3-scroll.md](https://github.com/kieranhj/paradroid-beeb/blob/main/docs/layer-3-scroll.md) [Edge CLAUDE.md](https://github.com/kieranhj/edge-beeb/blob/master/CLAUDE.md)
- **DFS filenames are seven characters.**
  [Paradroid CLAUDE.md](https://github.com/kieranhj/paradroid-beeb/blob/main/CLAUDE.md)

---

## 7. Keyboard internal key numbers

- **Internal key numbers are measured, never recalled.** The scan form is `A%=121:X%=16:Y%=0`
  (OSBYTE 121 scanning from key 16) in a BASIC loop with the key held, proved against a number the
  port already had (Z = 97) before it was trusted. **The MOS scan will not report keys 0-2** (SHIFT,
  CTRL), and `OSBYTE &7A` starts at 16 for the same reason; those were measured through INKEY and
  calibrated on a known key: **internal = (-INKEY) - 1** (Z is INKEY -98, internal 97). Paradroid
  derives the same thing as `INKEY byte EOR &FF`.
  Measured: 2026-09-06 (Edge, jsbeeb Master 128); Paradroid's table agrees on every key and is the
  cross-check, not the source. [Edge layer-9h-keyredef.md](https://github.com/kieranhj/edge-beeb/blob/master/docs/layer-9h-keyredef.md) [Paradroid layer-11e-sound.md](https://github.com/kieranhj/paradroid-beeb/blob/main/docs/layer-11e-sound.md)

| Key | Internal | Key | Internal | Key | Internal | Key | Internal |
|---|---|---|---|---|---|---|---|
| A | 65 | K | 70 | U | 53 | UP | 57 |
| B | 100 | L | 86 | V | 99 | DOWN | 41 |
| C | 82 | M | 101 | W | 33 | LEFT | 25 |
| D | 50 | N | 85 | X | 66 | RIGHT | 121 |
| E | 34 | O | 54 | Y | 68 | SHIFT | 0 |
| F | 67 | P | 55 | Z | 97 | CTRL | 1 |
| G | 83 | Q | 16 | `/` | 104 | RETURN | 73 |
| H | 84 | R | 51 | `:` | 72 | SPACE | 98 |
| I | 37 | S | 81 | | | ESCAPE | 112 |
| J | 69 | T | 35 | | | | |

INKEY (negative) codes confirmed in Paradroid's Layer 3 through `OSBYTE &81`: Z -98, X -67,
K -71, M -102, UP -58, DOWN -42; CTRL is INKEY -2 (`KEY_CTRL = &FE`).
[Paradroid layer-3-scroll.md](https://github.com/kieranhj/paradroid-beeb/blob/main/docs/layer-3-scroll.md),
[Paradroid layer-11e-sound.md](https://github.com/kieranhj/paradroid-beeb/blob/main/docs/layer-11e-sound.md)

- **`OSBYTE &7A`'s no-key return is documented as X = 0 (NAUG) but the MOS in jsbeeb returns
  `&FF`**; treat both as idle.
  Measured: 2026-08-26, jsbeeb. [Paradroid intro.md](https://github.com/kieranhj/paradroid-beeb/blob/main/docs/intro.md)
- **Edge-triggered keys must not block waiting for release** where two can be held together, or the
  loop deadlocks swallowing the press.
  Measured: Layer 3, jsbeeb. [Paradroid layer-3-scroll.md](https://github.com/kieranhj/paradroid-beeb/blob/main/docs/layer-3-scroll.md)

---

## 8. 6502 cycle facts and measured timing constants

- **`LDA abs` is 4 cycles and `LDA zp` is 3, but `LDA abs,X` and `LDA zp,X` are both 4.** Zero page
  went to scalars; indexed tables gained nothing by moving.
  Established: RAM pass (2026-08-25), from the cycle tables, worth knowing before costing a
  zero-page change. [Paradroid CLAUDE.md](https://github.com/kieranhj/paradroid-beeb/blob/main/CLAUDE.md)
- **`LDX zp,Y` is a legal mode**, one byte shorter and a cycle cheaper than `LDX abs,Y`; and
  `ldx zpaddr` is the same two bytes `ldx #imm` was, so moving a constant table into zero page can
  cost nothing at its call sites.
  Established: 2026-09-06, from the listing. [Edge layer-9h-keyredef.md](https://github.com/kieranhj/edge-beeb/blob/master/docs/layer-9h-keyredef.md)
- **IRQ latency swings by more than a few cycles**: the 6502 finishes the instruction it is on, and
  a `SEI` window in the foreground (17 cycles in Paradroid's `SetCRTCStart`) adds to it. A CRTC write
  with 3-7 cycles of margin to the end of horizontal blanking overran intermittently and showed a
  character of the next row in the bottom-left corner.
  Measured: 2026-09-06, jsbeeb, phase of the `STA CRTC_DATA` against a `run_frames` anchor,
  differenced mod 128. [Paradroid raster-timing.md](https://github.com/kieranhj/paradroid-beeb/blob/main/docs/raster-timing.md)
- **Self-modified base addresses argue against unrolling**: unrolling by eight multiplies the
  addresses that have to be patched, not the loop overhead saved (about 64 cycles a row against 24
  saved). Count the patches first.
  Measured: 2026-09-04, jsbeeb (`scroll_frame` 5,951 us -> 5,106 us by deleting a pass instead). [Edge performance.md](https://github.com/kieranhj/edge-beeb/blob/master/docs/performance.md)

### Measured timing constants

| Quantity | Value | Measured |
|---|---|---|
| One scanline | **128 CPU cycles at 2 MHz** (64 us), not 64 cycles | 2026-08-15, corrected a wrong earlier figure |
| One field | 312 scanlines, **39,936 cycles** | 1,000 fields in 39,936,000 cycles, Layer 3 |
| One 25 Hz pass (two fields) | 79,872 cycles | 128 passes in 10,223,616 cycles |
| MODE 1 scanline | display is cycles 0-79, blanking 80-127 | 2026-09-06 |
| MODE 1 blanking window | ~24 us to land a CRTC write in | Layer 3 |
| T1 tick | 1 MHz; `SL = 64` ticks a scanline | 2026-09-02 |
| A 25 Hz frame in T1 terms | 39,936 us | |

[Paradroid raster-timing.md](https://github.com/kieranhj/paradroid-beeb/blob/main/docs/raster-timing.md),
[Paradroid layer-3-scroll.md](https://github.com/kieranhj/paradroid-beeb/blob/main/docs/layer-3-scroll.md),
[Edge CLAUDE.md](https://github.com/kieranhj/edge-beeb/blob/master/CLAUDE.md)

### The two ruptures' T1 constants

| Port | Constant | Value | What it gives |
|---|---|---|---|
| Paradroid (three cycles, MODE 1) | `T1_I1` | `(84 + FRAME_DROP_ROWS * 8) * SL - 2 + T1_TUNE` | VSync handler to fire 1; VSync and this move together |
| Paradroid | `T1_TUNE` | `-4 * SL - 32` (was `-22`) | `-4 * SL` for the ~4-scanline CA1 service latency; the sub-scanline part centres fires 2 and 3 in blanking (writes at cycles ~93-99 of 128, 29 cycles of margin, against 116-124 before) |
| Edge Grinder (two cycles, MODE 2) | `T1_I1` | `56*SL - 4*SL - 2` | VSync handler to fire 1 = 6,802 cycles = 53.1 scanlines |
| Edge Grinder | `T1_I2` | `40*SL - 2` | fire 1 to fire 2 = 5,122 cycles = 40.0 scanlines |

Measured: Paradroid Layer 3 and 2026-09-06 (jsbeeb, breakpoint bisection and the `T1_PROBE`
screenshot method); Edge 2026-09-02 (jsbeeb, breakpoints on the two handlers and
`elapsed_cycles`). **Take the phase from the emulator, not from the arithmetic**: the phase is a
property of the whole IRQ path and drifted ~6 us later than the calibration as the handler changed.
[Paradroid layer-3-scroll.md](https://github.com/kieranhj/paradroid-beeb/blob/main/docs/layer-3-scroll.md),
[Paradroid raster-timing.md](https://github.com/kieranhj/paradroid-beeb/blob/main/docs/raster-timing.md),
[Edge layer-2-display.md](https://github.com/kieranhj/edge-beeb/blob/master/docs/layer-2-display.md)

- **Erring late on the top edge is harmless; erring early shows content from the bottom of the
  window at the top.** Bias late if in doubt.
  Measured: Layer 3, jsbeeb and b-em. [Paradroid layer-3-scroll.md](https://github.com/kieranhj/paradroid-beeb/blob/main/docs/layer-3-scroll.md)
- **VSync quantises a step to whole frames**: a redraw a few thousand cycles over the line costs a
  whole extra frame, so a small optimisation can move nothing and the next one everything.
  Measured: Layer 3, jsbeeb (vertical scroll 4 -> 5 -> 10 steps in 10 frames). [Paradroid layer-3-scroll.md](https://github.com/kieranhj/paradroid-beeb/blob/main/docs/layer-3-scroll.md)
- **A phase maximum includes any interrupt that landed inside it.** With six interrupts a frame, a
  644-cycle phase showed a 3,632-cycle maximum. Take worst cases from maxima and typical costs from a
  single-frame sample.
  Measured: 2026-09-04, jsbeeb. [Edge performance.md](https://github.com/kieranhj/edge-beeb/blob/master/docs/performance.md)

---

## 9. ZX0 / ZX02 compression

- **ZX02 is the one to use on a 6502, and it is not close.** Daniel Serpell's 6502-tuned fork of
  ZX0: the depacker is 131 bytes against ZX0's 257 and decodes at 53.9 cycles per output byte
  against 115.4 - 2.14x - for +0.11% on the packed size. Per file the ratio loss is under 1%
  except on data that is almost all one repeated run (ZX02's gamma codes are capped at 8 bits),
  where a near-empty 2,560-byte panel went 67 -> 79 bytes. Both upstream READMEs claim ZX02 wins
  on ratio as well; over this corpus it does not, it loses slightly.
  Measured: 2026-09-07, both depackers stepped in py65 over 43 real data files from both ports
  (242,481 bytes), each decode compared with the source file byte for byte; end to end by booting
  the kit template's ZX02 disc in jsbeeb (B-DFS1.2 and Master) and reading `&4A00` back.
  [lib/zx02depack.asm](../lib/zx02depack.asm) [dmsc/zx02](https://github.com/dmsc/zx02)
- **Both formats unpack forwards; a stream may share memory with its output only while the reader stays
  ahead of the writer.** The rule of thumb "the stream must end where the output ends" is not enough:
  the required gap is a property of THIS stream, because a literal run copies 1:1 plus flag bits and
  the writer can gain locally. Walk the decode and track `max(write_index - bytes_consumed)`; for
  Paradroid's font that was 1,566 with the worst point at the very end (ZX0's closing matches consume
  almost no input). Check it every build.
  Measured: 2026-08-29, `make_disc.py`'s `in_place_delta()`, verified by boot in jsbeeb. [Paradroid loader-compression.md](https://github.com/kieranhj/paradroid-beeb/blob/main/docs/loader-compression.md)
- **A full 20K screen cannot be unpacked in place from inside the screen**: the stream's tail would
  run past `&8000`. Stage it below the screen, and split it if the staging area is small.
  Established: 2026-09-04 (Edge) and 2026-08-30 (Paradroid intro), jsbeeb. [Edge layer-9-loader.md](https://github.com/kieranhj/edge-beeb/blob/master/docs/layer-9-loader.md) [Paradroid intro.md](https://github.com/kieranhj/paradroid-beeb/blob/main/docs/intro.md)
- **Already-compressed data does not compress again.** A bank whose deck maps and character
  bitmaps were already ZX0 streams packed to 63.9%; four compiled sprite shifts of the same data
  packed to 18.5%.
  Measured: 2026-08-21. [Paradroid loader-compression.md](https://github.com/kieranhj/paradroid-beeb/blob/main/docs/loader-compression.md)
- **Compression roughly pays for a loading picture and no more** on a Master with a 1770 DFS:
  reading 37,632 bytes instead of 91,904 saved about 9 s of disc and unpacking 74,752 bytes plus
  drawing 20K cost almost all of it back (11.1 s -> 10.9 s).
  Measured: 2026-09-04, jsbeeb, `*RUN` to `install_irq`. [Edge layer-9-loader.md](https://github.com/kieranhj/edge-beeb/blob/master/docs/layer-9-loader.md)
- **A size-optimised depacker costs about 40k cycles per 1K** on deck maps, rising on less
  compressible data.
  Measured: 2026-08-21, jsbeeb. [Paradroid loader-compression.md](https://github.com/kieranhj/paradroid-beeb/blob/main/docs/loader-compression.md)
  (The 2026-09-07 py65 figures above are higher - 118k per 1K for the same ZX0 depacker - because
  they count every cycle of the decode alone, not a load's wall clock. Compare them with each
  other, not across the two methods.)

---

## 10. beebasm (1.11) gotchas

*The kit's template assembles with Baron now, and four of these do not apply to it -
`docs/toolchain-baron.md` says which and what replaced them. They stay here because the two
shipping ports are beebasm projects, and `lib/` is still beebasm syntax.*

- **No `IFDEF`, and a symbol defined twice is an error**, so a source file cannot carry a default
  for a command-line symbol: every invocation must pass `-D RELEASE=0` (and every other such flag)
  or assembly stops with *Symbol not defined*. A build that needs one optional flag therefore needs
  every bare invocation to pass it, which is why Paradroid's `!BOOT` wiring became a post-processor
  patch instead.
  Established: 2026-08-26 and 2026-08-29. [Paradroid CLAUDE.md](https://github.com/kieranhj/paradroid-beeb/blob/main/CLAUDE.md) [Paradroid intro.md](https://github.com/kieranhj/paradroid-beeb/blob/main/docs/intro.md)
- **beebasm writes progress and success messages to stderr.** In PowerShell under
  `$ErrorActionPreference = 'Stop'`, redirecting that stream (`2>&1`) raises `NativeCommandError` on
  a successful build. Redirect stdout alone; check the exit code. From bash, `2>&1` is fine. [Paradroid CLAUDE.md](https://github.com/kieranhj/paradroid-beeb/blob/main/CLAUDE.md) [Edge CLAUDE.md](https://github.com/kieranhj/edge-beeb/blob/master/CLAUDE.md)
- **`SAVE` writes a loose host file whenever there is no disc image to put it in**, so a run
  without a working `-do` drops every SAVEd file in the working directory, and a `-do` path that
  cannot be written leaves a build that looks like it worked. [Paradroid CLAUDE.md](https://github.com/kieranhj/paradroid-beeb/blob/main/CLAUDE.md)
- **`CLEAR` releases beebasm's overwrite check; `GUARD` is what catches an overrun.** `CLEAR A, B`
  over the range an over-long image spills into means the overrun assembles silently and corrupts
  whatever loads there at run time. Keep a `GUARD` at the top of every image. [Paradroid CLAUDE.md](https://github.com/kieranhj/paradroid-beeb/blob/main/CLAUDE.md)
- **An undefined symbol is assembled as an absolute address in pass 1**, then errors on the size
  change in pass 2 when it turns out to be zero page. Declare zero-page slots before the code that
  uses them.
  Measured: 2026-09-04. [Edge layer-9-loader.md](https://github.com/kieranhj/edge-beeb/blob/master/docs/layer-9-loader.md)
- **beebasm will not `INCLUDE` inside a braced `{}` block.**
  [Edge CLAUDE.md](https://github.com/kieranhj/edge-beeb/blob/master/CLAUDE.md)
- **A local label inside `{}` shadows a global of the same name, silently.** `sta comp_flag` next to
  a local `.comp_flag` would have stored into code. Assembles cleanly, fails quietly. [Edge CLAUDE.md](https://github.com/kieranhj/edge-beeb/blob/master/CLAUDE.md)
- **`SKIP` emits nothing, so a listing-based gap finder cannot tell reserved storage from padding.**
  A "739 bytes of alignment holes" claim was four `SKIP`ped tables; the genuine `ALIGN` padding was
  111 bytes, and removing it freed nothing because the next `ALIGN` padded by the same amount.
  Measured: RAM pass (2026-08-25). [Paradroid layer-13-ram-pass.md](https://github.com/kieranhj/paradroid-beeb/blob/main/docs/layer-13-ram-pass.md) [Paradroid CLAUDE.md](https://github.com/kieranhj/paradroid-beeb/blob/main/CLAUDE.md)
- **Spending one byte past an `ALIGN` pad costs 256 at a stroke**; anything assembled before the
  pad rides in it for nothing. Quote a bank's pad and tail as a pair. [Paradroid CLAUDE.md](https://github.com/kieranhj/paradroid-beeb/blob/main/CLAUDE.md)
- **`INCLUDE` and `INCBIN` resolve from the working directory**, so the build must run from the
  project root (or from inside a vendored directory whose `PUTFILE` paths are relative to itself). [Edge layer-0-toolchain.md](https://github.com/kieranhj/edge-beeb/blob/master/docs/layer-0-toolchain.md) [Paradroid CLAUDE.md](https://github.com/kieranhj/paradroid-beeb/blob/main/CLAUDE.md)
- **The assembler works in one 64K image**: a file assembled at an address after another file's
  `SAVE` lands on the earlier file's bytes, so the order of the two is load-bearing. [Paradroid layer-13-compatibility.md](https://github.com/kieranhj/paradroid-beeb/blob/main/docs/layer-13-compatibility.md)
- **Constant assignments resolve in file order**, so shared constants go in the top file before the
  includes that need them. [Paradroid CLAUDE.md](https://github.com/kieranhj/paradroid-beeb/blob/main/CLAUDE.md)
- **`TIME$` stamps the assembly time**, useful in `!BOOT` so any disc image can be dated.
  [Edge CLAUDE.md](https://github.com/kieranhj/edge-beeb/blob/master/CLAUDE.md)
- **The symbol dump**: `beebasm -i src/main.asm -do build/symbols.ssd -D RELEASE=0 -d | tr ',' '\n'
  | grep "'name'"` prints every global label as `'name':decimal`, the quick way to find a variable's
  address for an emulator poke. `-do` is there only to stop the loose files. [Paradroid CLAUDE.md](https://github.com/kieranhj/paradroid-beeb/blob/main/CLAUDE.md)
- **A mechanical change can be proved mechanical** by reducing both listings to a stream of
  (mnemonic, addressing class) and comparing, or by extracting the files from both SSD catalogues
  and comparing bytes. [Paradroid CLAUDE.md](https://github.com/kieranhj/paradroid-beeb/blob/main/CLAUDE.md) [Edge layer-0-toolchain.md](https://github.com/kieranhj/edge-beeb/blob/master/docs/layer-0-toolchain.md)

---

## 11. Emulator facts

### jsbeeb (via the MCP)

- **RAM powers up zeroed.** Uninitialised state that is 0 on every emulated boot is garbage on real
  hardware and survives BREAK. It hid a white briefing and a white title in Paradroid, three times in
  two days; the test is to seed the byte before a SHIFT+BREAK autoboot, or to run something that
  writes over the area first.
  Measured: 2026-08-28 and 2026-08-30, jsbeeb. [Paradroid intro.md](https://github.com/kieranhj/paradroid-beeb/blob/main/docs/intro.md)
- **`cycles_run` is NOT the actual count when a breakpoint fires**: it returns the number
  requested. Use `elapsed_cycles` from `read_registers`; that one is exact.
  Measured: 2026-08-20. [Paradroid raster-timing.md](https://github.com/kieranhj/paradroid-beeb/blob/main/docs/raster-timing.md)
- **A run that starts with the PC already on a breakpoint returns immediately with `cycles_run` 0**
  (the next call moves on). Read, clear the breakpoint that just fired, run. Breakpoints DO fire
  under `run_for_cycles`; an older note saying otherwise was wrong.
  Measured: 2026-08-20 (Paradroid), 2026-09-02 (Edge). [Paradroid raster-timing.md](https://github.com/kieranhj/paradroid-beeb/blob/main/docs/raster-timing.md) [Edge layer-2-display.md](https://github.com/kieranhj/edge-beeb/blob/master/docs/layer-2-display.md)
- **A `run_for_cycles` snapshot can stop the CPU mid-routine**: a buffer dump caught a half-written
  strip and reported 16 differing bytes that were not a bug; an oracle redraw of >500,000 cycles was
  sampled before it finished. Idle a few frames after releasing a key; take both halves of a diff
  inside one pass with breakpoints.
  Measured: Layer 3 and 2026-08-20, jsbeeb. [Paradroid layer-3-scroll.md](https://github.com/kieranhj/paradroid-beeb/blob/main/docs/layer-3-scroll.md) [Paradroid raster-timing.md](https://github.com/kieranhj/paradroid-beeb/blob/main/docs/raster-timing.md)
- **Screenshots crop to the active display's content bounding box**, so builds are not to the same
  scale, absolute row positions move when the display start moves, and one scanline is about 2
  framebuffer pixels. Judge geometry by poked patterns, and verify against the buffer, not the
  screenshot.
  Measured: Layer 3 (Paradroid), 2026-09-02 (Edge). [Paradroid layer-3-scroll.md](https://github.com/kieranhj/paradroid-beeb/blob/main/docs/layer-3-scroll.md) [Edge layer-2-display.md](https://github.com/kieranhj/edge-beeb/blob/master/docs/layer-2-display.md)
- **`read_memory` returns whatever bank is paged at that instant.** A sample taken inside a sprite
  draw returned bank 5's empty space, which read exactly like the player having been wiped. Check
  `&F4` first. Reading shadow RAM from the CPU side likewise follows the X bit.
  Measured: Layer 7 (Paradroid combat, 2026-08), 2026-09-04 (Edge titles). [Paradroid layer-7-combat.md](https://github.com/kieranhj/paradroid-beeb/blob/main/docs/layer-7-combat.md) [Edge layer-6e-titles.md](https://github.com/kieranhj/edge-beeb/blob/master/docs/layer-6e-titles.md)
- **jsbeeb WILL boot an unpadded SSD.** An earlier note claimed it would not and blamed a hang in
  the DFS FDC poll at `&ACAE` on beebasm's image ending mid-track; KC corrected it on 2026-09-01.
  Padding to 200K (204,800 bytes) is convention and robustness, and a published size that differs
  from the last publish is a useful signal that the wrong file went out. [Paradroid CLAUDE.md](https://github.com/kieranhj/paradroid-beeb/blob/main/CLAUDE.md) [Paradroid layer-4-player.md](https://github.com/kieranhj/paradroid-beeb/blob/main/docs/layer-4-player.md)
- **jsbeeb emulates the VideoNuLA palette** (`?&FE23=&78 : ?&FE23=&88` gives mid grey; sixteen
  distinct entries come back under logical mapping). **Its NuLA scrolling and attribute modes are
  NOT emulated.** The belief that a NuLA build could not be tested in jsbeeb is what let a
  palette-mapping mistake reach real hardware.
  Measured: 2026-09-05, jsbeeb, decision 67. [Edge CLAUDE.md](https://github.com/kieranhj/edge-beeb/blob/master/CLAUDE.md) [Edge layer-8b-nula.md](https://github.com/kieranhj/edge-beeb/blob/master/docs/layer-8b-nula.md)
- **jsbeeb needs VSync for the 8271 poll**: with R7 parked so VSync never fires, `*LOAD` hangs at
  `&ACAE` (section 6). It reproduces from BASIC, so it is not the game.
  Measured: Layer 3, jsbeeb. [Paradroid bug-map-corruption.md](https://github.com/kieranhj/paradroid-beeb/blob/main/docs/bug-map-corruption.md)
- **`frame_count` counts the CRTC's own frames, not 50 Hz ones**, which is why it climbs 14 in
  258k cycles when the CRTC is left free-running in a short shape.
  Measured: 2026-08-31. [Paradroid raster-timing.md](https://github.com/kieranhj/paradroid-beeb/blob/main/docs/raster-timing.md)
- **jsbeeb's `B-DFS1.2` model has eight sideways RAM banks**; a Master model has 4-7.
  Measured: 2026-08-29. [Paradroid layer-13-compatibility.md](https://github.com/kieranhj/paradroid-beeb/blob/main/docs/layer-13-compatibility.md)
- **`read_sound_state` and the SN76489 write capture are the instrument for sound**: CH0 tone 284 =
  440.1 Hz confirmed the 4 MHz chip clock and `N = 125000 / f`; a 246-cycle window between a volume
  write and a silence write showed up as a 50 Hz crackle in the capture before it was heard.
  Measured: 2026-08-21 (Paradroid), 2026-09-04 (Edge; the crackle was also heard on b2 by KC). [Paradroid layer-11e-sound.md](https://github.com/kieranhj/paradroid-beeb/blob/main/docs/layer-11e-sound.md) [Edge layer-7-music.md](https://github.com/kieranhj/edge-beeb/blob/master/docs/layer-7-music.md)
- The MCP timed out on its first connection in one session and was fine after `/mcp` reconnect.
  [Edge layer-0-toolchain.md](https://github.com/kieranhj/edge-beeb/blob/master/docs/layer-0-toolchain.md)

### b-em, b2 and beebjit

**b-em is no longer used (KC, 2026-09-07); the second opinion is b2 or beebjit.** The b-em
observations below are kept as history. To boot a disc: beebjit `beebjit -0 game.ssd -autoboot`
(add `-master` for a Master 128, `-swram 4` per sideways RAM bank), b2 `b2 -0 game.ssd -b`
(`-c CONFIG` picks a saved machine configuration). Both from the tools' own help text, 2026-09-07.

- **b-em shows garbage on alternate frames for a displayed area below `&3000` with the shadow D bit
  set; jsbeeb displays it.** Real hardware untested.
  Measured: 2026-09-02, b-em (KC) and jsbeeb. [Edge layer-2-display.md](https://github.com/kieranhj/edge-beeb/blob/master/docs/layer-2-display.md)
- **b2 shows a misplaced (right-length, wrong-phase) field that jsbeeb does not**; it is the
  instrument for TV resync questions.
  Measured: 2026-08-31, b2 photograph. [Paradroid raster-timing.md](https://github.com/kieranhj/paradroid-beeb/blob/main/docs/raster-timing.md)
- **b-em caught a two-scanline top-edge error that jsbeeb screenshots could not resolve.**
  Measured: Layer 3, b-em (KC). [Paradroid layer-3-scroll.md](https://github.com/kieranhj/paradroid-beeb/blob/main/docs/layer-3-scroll.md)
- **b-em has not seen the Master mid-frame bank switch or the titles' four-cycle rupture**;
  decision 17 is why that matters. [Edge layer-6e-titles.md](https://github.com/kieranhj/edge-beeb/blob/master/docs/layer-6e-titles.md)
- **Only b2's debug build carries an HTTP API** (`peek` for buffer diffs, paste, loading a disc),
  documented in `doc/Debug-version.md` in the b2 tree
  (<https://github.com/tom-seddon/b2/blob/master/doc/Debug-version.md>). Paradroid's NuLA plan
  notes that reading the endpoints out of the binary got the port wrong and missed half of them:
  read the document first. [Paradroid nula-plan.md](https://github.com/kieranhj/paradroid-beeb/blob/main/docs/nula-plan.md)
- **b-em is launched as a Master with `-m3`.**
  [Edge layer-0-toolchain.md](https://github.com/kieranhj/edge-beeb/blob/master/docs/layer-0-toolchain.md)

---

## 12. Things stated in the ports but not measured

Kept separate so they are not mistaken for the rest:

- What the MOS masks for inside `OSBYTE &81` was never measured, so "direct keyboard reads
  interrupt less than the OS did" is not a claim either port makes. [Paradroid raster-timing.md](https://github.com/kieranhj/paradroid-beeb/blob/main/docs/raster-timing.md)
- The SN76489's periodic-noise register path was taken on trust from the verified white-noise
  encoding. [Paradroid layer-11e-sound.md](https://github.com/kieranhj/paradroid-beeb/blob/main/docs/layer-11e-sound.md)
- The reverse transition out of a rupture (`UninstallIrq` then a plain frame) costs at most one
  field, unmeasured beyond the one 376-line field recorded. [Paradroid raster-timing.md](https://github.com/kieranhj/paradroid-beeb/blob/main/docs/raster-timing.md)
- The Master mid-frame bank switch, the wrap-inside-bank behaviour and the "nothing displayed below
  `&3000`" rule are emulator results (jsbeeb; b-em for the last) with no real-hardware confirmation. [Edge CLAUDE.md](https://github.com/kieranhj/edge-beeb/blob/master/CLAUDE.md)
- DFS sector timings are jsbeeb's disc model and were flagged as such before any faster reader was
  costed. [Paradroid loader-compression.md](https://github.com/kieranhj/paradroid-beeb/blob/main/docs/loader-compression.md)
- The keyboard phantom on real hardware was reported, not instrumented, and the redefined-controls
  case remains open. [Paradroid human-notes-status.md](https://github.com/kieranhj/paradroid-beeb/blob/main/docs/human-notes-status.md)
