# The smooth vertical scroll example, measured

*`examples/vscroll/`, built and measured 2026-09-08, jsbeeb 1.25.0, `B-DFS1.2` (a BBC Model B).
It is a worked example of Rich Talbot-Watkins's frame shape for scrolling one scanline at a time,
under key control, and of what that shape does and does not cost. The kit's facts about the
technique are in `../../docs/hardware-facts.md`, "The vertical total adjust displays"; the primary
sources are `BEEB\Notes\Vertical Rupture.txt` (Rich's write-up) and `BEEB\Disks\RTW\smoothscroll.ssd`
(his demo - detokenise `$.TEST25` and read the register writes).*

## What it is, and why it is not the template itself

The template's own rupture scrolls **horizontally** with the panel on top, which is what both
shipped ports do and what most ports want. This example is the other shape, kept beside it rather
than replacing it, because a scanline vertical scroll wants the frame the other way round:

```
build\VSCROLL.SSD        SHIFT+BREAK, or *RUN VScroll
    cursor UP / DOWN     scroll the view one SCANLINE per 25 Hz tick
```

| | the template | this example |
|---|---|---|
| scroll | horizontal, one CRTC unit (4 px) a tick | **vertical, one scanline a tick** |
| cycle 1 | panel, 4 rows at `&4A00` | **play strip, 15 rows, scrolled** |
| cycle 2 | play strip, 16 rows, VSync inside | **panel, 4 rows at `&4A00`, VSync inside** |
| R5 | 0, never written | **`line` and `8 - line`, one per cycle** |
| R6 | `PLAY_ROWS` = 16 | **`PLAY_VIS_ROWS + 1` = 16: the adjust row displays** |
| palettes | two, switched at a measured phase | **one** - there is no gap to hide a switch in |
| T1 fires | 3 | 3 |

## The frame

38 rows + 8 adjust scanlines = 312 lines, with line 0 at the VSync edge:

```
line   0  panel rows 14-22 run out                          72 lines
line  72  the PANEL cycle's adjust: (8 - line) lines of TOP BORDER
line  80-line  the PLAY cycle starts, from the scroll address. Its first
          `line` scanlines are real, displayed and wrong; R8 is blank over them
line  80  R8 ON. THE FIRST VISIBLE PLAY LINE = scanline `line` of the buffer
          row at the scroll address. FIXED, whatever the scroll is
line 200-line  the play cycle's 15 rows end. Its adjust follows: `line`
          DISPLAYED scanlines of the 16th row - the bottom sliver
line 200  the panel cycle starts IMMEDIATELY, no gap: 4 rows
line 232  PANEL_R6 = 4 has ended its display; blanking from here
line 312  the next VSync edge (panel row PANEL_R7 = 14)
```

The two things that make it free, and both hinge on the play strip being first:

1. **The `(8 - line)` adjust is top border.** Nothing can see it, and because
   `(8 - line) + line = 8` the first visible play line sits at a fixed distance from the VSync
   edge whatever `line` is. Nothing slides, and there is no gap, because the blanked scanlines at
   the top of the play cycle are indistinguishable from the border above them.
2. **The bottom sliver comes out of the play cycle's own adjust, which displays.** `PLAY_R6 =
   PLAY_VIS_ROWS + 1` keeps display enable on through the adjust and the CRTC fetches the 16th
   buffer row's top `line` scanlines. This is the behaviour Paradroid refused to depend on, so it
   is measured here rather than assumed.

## The three fires

| | at | writes | why there |
|---|---|---|---|
| VSync | line 0 + ~4 | restart T1; take the parked position (all four bytes); `R5 = 8 - line`; `R6 = 16`, `R7 = 127` and `R12/13` for the play cycle; `R8` blank | R5 is sampled at line 72, 68 lines away; the rest belong to the *previous* cycle, which is this one |
| fire 1 | line 80 | **`R8` ON** - the only scanline-exact write in the frame - then `R4 = 14` | the first visible play line |
| fire 2 | line 140 | `R5 = line`; `R12/13` for the panel | the R5 trap: the middle of the cycle, 60 lines from where it is sampled |
| fire 3 | line 204 | `R4 = 22`, `R6 = 4`, `R7 = 14` | panel row 0, before C4 reaches any of them |

**Fire 2 exists only because of the R5 trap.** R5 is sampled at each cycle's end, and changed
after the adjust counter has passed the new value the match never happens and the adjust runs on
to its 5-bit wrap. Rich writes the play cycle's R5 in his *first* fire and gets away with it by
instruction ordering; at `line` = 0 our fire 1 lands in the blanking of the panel adjust's last
scanline, which is precisely the worst case, so the write goes in the middle of the cycle.

## T1_PHASE, measured by sweeping it

Fire 1 writes R8, and an R8 write takes effect immediately, so one landing in displayed time cuts
its scanline part-way across. MODE 1 at `R1 = 80` displays 80 of 128 character times, so the
blanking window is 48 CPU cycles wide.

`T1_PHASE` is in 1 MHz ticks (2 CPU cycles each). It was **measured by building the example at
each value and reading the oracle**, not calculated:

| `T1_PHASE` | result |
|---|---|
| 0, 8, 16, 18 | the lit run is **153** scanlines at `line` = 1, not 152: the write lands before its target line and lights a scanline that should have been blanked |
| **20 to 42** | **pass** - 152 lit scanlines at every `line`, 0 of 38,400 pixels wrong |
| 44 | 8 pixels wrong: the write has crossed into the first visible line's displayed part |
| 46, 48, 56 | 24, 32 and 88 pixels wrong - the cut moves further across the line |

The passing window is 23 ticks = **46 CPU cycles wide, against MODE 1's 48 cycles of horizontal
blanking** - which is the cross-check that the instrument is measuring what it claims to.
`T1_PHASE = 31` is the middle of it, with 11 ticks of margin each way. **Re-measure it if
anything in the IRQ path before that write changes.**

## Measured

All 2026-09-08, jsbeeb 1.25.0, `B-DFS1.2`, on `build/VSCROLL.SSD` at `T1_PHASE = 31`:

| What | Result |
|---|---|
| Field length | **39,936.00 cycles over 100 fields** - 312 lines, unchanged by the scroll |
| Strip oracle (A) | **0 of 10,240** bytes, every tick |
| View oracle (B) | **0 of 38,400** pixels, at all eight values of `line` |
| **The sliver** | **0 wrong of 19,840 pixels fetched by the vertical total adjust** |
| Lit structure | **one run of 152 scanlines, 320 wide, nothing else lit**, at every position |
| `linesSeen` | `[0,1,2,3,4,5,6,7]` - every sub-row phase, twice |
| Code size | 869 bytes at `&1900`, 5,019 free to `&3000` |

The lit run's *length* is itself a test: if the adjust stopped displaying, the run would be short
by `line` and the number would move with the scroll instead of standing still at 152.

## What the shape costs here, and what it does not

**It does not buy a row back in this geometry, and that is worth understanding.** The strip is the
template's - 10K wrap, 640-byte rows - so the ring is exactly 16 rows and the window may fetch 16.
Paradroid, in the same geometry, gets 16 displayed rows of which 15 are visible; this example gets
15 visible plus a fetched sliver. Same 15. **The row Paradroid lost was the wrap's doing, not the
technique's**: a ring with a spare row gets the row as well as everything below.

What it does buy, against the panel-first shape:

- **no visible gap.** The panel-first shape has to blank the `(8 - line)` adjust between the two
  areas, and (if the adjust may not display) a second 8-line band under the play area.
- **one scanline-exact R8 edge instead of four**, because there are no blanked gaps to bound.
- **no palette switch.** There is no blanked scanline at the boundary for one to hide in - that is
  what "no gap" means - so the panel draws in the play palette. If a HUD ever needs its own
  colours, a partial switch of two logical colours is eight ULA writes = 48 cycles, which fits
  MODE 1's blanking exactly and would need a measured phase; all sixteen (96 cycles) would not fit
  and would cost a play-line.

## Not measured

- **b2, beebjit and real hardware.** Everything here is jsbeeb 1.25.0. The behaviour the shape
  depends on - the vertical total adjust displaying when `R6 > rows` - has not been checked on any
  other emulator or on a real machine, by this example or by 1942, which measured it on a Master.
  Rich's own demo is a Model B program that relies on it and runs, which is evidence about the
  6845 but not a measurement of the sliver. Run `skills/beeb-cross-emulator` before spending
  anything on it.
- **Where the picture sits on a tube.** `PANEL_R7 = 14` puts the 152-line picture at line 80,
  near where the OS's MODE 1 sits. Chosen by arithmetic, not by eye on a display.
- **The scroll's feel.** No emulator can judge smoothness; one scanline per 25 Hz tick is the
  rate, not a taste call that has been played.

## How to run the checks

```powershell
cd examples\vscroll
.\build.ps1
python ..\..\tools\listing.py symbols build\VSCROLL.lst     # crtc_live, line_live, ypos
node tools\verify_vscroll.mjs build\VSCROLL.SSD 02 0D 10
```

**The addresses are HEX and they move on every edit** - Baron allocates the zero page, so take
them from the listing each time; decimal silently measures the wrong bytes and returns numbers
that look like a regression. The harness prints one JSON line per scroll position and a summary,
and exits non-zero on any failure.

**Feed it the LIVE position, never `ypos`.** The main loop parks the next position and the VSync
hook takes it two fields later, so `ypos` runs a game tick ahead of what the CRTC was given. 1942
scored 57,284 of 57,344 pixels wrong on a correct build by feeding an oracle the parked pair
(kit `docs/verification.md`, procedure 3).
