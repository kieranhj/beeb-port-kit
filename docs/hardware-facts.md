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

A few entries carry a third source: **1942** (BBC Master 128, September 2026), the first port built
*with* this kit rather than distilled into it. It is unpublished, so those entries name the layer
and the measurement rather than a link, and they say when the kit re-ran the check itself.

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
- **The specific worst case: a fire that lands in the adjust's own last scanline.** In the
  two-cycle scroll frame below, whose cycles carry `line` and `8 - line`, the first timer fire
  after VSync is placed at the first visible line - and at `line` = 0 that is the blanking of the
  *preceding* adjust's last scanline, precisely where an R5 write must not go. Rich
  Talbot-Watkins's demo writes the scrolling cycle's R5 in that fire and gets away with it by
  instruction ordering (R8, then the timer, then R4, then R5); 1942 writes it in the middle of the
  cycle instead, which is what the rule above already says, and that write is the whole reason its
  frame has a second timer fire at all.
  Measured: 1942 Layer 2b, 2026-09-08, jsbeeb 1.25.0, Master; Rich's ordering read off the
  detokenised listing of his demo (lines 510-580).
- **Timer fires that must land in a cycle should overshoot the boundary by a few rows.** Sized to
  reach the boundary exactly, IRQ latency alone carried them into the previous cycle.
  Measured: Layer 3, jsbeeb, with a `DEBUG_RASTER` tint at each interrupt entry. [Paradroid layer-3-scroll.md](https://github.com/kieranhj/paradroid-beeb/blob/main/docs/layer-3-scroll.md)

### The vertical total adjust displays, and where that puts the scrolling area

The adjust (R5) is how a rupture scrolls vertically by single scanlines: two cycles whose adjusts
sum to 8 keep the field at 312 lines while the boundary between them slides. These are the facts
that decide what the technique costs. The primary source is Rich Talbot-Watkins's own write-up,
*Line by line vertical scrolling on the Beeb* (`BEEB\Notes\Vertical Rupture.txt`) and his working
demo `smoothscroll.ssd` (`$.TEST25`, tokenised BASIC; detokenise it and read the register writes -
the comments in the listing are the specification).

- **`R6 = displayed rows + 1`, because the vertical total adjust counts as one more character row
  for the R6 compare.** Set R6 one higher than the cycle's row count and display enable survives
  into the adjust, and the CRTC fetches the *next* buffer row's top `line` scanlines - which is
  exactly the bottom sliver a 1-scanline scroll needs. Rich's demo sets `R6 = 24 + 1` for a 24-row
  window and his write-up says why ("total screen rows + 1 to account for the fractional row which
  comes from R5").
  Measured: 1942 Layer 2b, 2026-09-08, jsbeeb 1.25.0, Master, by a buffer oracle that scores the
  adjust's own scanlines separately against an independent model of what the CRTC must fetch:
  **0 wrong of 14,784 pixels fetched by the adjust**, at all eight values of `line`. Re-run here
  the same day, same result. The field stays 312 lines with it: 3,993,600 cycles over 100 fields =
  39,936.00 each. Rich's demo was booted here too (jsbeeb 1.25.0, Model B): it runs, and its own
  field measures 39,936.0 cycles over 50 fields.
  Measured again on a **Model B**, 2026-09-08, jsbeeb 1.25.0, by the kit's own worked example
  (`template/examples/vscroll`, and `template/docs/vertical-scroll.md` for the numbers): a 15-row
  play cycle with `R6 = 16`, **0 of 38,400 pixels wrong at all eight values of `line`, 0 wrong of
  19,840 pixels fetched by the adjust**, one unbroken lit run of 152 scanlines, 39,936.00 cycles a
  field.
- **Put the scrolling area FIRST in the frame.** The pair of adjusts is `line` on the scrolling
  cycle and `8 - line` on the other. With a static panel *above* the scrolling area the
  `8 - line` lands *between* them, where it is visible and has to be blanked: a gap of up to 8
  scanlines. Put the scrolling area first and the same adjust falls at the end of the panel cycle,
  which is **top border**, where there is nothing to see - and the first visible line then sits at
  a *fixed* distance from the VSync edge whatever `line` is, because the `8 - line` of border and
  the `line` scanlines blanked at the top of the scrolling cycle always sum to 8. Nothing slides,
  and there is no gap.
  Measured: 1942 Layer 2b, 2026-09-08, jsbeeb 1.25.0, Master - the port built both shapes. Rich's
  shape: 2 CRTC cycles, 3 T1 fires, 272 lit lines in a 272-line span with no gaps, 40 lines of
  blanking. The Paradroid-shaped first cut of the same port: 3 cycles, 6 fires, a 296-line span
  with two visible 8-line gaps, 16 lines of blanking.
- **Only ONE R8 edge in such a frame has to land on an exact scanline** - the unblank at the first
  visible line. The panel-first shape needed four, because each of its two gaps has two edges.
  Measured: 1942 Layer 2b, 2026-09-08, by counting the scanline-exact writes in the two builds.
- **Paradroid deliberately refused to depend on the displayed adjust, and it cost a row of play
  area.** Its layer-3 write-up: *"18 cycle rows rather than 17 is deliberate. It makes row 16
  non-displayed, so display-enable turns off by ordinary means and we never depend on the murky
  "R6 > R4" behaviour where the VADJ scanlines themselves are displayed."* That is a true record of
  that port and it is still true of it. Two other constraints stand behind it: Paradroid's 10K wrap
  makes its strip exactly 16 rows, so there was no spare row for the sliver to come out of (see the
  display window rules below), and its panel is above the play area, which is what forces three
  cycles - *"two cycles would leave the variable adjust between VSync and the panel, sliding the
  panel up to 7 scanlines"*. **Neither cost is intrinsic to the technique**; both follow from that
  port's frame shape.
  Source: [Paradroid layer-3-scroll.md](https://github.com/kieranhj/paradroid-beeb/blob/main/docs/layer-3-scroll.md).
- **What Rich's shape assumes, and what has not been measured.** It assumes the scrolling area can
  come first - a port whose panel must sit at the top of the tube cannot have it - and it assumes
  `R6 > rows` displays the adjust on the CRTC you are running on. That second one is measured on a
  Master and on a Model B, but **in jsbeeb 1.25.0 only**: not on b2, not on beebjit, and not on
  real hardware. Rich's demo is a Model B program that relies on it and runs, which is evidence
  about the 6845 but not a measurement of the sliver. Cross-check it on your own target before you
  spend the row it saves (procedure 11 in [verification.md](verification.md)).

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
  ceiling **in Paradroid**, and 1-scanline vertical scrolling cost it one row of play area: with no
  spare row, the sliver had to come out of the visible 16. That is the wrap's cost, not the scroll
  technique's - a strip with a spare row takes the sliver out of the displayed adjust instead and
  pays nothing (see the vertical total adjust above).
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
- **The MOS uses three of ANDY's sixteen pages, each only when one particular thing happens.**
  Whether a port can use all 4K depends on whether its game ever does those things once ANDY is
  filled. The page map:

  | Page | Written by | Free for a game that... |
  |---|---|---|
  | `&80` | the soft-key buffer: `*KEY 1 HELLO` put "HELLO" at `&8022` | never issues `*KEY` after filling it |
  | `&81`-`&87` | nothing tried (1,792 bytes) | always |
  | `&88` | **`&8800`-`&882F` on every mode change and every soft BREAK**: 48 bytes of MODE 1's colour patterns and pixel masks. `&8830`-`&88FF` untouched | fills ANDY after its last mode change and reloads after a BREAK |
  | `&89`-`&8E` | nothing tried (1,536 bytes) | always |
  | `&8F` | user-defined characters: `VDU 23,224,...` wrote 8 bytes | never defines a character after filling it |

  **None of these wrote to ANDY:** 26 OSFILE loads (every file on a disc, twice), `*CAT`, the
  MOS sound for a second (`SOUND 1,-15,100,20`), PRINT, and half a second idle.
  **So all 4K is usable** by a game that fills ANDY after its one mode change, never calls
  `*KEY` or `VDU 23` afterwards, and reloads from disc after a BREAK. The kit template qualifies
  (one `VDU 22`, before `install_irq`; nothing through the MOS's VDU afterwards). 1942 loads its
  text code at `&8000` on that basis. A game that changes mode during play, or keeps the MOS's
  VDU driver running for text, has `&81`-`&87` and `&89`-`&8E`: 3,328 bytes. It can use page
  `&88` from `&8830`, and `&8F` if it never defines characters.
  **Not measured, and each could move the map**: real hardware; MOS 3.5; ADFS and MMFS; any
  user-defined character other than 224; the soft-key buffer's full length. **Two traps in the
  measurement**: a fill over page `&80` corrupts the key buffer, so a later `*KEY` fails with "Bad
  key" (test keys on a fresh machine first). jsbeeb's `run_until_prompt` also stops at BASIC's
  `INKEY` (use `run_frames` for a timed wait). The routines and the BASIC that drove them are in
  1942's `docs/andy.md`, ready to retype on a real machine.
  Measured: 2026-09-11, jsbeeb Master 128 (MOS 3.20, 1770 DFS), from machine code in main RAM
  paging ANDY as `unpack_andy` does, a fill and a check around each event. [1942-beeb docs/andy.md](https://github.com/kieranhj/1942-beeb/blob/main/docs/andy.md)
- **Code that reads ANDY lives in main RAM**: with ANDY paged, the first 4K of the paged sideways
  bank is hidden. The kit's IRQ never touches ROMSEL, so it can't unpage ANDY under a running
  routine. An IRQ that pages anything has to save and restore ROMSEL, ANDY bit included.
  Established: 2026-09-11, 1942 port. [1942-beeb docs/andy.md](https://github.com/kieranhj/1942-beeb/blob/main/docs/andy.md)

### HAZEL

- **HAZEL (`&C000-&DFFF`, ACCCON bit 3, Y) is the filing system's workspace.** Take it and BREAK
  must clear memory: a soft BREAK out of the game gave `Acorn MOS` with no DFS banner and `*CAT`
  returned nothing. `OSBYTE 200, X=3` at the top of the program makes BREAK a power-on reset (bit 1)
  and disables ESCAPE (bit 0); afterwards BREAK gave a clean `Acorn 1770 DFS` and SHIFT+BREAK
  reloaded the game. Load HAZEL's contents LAST and touch the disc no more. This is Edge
  unpacking over all 8K from `&C000`, DFS's own pages included; the window below is different.
  Measured: 2026-09-04, jsbeeb, before and after. [Edge layer-7-music.md](https://github.com/kieranhj/edge-beeb/blob/master/docs/layer-7-music.md)
- **`&C300-&DEFF` is usable with DFS still working (pop-beeb's range), but how much of it depends
  on what the program still asks of the filing system.** Every byte of the window was filled
  with `page EOR offset` from main-RAM code (SEI, ACCCON Y on, copy down, Y off), then checked
  after each kind of call:

  | after | written inside `&C300-&DEFF` |
  |---|---|
  | OSFILE load (A = `&FF`), 8 KB file, 4 times | nothing |
  | OSFILE save (A = 0) and delete (A = 6) | nothing |
  | any `*` command (OSCLI) | `&DC00` up: the command line (4 bytes for `CAT`, 20 for `SAVE TMP 3000 +800`) |
  | `OPENIN` + `BGET` | 32 bytes of `&C3` per open channel, plus one whole page per channel from `&C400` up: five channels took 159 bytes of `&C3` and all of `&C400-&C8FF` |
  | soft BREAK | 10 bytes of `&C3`, 237 of `&DA` |

  DFS worked throughout with the whole window overwritten, including `&D900-&DBFF`, which hold
  DFS data at rest after boot (`&DB00` looks like a ROM-paging stub): two full loads, `BGET`,
  save, delete, `*CAT`, and a soft BREAK that came back with the `Acorn 1770 DFS` banner and a
  working `*CAT`. `&C000-&C2FF` and `&DF00-&DFFF` hold DFS data at rest and change during calls;
  they were never overwritten and are not usable.
  Choosing the window by what runs after HAZEL is loaded:
  - **OSFILE loads, saves and deletes only**: all of `&C300-&DEFF`, 7K.
  - **plus `*` commands**: lose `&DC`.
  - **plus open files** (`OPENIN`, `BGET`, and presumably OSGBPB and `OPENOUT`, not tested): lose
    `&C3` and a page per channel from `&C4`.
  - **data that must survive a soft BREAK**: lose `&C3` and `&DA`.
  1942-beeb uses `&C400-&D9FF`, which clears everything except open channels; it never opens one.
  Measured: 2026-09-11, jsbeeb-mcp 3.4.0 / jsbeeb 1.25.0, Master 128 (MOS 3.20, Acorn 1770 DFS),
  MODE 7. The OSFILE-load, `*CAT` and soft-BREAK figures match 1942-beeb's independent run the
  same day byte for byte (1942-beeb `docs/hazel.md`, 20 OSFILE loads over its own disc). Channels,
  saves and deletes are this run's alone.
  **Not covered, and each could move the map:** real hardware; **MOS 3.5** - pop-beeb 1.2 moved off
  `&DA` for "DFS versions in MOS 3.5+" and pokes `&DAD3`/`&DAD4` to keep DFS 2.45 believing it is
  active (`disc/readme.txt`, `pop-beeb.asm`); **MMFS** - pop-beeb guards `&DAC0` because "Can't use
  page `&DBxx` with MMFS FFS"; ADFS; writes through open channels. [pop-beeb](https://github.com/kieranhj/pop-beeb)
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

### Target configurations (paradroid-beeb issue #18)

The template's boot, before and after four defaults: the host's addresses, OSBYTE 114,1, every
CRTC register, and `claim_nmi` (joined 2026-09-13 by `release_fs`, OSBYTE 140, which the
results below predate). Each result is a fresh jsbeeb machine, SHIFT+BREAK, then 400
frames. It **plays** when the panel and strip are drawn, `frame_count`/`field_count` are
advancing and `&0D00` reads `&40`.

| Machine | Before | After |
|---|---|---|
| B, DFS 1.20 | plays | plays: `field_count` +50 and `frame_count` +25 over 50 frames, `&0D00` = `&40` |
| B + 65C02 second processor | **black**. MODE 7 never left: `Game` loaded into the parasite | plays |
| Master + 65C102 second processor | **black**, the same | plays |
| Master after `*SHADOW` and a soft BREAK | **wrong picture**: a blue strip, no panel; ACCCON `&1B` (D and E set, the display in shadow) | plays; ACCCON `&18` |
| Master after `*CONFIGURE TV 252,0` and a hard reset | plays | plays. **This test can't tell before from after**: the template already rewrote R7 and R8, which are what `*TV` moves |

- **The second processor needs the host bits in TWO places.** The catalogue (`dfs.to_host`) is
  not enough on its own when the loader passes its own address. With only the catalogue fixed,
  both Tube machines reached MODE 1 and then hung in the first load. The B was at `&0701`
  inside the Tube host code with S = `&0B`, just after writes to `&FE4B`-`&FE4E`. The Master
  was at the MOS IRQ entry. `&0D00` still held DFS's code. `load_stream`'s OSFILE block
  carried `&0000xxxx`, a parasite address. `&FF` in its bytes 2 and 3 fixed both machines.
  Edge's loader has the same block, so a Master + 65C102 would presumably break it too. That
  is inferred, not measured.
- **OSBYTE 114 is safe to call on a Model B**: its OS 1.20 passes the unknown OSBYTE to the ROMs
  and nothing claims it. It is `*FX 114` that says "Bad command", not the call (hexwab, #18).
  The plain B plays with it in the boot.
- **A `*RUN` boot (disc option 2) is entered with interrupts OFF, before any language starts.**
  A breakpoint on the template's release `!BOOT` stub at `&0900` read P = `&35` (I set) on
  `B-DFS1.2` and `Master` alike, with only the machine and DFS banners on screen. The stub still
  prints (OSASCI) and `*RUN`s the game (the DFS loads with interrupts masked). But on the **Model
  B the BREAK beep never ended**: after 400 frames channel 0 still sounded, 523 Hz at attenuation
  2. The debug build's `*EXEC` boot, which starts BASIC with interrupts on, left every channel at
  15. The Master was silent either way. The fix is `install_irq` writing attenuation 15 to all
  four channels (Edge's `sn_write` sequence); afterwards the release B read 15 on channel 0 and
  played. Measured: 2026-09-11, jsbeeb.
- **OSBYTE 126 would not have stopped that beep: at a `*RUN` boot no ESCAPE is pending.** At
  the stub's first instruction, `&FF` (the ESCAPE flag) read `&00` and `&0276` (ESCAPE effects)
  read `&00` on `B-DFS1.2` and `Master` alike. On the B, channel 0 was already sounding at 523
  Hz, attenuation 2; on the Master every channel was already silent. In OS 1.20, OSBYTE 126 at
  `&E65C` does nothing without an ESCAPE: `BIT &FF : BPL` returns X=0. Only when one is pending,
  and `&0276` is 0, does it `CLI`, close EXEC files and purge every buffer. Purging a sound buffer
  goes `&E1AD` → `&ECA2`, whose first act is `JSR &EB03`, "silence the channel". So it silences
  sound only as a side effect of an ESCAPE. The llm-beeb-wiki's `os/escape.md` agrees ("Stops
  any sound currently playing", among the ESCAPE effects), and notes that `OSBYTE &E6, X=&FF`
  turns those effects off. **Write the chip instead**, as `install_irq` now does: it doesn't
  depend on the ESCAPE state or the effects setting. hexwab (paradroid-beeb #18) recommended
  OSBYTE 126 for the boot beep; on this evidence it does nothing at this point in the boot.
  Measured: 2026-09-11, jsbeeb, breakpoint at `&0900` on the template's release image. Code read
  from `bbc-documents/B/os/os.txt` (OS 1.20). MOS 3.20 not disassembled.
- **Not measured here**: a real second processor, a real `*SHADOW` machine, B+, other DFSs,
  softloaded filing systems (Paradroid's ZMMFS handling), a real machine's BREAK beep under a
  `*RUN` boot.
  Measured: 2026-09-11, jsbeeb (`B-DFS1.2`, `Master`, both with `tube`), the kit template. [paradroid-beeb #18](https://github.com/kieranhj/paradroid-beeb/issues/18)

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
- **ROMSEL (`&FE30`) is WRITE-ONLY on a Model B: read ROMSHAD (`&F4`) instead.** A test that read
  `&FE30` back to see which bank was paged got `&FE` on jsbeeb's `B-DFS1.2` and the right answer
  (4) on its Master, which has a readable copy. The MOS keeps its own copy in ROMSHAD on both, and
  that is the byte an IRQ handler saves and restores anyway.
  Measured: 2026-09-11, jsbeeb, `lib/test/run_test.6502` after `load_bank`.
- **Take the four highest-numbered RAM banks**: the banks that matter to other people sit low, and
  on a machine with exactly 4-7 the answer is unchanged.
  Decided: 2026-08-29 (KC). [Paradroid layer-13-compatibility.md](https://github.com/kieranhj/paradroid-beeb/blob/main/docs/layer-13-compatibility.md)
- **A ROM image in sideways RAM can be the fourth bank, if the game fills it last.** ZMMFS copies
  MMFS into the highest free RAM bank and marks it in `&02A1`, so a B with four banks and ZMMFS
  has three clean ones. With exactly three, `swram_probe.6502` takes the highest marked bank that
  passes MMFS's own RAM test (flip `&8006`, read it back, flip it back). The game then owes two
  things: fill that bank after its last filing-system call, and zero its `&02A1` byte first.
  Built by Paradroid 2026-09-10 (issue #18 item 9).
- **The kit's probe, on `lib/test/probe_test.6502`**, a fresh jsbeeb machine for each:

  | Machine | Printed | Handover at `&0A00` |
  |---|---|---|
  | `B-DFS1.2` | `Sideways RAM found: 7 6 5 4 3 2 1 0` / `Using banks: 4 5 6 7` | `A5 04 05 06 07` |
  | `Master` | `found: 7 6 5 4` / `Using banks: 4 5 6 7` | `A5 04 05 06 07` |
  | `Master`, bank 7 marked as a ROM image | `found: 7 6 5 4` / `Using banks: 4 5 6 7` / `(The last holds a ROM image, which will be overwritten)` | `A5 04 05 06 07`; bank 7's `&8006` put back as it was (`&82`); its `&02A8` byte still `&82`, because zeroing it is the game's job |
  | `Master`, banks 6 and 7 marked | `found: 5 4` / `...found 2` / `(Set LK18 and LK19 west?)` | untouched (`00`), so no magic byte |

  **A test ROM image needs a service entry that returns.** Marking a `&02A1` byte makes the MOS
  call that bank's `&8003` with every service call. A bank of zeros BRKs there, the BRK is
  offered to the same bank as service call 6, and the machine loops at `&8003` before the
  probe runs. `60` (RTS) at `&8003` and a type byte at `&8006` are enough; Paradroid planted a
  full header. **A load from jsbeeb's 1770 DFS takes more than 50 frames**: a `*RUN` still in
  DFS's NMI code at `&0D3F` is loading, not hung.
  Measured: 2026-09-11, jsbeeb. The Solidisk refusal and a real ZMMFS machine are not tested.
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

**READ THIS BEFORE THE TABLE (hexwab, paradroid-beeb #18, 2026-09-13).** Most of the table below
is workspace the filing system still owns, and there are **two ways to take it, for two different
jobs**:

- **A loader**, which still has to load, cannot shut the filing system down. It borrows the
  workspace and must **own the machine** while it does: claim the NMI (`OSBYTE 143,12,255`, `RTI`
  at `&0D00`) and let **no OS code run at all** - no OS call, no MOS interrupt handler. Regaining
  control is the only way the filing system could discover the theft, and the NMI is the route it
  keeps.
- **A game that has finished loading** calls **`OSBYTE 140`** - what `*TAPE` ends up calling,
  without the OSCLI in the middle - while the workspace is **still intact**. The filing system
  detaches every hook it holds and tells whatever hardware it was driving to stop raising NMIs.
  Only then is the workspace yours, `&B0-&CF` in the zero page included, and only then is an OS
  call safe afterwards. The price: **nothing may load again**.

A filing system is *entitled* to hook `OSBYTE`, `OSWORD` and the vectors and to find its workspace
intact when one of them is called. Acorn's DFS hooks none of them, which is the only reason a game
that skips `OSBYTE 140` appears to work - see the Opus DDOS entry below. `lib/loader.6502` has the
contract in full; `release_fs` and `claim_nmi` are the two calls.

| Range | What it is | Yours when | Trap |
|---|---|---|---|
| `&00A8-&00AF` | the MOS's own zero-page scratch | after `OSBYTE 140` | not the filing system's, so 140 is not the whole story: an OS call may use it |
| `&00B0-&00CF` | the FILING SYSTEM's zero page | after `OSBYTE 140`, and not before | Paradroid used it without the call and ran only because Acorn's DFS did not mind |
| `&0100-&017F` | bottom half of the stack page | measured untouched through play, deck load, console and game over including `*LOAD`s | not loadable from disc; paths not exercised invalidate the measurement |
| `&0400-&07FF` | language workspace | after `*RUN` (Edge, verified by sentinel) | Paradroid's briefing lives here; the ceiling is `&0800` |
| `&0800-&08FF` | MOS sound: `&800-&83F` workspace, `&840-&87F` channel queues, `&8C0-&8FF` envelopes | only while you own IRQ1V | see below |
| `&0800-&0BFF` | sound, serial, soft keys | once the MOS interrupt is gone (Edge, sentinel) | |
| `&0A00` | printer buffer | survives BASIC exec, DFS loads, `VDU 22` | inside pdloader's tables |
| `&0C00-&0CFF` | user-defined characters | once the MOS is not printing | |
| `&0D00-&0D5F` | NMI routine (DFS) | never while the disc is in use | |
| `&0D9F+` | extended vector table: the route ANY sideways ROM takes when it claims a vector, filing system or not | never safely, if you make OS calls afterwards | `OSBYTE 140` does NOT make it yours - it is the MOS's, not the filing system's. Paradroid buries it and is still carrying the question (#18, open) |
| `&0DF0-&0DFF` | ROM private workspace | excluded | |
| `&0E00-&10FF` | DFS shared workspace | after `OSBYTE 140`, or while you own the machine | nothing may be LOADED there. **And it need not end where DFS's does**: OSHWM is the only thing that says where this machine's filing system stops |
| `&1100-&18FF` | DFS random-access buffers, untouched by `*LOAD`/OSFILE | immediately - Paradroid RUNS here; worth 2K below `PAGE = &1900` | **`*EXEC` writes here** and so does closing an exec file, so a game living here must boot by `*RUN`. Acorn-DFS-specific either way: put code as high as you can afford |

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
- **DFS does not need the MOS to service interrupts, and does not need interrupts at all.** An
  8 KB, 32-sector `*LOAD` completed byte-for-byte in three configurations: IRQ1V pointed at a
  handler that only clears both VIAs' flags and returns (`TIME` unmoved, 232 interrupts through the
  null handler); interrupts masked with `SEI` across the whole call (a counter in the handler proved
  none was taken); and both of those with VSync stopped as well. The 8271 transfers on NMI, which
  none of that touches. This **replaces** the older claim that taking IRQ1V stops the MOS servicing
  the filing system, which was assumed from the fact that both ports load before the takeover and
  was never tested.
  Measured: 2026-09-09, jsbeeb-mcp 3.4.0 / jsbeeb 1.25.0, `B-DFS1.2`, MODE 7, purpose-built
  one-file disc. Load before the takeover anyway, for the reasons that do hold: DFS pages its ROM
  over `&8000`, its workspace is live until the last call returns, and loads cost whole frames.
- **The MOS's disc code needs VSync - not reproducible on current jsbeeb.** The original: with the
  CRTC's R7 parked where VSync never fires, the second `*LOAD` hung forever in DFS's 8271 status
  poll at `&ACAE`, and bisecting the CRTC writes one at a time showed R7 was the trigger.
  Measured: Layer 3 (August 2026), jsbeeb. [Paradroid bug-map-corruption.md](https://github.com/kieranhj/paradroid-beeb/blob/main/docs/bug-map-corruption.md)
  Re-tested 2026-09-09 on jsbeeb-mcp 3.4.0 / jsbeeb 1.25.0: R7 = 34 against R4 = 30 in MODE 7 stops
  VSync (System VIA IFR bit 1 never sets again across 3,000 loop iterations, against 78 interrupts
  carrying it before the change) and the same 8 KB `*LOAD` still completed. That is R7 alone in a
  full-length frame, not Paradroid's rupture shape, and a different jsbeeb; treat the hang as real
  but not yet pinned to VSync as its cause.
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
- **`*TYPE <file>` prints a text file at any prompt, and needs no language ROM**: it is the
  filing system's own command, through OSASCI. That is what makes the build stamp worth keeping
  as a disc file (`INFO`) rather than only as a boot message - the disc can be asked what it is
  a week later. Works on DFS 1.20 and the Master's 1770 DFS; a boot that `*TYPE`s it costs one
  line of `!BOOT` and the sector `INFO` occupies.
  Measured: 2026-09-11, jsbeeb `B-DFS1.2` and `Master` - the kit template's dev disc, typed at
  the BASIC prompt and again from its `!BOOT`. [Paradroid b5ffa94](https://github.com/kieranhj/paradroid-beeb/blob/main/src/main.asm)
- **A filing system may hook `OSBYTE`, `OSWORD` and the vectors, and expects its workspace intact
  when it does.** Paradroid buried the workspace and then called `OSBYTE 229` per game start,
  `OSBYTE &0F` at the game over and `OSBYTE 19` at every rupture align, with no `OSBYTE 140`
  anywhere: fine on Acorn's DFS, which hooks none of them, and **it hung at the deck plan on an
  Opus 1770 with DDOS 3.45**. That is the only real-hardware evidence either way, and it is why
  `OSBYTE 140` is not optional for a game that calls the OS at all.
  Reported: 2026-09-13, hexwab, real hardware. [Paradroid layer-13-compatibility.md](https://github.com/kieranhj/paradroid-beeb/blob/main/docs/layer-13-compatibility.md)
- **`*EXEC` writes into `&1100-&1900`, and so does CLOSING an exec file.** A game running there -
  Paradroid at `&1100`, the kit's template higher at `&1900` - survives only because `*LOAD`, and
  `*RUN` which is `*LOAD` plus a jump, never touch the buffer area. Adding `OSBYTE 140` to
  Paradroid's boot hung the `*EXEC`-booted dev disc dead: black screen, CPU inside the DNFS ROM at
  `&ACB1` with `ROMSEL` 14, while the `*RUN` release disc was fine. Putting `OSBYTE 119` in front
  to close the exec file politely hung identically - the close is itself a write into the region
  it was meant to make safe. **Boot by `*RUN`** (`lib/boot_stamp.6502` builds only that shape).
  Measured: 2026-09-13, jsbeeb `B-DFS1.2`. [Paradroid 61500a8](https://github.com/kieranhj/paradroid-beeb/blob/main/docs/layer-13-compatibility.md)
- **Nothing guarantees filing-system workspace stops at `&1900`.** `&1900` is Acorn DFS's `PAGE`
  on a Model B; another filing system's OSHWM can be higher (and MMFS in sideways RAM puts it
  *lower*, at `&0E00`). hexwab: *"The safe thing to do is put our code as high as you can; read
  OSHWM to know which workspace regions to save."* Neither port checks, and neither does the kit -
  reading OSHWM at boot and refusing loudly, the way `swram_probe.6502` refuses too few banks, is
  the cheap guard and is **not built yet**.
  hexwab, 2026-09-13, paradroid-beeb #18. Not measured.
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
  [lib/zx02depack.6502](../lib/zx02depack.6502) [dmsc/zx02](https://github.com/dmsc/zx02)
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

*The kit assembles with Baron now - `lib/` and `template/` both - and four of these do not apply
to it; `docs/toolchain-baron.md` says which and what replaced them. They stay here because the
two shipping ports are beebasm projects, and because a port that goes back to beebasm meets them
again.*

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
- **The symbol dump** (BeebASM only - Baron has none, so the kit parses the listing instead:
  `python -m beeb_port_kit.listing symbols build/game.lst NAME`, and
  waitingforvsync/baron#5): `beebasm -i src/main.asm -do build/symbols.ssd -D RELEASE=0 -d | tr ',' '\n'
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
- **`run_for_cycles` reports what it actually ran, and runs on from a breakpoint - from
  jsbeeb-mcp 3.4.0.** On 3.3.0 and earlier `cycles_run` was the count *requested*, not the count
  run (a request for 600,000 that a breakpoint stopped after 598 reported 600,000), and a run
  starting with the PC already on a breakpoint returned `cycles_run` 0 having advanced nothing.
  Both were reported from this kit on 2026-09-07 (mattgodbolt/jsbeeb-mcp#25, #26), fixed in #30
  and **released in 3.4.0 the same day**. On 3.4.0: `cycles_run` is the cycles actually executed;
  a breakpoint sets `completed` false with `stopped_reason` `breakpoint`, and the registers at
  the stop carry `elapsed_cycles`, so the second `read_registers` this kit's procedures used to
  do is no longer needed; the next call runs on from where it stopped; and a breakpoint hit
  during an earlier call that did not report it comes back first as `stopped_reason`
  `pending_breakpoint` with `cycles_run` 0.
  Breakpoints DO fire under `run_for_cycles`; an older note saying otherwise was wrong.
  **Do not step frames with `run_for_cycles`**: a frame is 40,000 cycles with interlace on (the
  MCP default) but 39,936 with it off, so a fixed cycle step drifts against the display. Use
  `run_frames`.
  Measured: 2026-08-20 (Paradroid), 2026-09-02 (Edge), 2026-09-07 (this kit, on 3.3.0), and
  **2026-09-07 on jsbeeb-mcp 3.4.0 / jsbeeb 1.25.0 through the MCP**, on this kit's own template
  on `B-DFS1.2`: with an execute breakpoint at `main_loop` (`&194E`), a request for **600,000
  cycles returned `cycles_run` 38,948**, `completed` false, `stopped_reason` `breakpoint`, the
  breakpoint identified, and the registers in the same reply carrying `elapsed_cycles` 10,038,950
  and `frame_count` 255. `elapsed_cycles` went 10,000,002 -> 10,038,950, a delta of **exactly
  38,948** - so `cycles_run` is the truth and the second `read_registers` is genuinely redundant. [Paradroid raster-timing.md](https://github.com/kieranhj/paradroid-beeb/blob/main/docs/raster-timing.md) [Edge layer-2-display.md](https://github.com/kieranhj/edge-beeb/blob/master/docs/layer-2-display.md)
- **`run_for_cycles` used to overrun its request after a breakpoint stop**, leaving the unspent
  budget on the CPU: a 3,993,600-cycle request once ran 4,553,339 here, and jsbeeb-mcp's author
  measured a 1,000-cycle request running 75,987 straight after a stop. It was a jsbeeb bug
  (mattgodbolt/jsbeeb#1092), **fixed in jsbeeb 1.25.0 and shipped in jsbeeb-mcp 3.4.0**
  (jsbeeb-mcp#32). Keep counting fields **from `elapsed_cycles` and never from the number
  requested** anyway - the rule cost nothing, this kit had it for a year before it had a cause,
  and it is why the overrun never corrupted a measurement.
  Measured: 2026-09-06 (this kit, on 3.3.0), 2026-09-07 (jsbeeb-mcp#30's notes), and **the fix
  measured 2026-09-07 on 3.4.0 / jsbeeb 1.25.0**: stopped on the breakpoint above, so with the PC
  sitting on it, a 1,000-cycle request ran **exactly 1,000** (`completed` true) and
  `elapsed_cycles` went 10,038,950 -> 10,039,950. Both faults gone in one call - it neither
  returned 0 having advanced nothing (#26) nor overran (#32).
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
- **`save_state` / `restore_state` rewind memory, registers and the cycle count exactly - but
  not the keyboard.** A restore puts RAM, sideways RAM, video, sound, discs and the CPU back as
  they were, `elapsed_cycles` with them; jsbeeb's own frame counter carries on climbing, and a
  state can be restored into ANY session of the same model, including one that never loaded the
  disc. **A key held with `key_down` stays held across a restore**: restoring a state saved
  before the key, then running 50 frames, scrolled the play area exactly as if the key were
  still down - because it was. `key_up` it yourself as part of the restore - or, **from
  jsbeeb-mcp 3.4.0, `release_all_keys`**, which also drops typing left pending by an interrupted
  `type_input`. **`keyboard_state`** reports every key the machine currently sees held, with its
  matrix column and row, its name, and on a BBC its internal and INKEY numbers; check it before
  any test that assumes nothing is held (jsbeeb-mcp#33).
  Measured: 2026-09-07, jsbeeb-mcp 3.4.0. `key_down key:"X"` reported
  `{col: 2, row: 4, name: "X", internal: 66, inkey: -67}`; `keyboard_state` then listed exactly
  that key with `typing_pending: false`; `release_all_keys` reported it released. The internal
  number agrees with section 7's table, which is a free cross-check of both.
  Measured: 2026-09-07, jsbeeb MCP 3.3.0 / jsbeeb 1.24.1, the kit's template. Save at the idle
  state; hold X; 50 frames -> `scroll` 200, `frame_count` 113. Restore -> `scroll` 0,
  `elapsed_cycles` back to its saved value to the cycle, PC and A/X/Y identical. 50 frames again
  with the key still latched -> 200 and 113 again, byte for byte. Restore, `key_up X`, 50 frames
  -> `scroll` 0. The same state restored into a second, disc-less machine and run 50 frames gave
  the same 113: **one boot can seed any number of machines**.
- **`read_memory` returns whatever bank is paged at that instant.** A sample taken inside a sprite
  draw returned bank 5's empty space, which read exactly like the player having been wiped. Check
  `&F4` first. Reading shadow RAM from the CPU side likewise follows the X bit.
  **From jsbeeb-mcp 3.4.0 you do not have to guess** (jsbeeb-mcp#35): `read_memory` and
  `save_memory` report the paging they read under - `romsel`, and `acccon` on a Master - and take
  `bank` or `shadow` to read a particular one whatever is paged in. Prefer that to reading `&F4`
  and hoping.
  Measured: 2026-09-07, jsbeeb-mcp 3.4.0, the kit's template on `B-DFS1.2`. A plain read of
  `&8000` came back with `paging: {romsel: 14}`; the same read with `bank: 12` came back
  `{romsel: 14, bank: 12}` and returned bank 12's contents, not the paged bank's.
  Measured: Layer 7 (Paradroid combat, 2026-08), 2026-09-04 (Edge titles). [Paradroid layer-7-combat.md](https://github.com/kieranhj/paradroid-beeb/blob/main/docs/layer-7-combat.md) [Edge layer-6e-titles.md](https://github.com/kieranhj/edge-beeb/blob/master/docs/layer-6e-titles.md)
- **jsbeeb WILL boot an unpadded SSD, and padding is not a build step.** An earlier note claimed
  it would not and blamed a hang in the DFS FDC poll at `&ACAE` on an image ending mid-track; KC
  corrected it on 2026-09-01, and the version detail came from jsbeeb's author on 2026-09-07:
  **jsbeeb stopped complaining in 1.9.0**, and **jsbeeb-mcp 3.0.0** is the first release whose
  declared dependency guarantees that fix. Anything at or past those boots a 2,304-byte image as
  happily as a 204,800-byte one.
  Measured: 2026-09-07, jsbeeb MCP (jsbeeb-mcp 3.3.0, jsbeeb 1.24.1). The kit template's
  unpadded `game.ssd` (2,304 bytes) booted on `B-DFS1.2` and `Master`: `!BOOT` EXECed, `PANEL`
  unpacked to `&4A00` byte-identical to its source, 100 fields in 100 frames, 50 loop passes in
  those, `scroll` 0 -> 200 under 50 fields of X.
  **Padding to 200K (204,800 bytes) remains a PUBLISHING convention**: a published size that
  differs from the last publish is a useful signal that the wrong file went out. `py/dfs.py`'s
  `pad()` is there for that, and for nothing else. [Paradroid CLAUDE.md](https://github.com/kieranhj/paradroid-beeb/blob/main/CLAUDE.md) [Paradroid layer-4-player.md](https://github.com/kieranhj/paradroid-beeb/blob/main/docs/layer-4-player.md)
- **jsbeeb emulates the VideoNuLA palette** (`?&FE23=&78 : ?&FE23=&88` gives mid grey; sixteen
  distinct entries come back under logical mapping). **Its NuLA scrolling and attribute modes are
  NOT emulated.** The belief that a NuLA build could not be tested in jsbeeb is what let a
  palette-mapping mistake reach real hardware.
  Measured: 2026-09-05, jsbeeb, decision 67. [Edge CLAUDE.md](https://github.com/kieranhj/edge-beeb/blob/master/CLAUDE.md) [Edge layer-8b-nula.md](https://github.com/kieranhj/edge-beeb/blob/master/docs/layer-8b-nula.md)
- **jsbeeb needs VSync for the 8271 poll - no longer true, if it ever was the cause**: with R7
  parked so VSync never fires, `*LOAD` hung at `&ACAE` (section 6), reproducing from BASIC, so it
  was not the game.
  Measured: Layer 3, jsbeeb. [Paradroid bug-map-corruption.md](https://github.com/kieranhj/paradroid-beeb/blob/main/docs/bug-map-corruption.md)
  On jsbeeb-mcp 3.4.0 / jsbeeb 1.25.0 the same idea does not reproduce: with VSync confirmed dead
  (IFR bit 1 never sets) an 8 KB `*LOAD` runs to completion. See section 6 for the re-test.
  Measured: 2026-09-09, jsbeeb-mcp 3.4.0 / jsbeeb 1.25.0.
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
- The vertical total adjust displaying under `R6 > rows` is a jsbeeb 1.25.0 result on a Master
  (1942 Layer 2b) and on a Model B (`template/examples/vscroll`), both 2026-09-08. Rich
  Talbot-Watkins's demo relies on the same behaviour and runs in jsbeeb too, but nothing has
  checked it on b2, beebjit, b-em or real hardware.
- DFS sector timings are jsbeeb's disc model and were flagged as such before any faster reader was
  costed. [Paradroid loader-compression.md](https://github.com/kieranhj/paradroid-beeb/blob/main/docs/loader-compression.md)
- The keyboard phantom on real hardware was reported, not instrumented, and the redefined-controls
  case remains open. [Paradroid human-notes-status.md](https://github.com/kieranhj/paradroid-beeb/blob/main/docs/human-notes-status.md)
