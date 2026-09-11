# Rules that bite

*Part of [beeb-port-kit](../README.md). The bug classes that recurred across two C64 to BBC Micro
ports - [Paradroid](https://github.com/kieranhj/paradroid-beeb) (Model B, August 2026) and
[Edge Grinder](https://github.com/kieranhj/edge-beeb) (Master 128, September 2026) - each with
the instance that taught it, the evidence, and the rule that came out of it.*

Every entry here was paid for. Both ports kept a `BUGS.md` that records what was ruled out as
well as what was wrong, and a set of layer documents that record measurements beside the code
they measured; this file is the same material sorted by *kind* of mistake rather than by date,
because the second port made a striking number of the first port's mistakes again, in new
places, before it had read the first port's notes. The classes are the point. A developer who
has never seen `explosion_dirs` or `disrFlash` will still meet a runtime table that drifts over
an unguarded ceiling, or a byte that is zero on the emulator and garbage on the machine.

A few entries also draw on **1942** (Master 128, September 2026), the first port built with this
kit; it is unpublished, so those name the layer and the date rather than a link.

The entries only state what the two repositories record. Where a figure is quoted it is the
figure in the source document, and where the source document itself was later corrected the
correction is given rather than the original. Two things could not be confirmed from the
repositories and are flagged where they appear: a verbatim "do not judge smoothness in an
emulator" rule, and a specific bug from confusing the two VIA timers. Links are to the files at
the commits current when this was written; the layer documents in particular carry numbers that
their own headers say go stale, so treat a quoted byte count as history and take a live one from
the listing.

---

## 1. Believing a model over the artefact

**A screenshot of the original beats a model of it.**
Instance: Paradroid's charset reader was corrected three times. The first read it as 1bpp with a
nibble split, the second called the whole set multicolour, the third decided both modes were in
use, selected per cell by bit 3 of the colour nibble - and that third reading stood from Layer 1
until 2026-08-18. The play area is hires: `$D016` bit 4 is clear in play, and bit 3 is part of
the colour. One C64 screenshot of deck 5 settled it three ways at once (light grey floor, solid
orange crosshairs, crisp `ALERT.` lettering).
Cost: every cell coloured 8-15 - most of the ship's structure - was drawn as four doubled pixels;
the ALERT lettering was mangled on eight decks and written up *as faithful*, twice, on the
strength of the theory. The fix bought back 305 bytes of bank 4 and halved the conversion.
Source: [docs/layer-1-graphics-pipeline.md](https://github.com/kieranhj/paradroid-beeb/blob/main/docs/layer-1-graphics-pipeline.md).

**A copy of the specification is itself a thing to verify against the original.**
Instance: Paradroid's annotated listing - the copy of the C64 disassembly everything was read
from - was produced by a script that kept only the first tab-separated group of each `.BYTE`
line. Looking up `CharColor` at `$0800` returned 76 bytes of a 256-byte table. Across the file,
21,405 of 49,537 data bytes survived: 295 blocks truncated and 96 blocks whose *values disagreed*,
because dropping a column group shifts everything after it.
Cost: 43% of the original's data was missing and the rest was misaligned, for as long as the
annotated listing had existed. A truncated table announces itself eventually; a misaligned one
hands back a real-looking byte from the wrong entry. `tools/verify_annotation.py` is the
standing check.
Source: [BUGS.md #19](https://github.com/kieranhj/paradroid-beeb/blob/main/BUGS.md),
[tools/verify_annotation.py](https://github.com/kieranhj/paradroid-beeb/blob/main/tools/verify_annotation.py).

**The nearest previous port is not the specification either, and neither is this kit.**
Instance: 1942 needed 1-scanline vertical scrolling and took the shape the kit encoded - Paradroid's
three CRTC cycles, panel above the play area, the vertical total adjust never allowed to display.
It worked, and it verified 0/0, and it cost two visible 8-line gaps, six timer fires instead of
three, and the vertical blanking interval down from 32 lines to 16. None of that was intrinsic to
the technique. Paradroid's shape answered Paradroid's constraints: a 10K wrap that made its strip
exactly 16 rows, so there was no spare row for the sub-row sliver, and a panel that sits above the
play area. KC read the gaps off the screen and pointed at the technique's author - Rich
Talbot-Watkins's write-up and his working demo disc, neither of which the kit cited. Putting the
scrolling area first and letting the adjust display removed both gaps, three fires, both palette
switches and the open decision that had been raised to pay for them.
Cost: the frame rebuilt twice inside one layer, and a costed decision with four fallbacks, all of
which paid in play area, none of which was necessary.
Rule: **when a borrowed technique costs something, ask whether the cost is intrinsic to it or to
the port you copied it from** - and read what the technique's own author does before assuming the
nearest previous implementation got it right.
Source: 1942 Layer 2b, 2026-09-07/08; the facts and measurements are in
[hardware-facts.md](hardware-facts.md) under *The vertical total adjust displays*.

**"I cannot measure this" is itself a claim, and it wants testing.**
Instance: Edge Grinder's VideoNuLA build (decision 63) wrote no `&FE21` at all, inferring from a
reference gallery that NuLA is indexed by the logical colour. The decision said honestly that
this was unverified - because it believed jsbeeb had no NuLA to test against. KC ran the disc on
real hardware and the scenery came back with a blue background. Decision 64 found the cause in
the manual (by default NuLA *composes* the `&FE21` palette with its own `&FE23` one, and the
titles' raster code leaves logical 15 on physical 7) and fixed it with `&FE22 = &11`. Decision 67
then measured that jsbeeb emulates the NuLA palette perfectly well: the manual's own
`?&FE23=&78 : ?&FE23=&88` gives mid grey, a colour no plain BBC has.
Cost: a hardware assumption reached real hardware that one boot and a screenshot would have
caught.
Source: [docs/decisions.md rows 63, 64, 67](https://github.com/kieranhj/edge-beeb/blob/master/docs/decisions.md),
[docs/layer-8b-nula.md](https://github.com/kieranhj/edge-beeb/blob/master/docs/layer-8b-nula.md).

---

## 2. Recalled arithmetic

**Do not write hardware code from recalled facts; measure the number in the emulator first.**
Instance: Paradroid's blitter document put the off-display window at 184 scanlines and 11,776
cycles and concluded that no rescheduling of the sprite work could fit inside it. A scanline is
64 us, which is **128** CPU cycles at 2 MHz, not 64; the window was 192 scanlines, not 184; so it
was 24,576 cycles, and there were two of them a pass. The work fitted. It was in the wrong places.
Cost: a whole flicker plan built on a budget half the real size.
Source: [docs/raster-timing.md](https://github.com/kieranhj/paradroid-beeb/blob/main/docs/raster-timing.md),
[docs/layer-5-blitter.md](https://github.com/kieranhj/paradroid-beeb/blob/main/docs/layer-5-blitter.md).

**Take a raster phase from the emulator, not from the arithmetic that once produced it.**
Instance: Paradroid's `T1_TUNE` came from a calibration recorded beside it. By the time the flicker
was chased, the CRTC writes for fires 2 and 3 were landing at cycles 120-124 of a 128-cycle
scanline, 3-7 cycles from the wrap - less than the IRQ's own latency swing (`SEI` window alone 17
cycles). Reality had drifted about 6 us later than the calibration because the whole IRQ path had
changed since. Measured by breakpoint and `elapsed_cycles` mod 128, then moved 10 us earlier.
Cost: an intermittent character of the row below the view in the bottom-left corner.
Source: [docs/raster-timing.md](https://github.com/kieranhj/paradroid-beeb/blob/main/docs/raster-timing.md).

**Both VIAs' timers tick at 1 MHz: one tick is two CPU cycles. Write the doubling into the
instrument.** Paradroid's audit stubs note it for System VIA T1 ("remember it counts at 1 MHz")
and Edge Grinder's frame meter for User VIA T2 ("to compare a figure here against the cycle counts
in docs/, DOUBLE IT"). *Not confirmed:* the repositories do not record a bug from confusing T1
with T2; what they record is each port having to state the unit conversion in its own header.
Source: [docs/perf-audit-2026-08-31.md](https://github.com/kieranhj/paradroid-beeb/blob/main/docs/perf-audit-2026-08-31.md),
[src/timing.asm](https://github.com/kieranhj/edge-beeb/blob/master/src/timing.asm).

**Check the range of a value before you take its sign from bit 7.**
Instance: Edge Grinder turned the C64's halved x into a byte column with `CMP #&80 : ROR`, an
arithmetic shift. `x - SPR_X_OFF` runs -12 to 243 and does not fit a signed byte, so every sprite
at x >= 140 came out with a large negative column and was culled as off the left edge. The 149
waves that spawn at x = 172 stayed invisible until they had crossed a third of the screen. The sign
now comes from the subtraction's carry.
Cost: from Layer 3 to Layer 5, and it poisoned a measurement (see class 11). It would have hidden
the player past x = 139 too, `PLY_X_MAX` being 155.
Source: [BUGS.md #8](https://github.com/kieranhj/edge-beeb/blob/master/BUGS.md).

**`LSR` then `ASL` does not restore a value.**
Instance: Paradroid's `DrawHalf` computed `halfX >> 1` by shifting in place and "restoring" with
`ASL`, which only works when the low bit was 0. `RedrawAll` set `halfX` once and incremented it
across a row, so the damage was written at deck load and persisted, because incremental scrolling
never repairs the interior. Bit on decks 2 and 14, both centring at `mapHX` = 180, where
`mapHX + 79` crosses 256.
Source: [docs/layer-3-scroll.md](https://github.com/kieranhj/paradroid-beeb/blob/main/docs/layer-3-scroll.md).

**A "maximal LFSR" tap you remembered is not maximal until you have simulated it.**
Instance: Paradroid's `XfRand` documented itself as a maximal 8-bit LFSR with taps `$B4`. `$B4`
has its low two bits clear, so bit 0 of every output is 0 for ever and the period is 65, not 255.
`AND #3` returned 0 almost always; `AND #&F` could produce six of sixteen values; one `CMP #3`
branch in the transfer game had never been taken. Fix: `$1D`, the polynomial the droid code
already used.
Cost: the game-over wash drew in one column only, and the transfer board and CPU opponent were
less varied than the original's, invisibly, from Layer 10.
Source: [BUGS.md #14](https://github.com/kieranhj/paradroid-beeb/blob/main/BUGS.md).

**Look the register bit up; do not build a control byte from what it "obviously" is.**
Instance: Edge Grinder's AY-to-SN converter built the noise byte as `&E0 | rate`. Bit 2 selects
white noise; clear, the chip plays periodic noise, a short repeating pattern that sounds like a
pitched tone. Every drum in the tune came out as a note. Diagnosed by comparing noise bytes in the
two streams (`&E4-&E7` shipping against `&E0-&E2` at runtime), not by ear.
Source: [BUGS.md #12](https://github.com/kieranhj/edge-beeb/blob/master/BUGS.md).

---

## 3. Silent memory drift

**Main RAM has a ceiling for things read in play and a higher one for boot-only things. Guard
the lower one, or a runtime table will cross it in silence.**
Instance: Edge Grinder's `explosion_dirs` sat at `&2024`, inside `SPR_SAVE` (`&2000-&2FFF`), the
sprite engine's saved-background area, rewritten every frame from the first sprite drawn. Slot 0's
page is the player's, so the player's own saved background landed on the twelve bytes his
explosion pieces fly on. The build's FREE figure was measured to `LOAD_STREAM` = `&2200`, the
right ceiling for the loader and depacker and the wrong one for anything read in play, and
nothing checked the other. Read out live: `enemy_spds` all zero after `life_lost`.
Cost: latent since main RAM first grew past `&2000`; surfaced two layers later when the starfield's
18 bytes moved the table to a different part of the same page, and was reported as a regression in
the starfield. `main.asm` now carries `ASSERT code_end <= SPR_SAVE`, and `code_end` was `&1FF9` -
seven bytes under.
Source: [BUGS.md #13](https://github.com/kieranhj/edge-beeb/blob/master/BUGS.md),
[CLAUDE.md](https://github.com/kieranhj/edge-beeb/blob/master/CLAUDE.md) "Facts about the current code that the old docs got wrong".

**`CLEAR` releases the assembler's overwrite guard over exactly the range an over-long image
spills into. Use `GUARD` at the ceiling, because it fires at the instruction that crosses it.**
Instance: Paradroid's code image ran up to `FONT_ADDR` = `&3000` with eleven bytes spare;
`DEBUG_VSYNC` added 143. beebasm did not object, because a `CLEAR FONT_ADDR, ...` further down the
file had released the guard there. `*RUN PARA` scribbled the tail over the font, the font load
scribbled it back, and the symptom was a corrupt player sprite and an unreadable digit. The only
bound was `ASSERT code_end <= SPR_SAVE`, 3,584 bytes too slack since the font had moved.
Cost: the flag had been broken for as long as the image had been full - 105 bytes over on the
commit before the one blamed. Five other debug flags now fail the build with a message instead.
Source: [BUGS.md #17](https://github.com/kieranhj/paradroid-beeb/blob/main/BUGS.md).

**The end of a file is not the end of the region. Check what follows before calling a gap spare.**
Instance: Paradroid put three high-score strings at `FONTCODE_ADDR + FONTCODE_BYTES`, which is
also the definition of `PN_TABS`, the mirrored droid tables copied down from bank 4 at every
title. The strings loaded and were overwritten. `DbStr` then printed the droid table as text, some
272 glyphs, walked out of the play buffer past `&8000` into bank 7 and flattened `xfRowAdrLo/Hi`;
on the *next* game over the wash loaded a zero high byte and wrote 640 bytes from `&00EE` through
zero page, the stack and the MOS vectors. Found by a write breakpoint on the table.
Cost: a hang followed by a drop into BASIC, two screens after the cause. The strings ended up in an
overlay with no resident RAM at all, which was the right size of fix; the wrong instinct was to
hunt for 77 bytes elsewhere.
Source: [BUGS.md #18](https://github.com/kieranhj/paradroid-beeb/blob/main/BUGS.md).

**A listing-based gap finder cannot tell `SKIP`ped storage from padding, and an `ALIGN` removed
upstream reappears at the next `ALIGN` downstream.**
Instance: the first analysis of Paradroid's RAM pass claimed 739 bytes of alignment holes in bank 4.
Four of the six holes were `SKIP`-reserved working storage. The 111 genuine bytes of `ALIGN &100`
padding could not be recovered either: `tiledefs` follows with an `ALIGN` of its own, and its
alignment is load-bearing (`MapChar` builds a pointer with no `LO(tiledefs)` term anywhere).
Bank 4 free stayed at 15.
Source: [docs/layer-13-ram-pass.md](https://github.com/kieranhj/paradroid-beeb/blob/main/docs/layer-13-ram-pass.md),
[docs/ram-pass.md](https://github.com/kieranhj/paradroid-beeb/blob/main/docs/ram-pass.md).

**"Written before it is read" has to hold on every path, including the ones outside the game.**
Instance: Paradroid's `lowbss` was `SKIP`ped and never zeroed, on the rule that everything in it is
written before it is read. `disrFlash` is read by the rupture IRQ's palette code from the first
title onwards, and `GameStart` - a whole title, high-score entry and briefing later - was the
first thing to clear it. Cold-boot garbage there meant a white briefing, once per session.
Cost: two white-screen bugs (2026-08-28 and 2026-08-30) and a third when the intro started
writing over `&0400-&21FF`. See also class 6: the emulator zeroes RAM, which is why it never showed.
Source: [docs/memory-map.md](https://github.com/kieranhj/paradroid-beeb/blob/main/docs/memory-map.md),
[docs/layer-11f-frontend.md](https://github.com/kieranhj/paradroid-beeb/blob/main/docs/layer-11f-frontend.md),
[docs/intro.md](https://github.com/kieranhj/paradroid-beeb/blob/main/docs/intro.md).

**A local label inside `{}` shadows a global of the same name, silently.**
Instance: Edge Grinder's `wave_manager` had a `.comp_flag` label beside the `comp_flag` variable it
sets; `sta comp_flag` would have stored into code. Assembles cleanly, fails quietly. Do not name a
local label after anything it is used next to.
Source: [CLAUDE.md](https://github.com/kieranhj/edge-beeb/blob/master/CLAUDE.md).

---

## 4. Paths nothing has called

**A path nothing has ever called is not a tested path, and the layer that first calls it will
be blamed for it.**
Instance: Edge Grinder's wave manager has a path for a wave falling due with no free slot; it must
consume all nine bytes of the wave and throw them away. The C64 writes the nine reads out longhand.
The port's loop ran seven times, eight bytes of nine, so from that moment the reader sat one byte
inside every later wave: shield read as x, x as y, y as the first movement command. The path only
runs with all six pool slots full, which nothing did until the player explosion in Layer 6b filled
them - so it was wrong from Layer 5 and unreachable.
Cost: three different symptoms by which wave the player died on, all one cause. Measured after
the fix over 3,500 frames of repeated deaths: the pointer stayed a multiple of nine from the table.
Source: [BUGS.md #10](https://github.com/kieranhj/edge-beeb/blob/master/BUGS.md).

**Enter a second deck (level, screen, state) before believing a result.**
Instance: Paradroid's `DroidsInit` skipped a roster hole and left the previous deck's droid in the
table. The table starts zeroed, so the first deck entered is always clean, and every unattended
test in Layers 5 and 6 ran on deck 1 from a cold boot. On deck 8 four stuck droids stood on cells
at rows 6, 18 and 26, which are deck 1 waypoints exactly. `drCount` read 14 for a deck that holds 6.
Cost: invisible to the whole verification suite by construction.
Source: [BUGS.md #8](https://github.com/kieranhj/paradroid-beeb/blob/main/BUGS.md).

**A harness is only as good as the inputs it was given. Cover odd and even, both axes.**
Instance: two runs of Paradroid's scroll diff harness reported 0 differing bytes and were
worthless: both used an even number of horizontal steps (30 and 300), so `halfSel` was always 0
and the odd path never executed. The harness was sound. Every scrolling bug in that port hid in
non-zero `line`, odd `mapHX` or a diagonal.
Source: [docs/layer-3-scroll.md](https://github.com/kieranhj/paradroid-beeb/blob/main/docs/layer-3-scroll.md) "Testing lesson",
[CLAUDE.md](https://github.com/kieranhj/paradroid-beeb/blob/main/CLAUDE.md).

**When the code grows a second path, the oracle recipe has to grow with it.**
Instance: Paradroid's buffer oracle said "poke `JSR SprDrawAll` to NOPs so the sprites cannot
pollute the diff". Once the tranche split existed, draws also went through two `JSR SprDrawTr`
sites, and a diff taken with only the first NOPed showed a player-shaped block of "corruption"
that was nothing of the kind. All three call sites now.
Source: [docs/ram-pass.md](https://github.com/kieranhj/paradroid-beeb/blob/main/docs/ram-pass.md) "The oracle recipe changed".

**If the check disables the thing that is broken, it will pass for weeks.**
Instance: Paradroid's interpreted sprite row fell into the wrong tail and drew every later row on
top of it; the restore mirrored the fault exactly and put the background back correctly. The
buffer-vs-`RedrawAll` diff with the draw disabled reported 0 differences for weeks. The symptom was
only ever in the *drawn* sprite, and every check disabled the draw.
Source: [BUGS.md #5](https://github.com/kieranhj/paradroid-beeb/blob/main/BUGS.md).

**Reproduce the rare case on demand by forcing the branch, not by waiting for it.**
Instance: Paradroid's wrapping sprites drew a white number because the fallback path never
recoloured. Patching the fast-path test to `LDA #0` forced every sprite down the fallback and made
the defect appear on every droid. The opposite lesson is #12: four scripted attempts to reproduce
the console corruption with droids beside the player all came out clean, because a droid next to
the player merges into his component and never reaches tranche B. It needed a bullet.
Source: [BUGS.md #16 and #12](https://github.com/kieranhj/paradroid-beeb/blob/main/BUGS.md).

**Say which paths have never run.** Edge Grinder's AKL player has arpeggio tables, pitch tables
and five effects "written but have never run, because EDGEA uses none of them", and its exporter's
`--check` says when a song strays into one.
Source: [docs/layer-7-music-arkos.md](https://github.com/kieranhj/edge-beeb/blob/master/docs/layer-7-music-arkos.md).

---

## 5. Instrumentation that lies

**Assert your patches. A patch that silently fails to apply produces a plausible number.**
Instance: a patch meant to move Paradroid's T1 bracket off `DoRedraws` did not match the file
(an em dash in the pattern), so the build had two brackets. `dbgAcc` summed two routines and
`dbgN` counted twice a pass, which made the game look as if it ran at one field a pass - double
speed. It was not: `plyX` moved 612 to 901 in the same two seconds, before and after.
Source: [docs/layer-5-blitter.md](https://github.com/kieranhj/paradroid-beeb/blob/main/docs/layer-5-blitter.md).

**A tint that is opened must be closed, or it reports everything until the next one.**
Instance: Paradroid's `DEBUG_DRAW` set magenta before `SprAnimateAll` and never closed it after
the draw, so when the droid AI moved below the draw the band ran on through `DroidsUpdate`, the
collisions, aging, `PanelTick` and the idle - some 20,000 cycles of display-period work reported
as sprite work. KC read it as the sprites overrunning the play area. Nothing was overrunning.
Source: [docs/raster-timing.md](https://github.com/kieranhj/paradroid-beeb/blob/main/docs/raster-timing.md) "the magenta band was lying".

**A free-running timer difference is only arithmetic while the counter has not passed zero
between the reads.**
Instance: the same bracket reported `ReadKeys` at 2,903 cycles after a change that made it three
times cheaper (1,009 before). 147,460 ticks against 19,200 expected is an excess of 1.96 x 65,536:
two wraps. And because the reload point drifts slowly through the pass, the bad readings arrive in
consecutive runs, so one run is clean and the next is not. For anything short, a breakpoint pair
and an `elapsed_cycles` difference is the honest tool.
Source: [docs/raster-timing.md](https://github.com/kieranhj/paradroid-beeb/blob/main/docs/raster-timing.md) "A trap in DEBUG_TIME".

**A two-byte counter read one byte at a time can roll between the bytes. Reject a sample that
goes backwards.**
Instance: Edge Grinder's frame meter stored a rolled T2 read as a ~65,000 us maximum and poisoned
the slot for the run; three readings out of three were junk. A frame over 65.5 ms (deaths, mode
changes - one measured at 234 fields) wraps the counter outright. And a phase maximum includes
any interrupt that landed inside it: `read_joystick`'s maximum read 3,632 cycles against a true
cost near 644, the difference being one music interrupt. Take worst cases from maxima and typical
costs from a single-frame sample.
Source: [docs/performance.md](https://github.com/kieranhj/edge-beeb/blob/master/docs/performance.md),
[src/timing.asm](https://github.com/kieranhj/edge-beeb/blob/master/src/timing.asm).

**Compare like with like: not maxima, and not the same frame number in builds of different speed.**
Instance: comparing phase maxima showed the scroll change saving 214 cycles and nearly hid a
1,690-cycle win. Comparing screen bytes at the same frame number put the faster build four frames
further through the map, because the pre-wind was shorter (190 fields against 197). Stepped to an
equal `char_col`, the buffers were byte-identical.
Source: [docs/performance.md](https://github.com/kieranhj/edge-beeb/blob/master/docs/performance.md).

**A corrupt instrument looks exactly like a game bug. Verify the stub bytes first.**
Instance: a hand-assembled branch in Paradroid's audit stub was two bytes short and executed
`JSR &6001` from the middle of an instruction. Black screen, `BRK` loop in the MOS, `fieldCount`
frozen: it wrecked two sessions, and a lift ride was blamed for the hang before the stub was
checked.
Source: [docs/perf-audit-2026-08-31.md](https://github.com/kieranhj/paradroid-beeb/blob/main/docs/perf-audit-2026-08-31.md).

**Position counters are not evidence about motion. Sample what the display latched.**
Instance: KC reported Paradroid's briefing scroller "a little bit jerky" on real hardware. The rate
was exactly right - 100 scanlines in 100 fields. Sampling what fire 1 actually latched showed
field 137 repeating 136 and 139 landing two scanlines on: a stall and a double step once a
character row. `iline`, the latched copy, is the truth.
Source: [docs/layer-11f-frontend.md](https://github.com/kieranhj/paradroid-beeb/blob/main/docs/layer-11f-frontend.md).

**Quiesce what you think you have quiesced, and prove it.**
Instance: zeroing `sprActive` for an oracle run was not enough in Paradroid: `DrScreen`
re-activates a droid's slot from `drSlotOwner` every pass, so the droids came straight back and
their sprites showed as 122 bytes of "corruption". `drCount = 1` as well, or NOP the draw sites.
Source: [BUGS.md #9](https://github.com/kieranhj/paradroid-beeb/blob/main/BUGS.md).

---

## 6. Emulator configuration hiding bugs

**A bug that only shows up off the development machine is the one your emulator's configuration
is hiding. Test the relocated case.**
Instance: Paradroid's intro kept the sideways-bank handover at `&0A00`, which is inside the
advance tables it unpacks (`advance_tables_len` x 256, not x 64, so `&0400-&1BFF`). The handover
was overwritten, the magic byte missed, and the game fell back to banks 4-7. On jsbeeb and the
development desk, which have 4-7, the fallback was right by coincidence. On KC's emulator, with
sideways RAM in 0-3, every `*LOAD` appeared to succeed and the first call into bank code crashed.
Cost: the very layer that had made the bank numbers a run-time answer was followed by the first
thing built on it depending on 4-7 again.
Source: [docs/intro.md](https://github.com/kieranhj/paradroid-beeb/blob/main/docs/intro.md) "The trap: &0A00".

**jsbeeb powers up with RAM zeroed. Real hardware does not, and a byte survives BREAK.**
Instance: `disrFlash` (class 3) was 0 on every emulated boot. Reproduced by seeding it before a
SHIFT+BREAK autoboot - the byte survives BREAK, which is exactly the real-hardware case. Three
times in two days.
Source: [docs/layer-11f-frontend.md](https://github.com/kieranhj/paradroid-beeb/blob/main/docs/layer-11f-frontend.md),
[docs/intro.md](https://github.com/kieranhj/paradroid-beeb/blob/main/docs/intro.md).

**An absolute that was never true, and stayed in the rules for a month: "pad an SSD to 200K or
the emulator will not boot it".**
Instance: Paradroid's Layer 4 notes record jsbeeb hanging in the DFS FDC poll at `&ACAE` loading
`PARASPR` from an image that ended mid-track; it reproduced from BASIC with `*LOAD`, so it was not
the game, and it cost an hour. The conclusion drawn - pad every image before booting it - became a
rule in two projects' `CLAUDE.md`. KC corrected it on 2026-09-01 (jsbeeb *will* boot an unpadded
image), and on 2026-09-07 jsbeeb's author supplied what the rule had been standing in for all
along: jsbeeb stopped complaining in **1.9.0**, and **jsbeeb-mcp 3.0.0** is the first release
whose declared dependency guarantees it. The kit stopped padding for emulators that day, having
booted an unpadded image on both models through the MCP first.
**Padding survives as a PUBLISHING convention only**: a published size that differs from the last
publish is a useful signal that the wrong file went out. The shape of the mistake is the thing to
learn - one debugging session's workaround, promoted to a rule, outliving the bug by a year and
costing every project a build artefact nobody needed.
Source: [docs/layer-4-player.md](https://github.com/kieranhj/paradroid-beeb/blob/main/docs/layer-4-player.md),
[CLAUDE.md](https://github.com/kieranhj/paradroid-beeb/blob/main/CLAUDE.md).

**Nothing displayed may live below `&3000` on a Master with shadow RAM. Emulators disagree there.**
Instance: Edge Grinder's panel at `&2000` displayed correctly in jsbeeb under both shadow states;
b-em showed garbage on alternate frames. What the video fetches below `&3000` with the D bit set is
emulator-dependent and was not verified on hardware. The panel moved to `&3000` and is drawn into
both banks. Likewise the mid-frame display-bank switch the titles rely on is measured in jsbeeb
only, and the docs say so.
Source: [docs/decisions.md row 17](https://github.com/kieranhj/edge-beeb/blob/master/docs/decisions.md),
[CLAUDE.md](https://github.com/kieranhj/edge-beeb/blob/master/CLAUDE.md).

**A field can be the right length and still in the wrong place. Field-length instruments cannot
see a misplaced field; a second emulator or a TV can.**
Instance: Paradroid's rupture handover was tuned in jsbeeb until every field read 39,93x cycles.
KC photographed b2 rolling. A CRTC left free-running in the tail's shape VSyncs every 104 lines, so
the aligned write produced a first VSync at line 104 instead of 312 - one short field, invisible to
the frame-length count. `ruptalign.asm` now suppresses VSync across the intermediate cycles.
Source: [docs/raster-timing.md](https://github.com/kieranhj/paradroid-beeb/blob/main/docs/raster-timing.md) "Round three".

**Judge motion and sync on a display, and say when you have not.**
*Not confirmed as a verbatim rule in either repository.* What is recorded: Edge Grinder's decision
22 (sprites do not take the scroll's bank phase) was marked "unconfirmed on a display" until a
stationary ship was observed steady; Paradroid's scroll notes say a transition "wants the emulator
and then real hardware, since a TV's tolerance is the thing being tuned"; KC judged one rupture
alignment worse by eye and it was reverted; and both the jerky scroller above and the b2 roll were
found on hardware after the emulator numbers said fine.
Source: [docs/decisions.md row 22](https://github.com/kieranhj/edge-beeb/blob/master/docs/decisions.md),
[docs/layer-3-scroll.md](https://github.com/kieranhj/paradroid-beeb/blob/main/docs/layer-3-scroll.md),
[docs/raster-timing.md](https://github.com/kieranhj/paradroid-beeb/blob/main/docs/raster-timing.md).

---

## 7. Ordering and register discipline in transcribed code

**Know which register a run of transcribed code keeps live, and count in the other one.**
Instance: Edge Grinder's scroll tail keeps `char_col + 1` in X from the increment at the top,
through the `AND 3` and `AND 1` tests, down to the `corner_addr` update. `tile_cnt_bump` counts in
Y precisely so it can sit in the middle of that. `coll_advance`, added beside it, counted in X, and
`crtc_addr` and `corner_addr` advanced on the wrong frames: "scrolling is very broken", plus a
vertical smear that looked like a sprite fault and was the column copy landing in the wrong place.
Source: [BUGS.md #5](https://github.com/kieranhj/edge-beeb/blob/master/BUGS.md).

**Port the whole of a reset routine, including the part that does not look like a reset.**
Instance: the C64's `map_read_rst` ends in what its author labels a "scroll fast winder for the
start of game" - the buffer-swap cycle run 20 times, a whole screen. Edge Grinder reset the pointer
and started playing. The playfield opened empty, and because the wave table's timings are authored
against a full screen, every wave spawned a screen ahead of the scenery it was drawn to fly
through.
Source: [BUGS.md #6](https://github.com/kieranhj/edge-beeb/blob/master/BUGS.md).

**Keep the original's loop order. Advance after the draw, not before.**
Instance: factoring the scroll into one routine for the winder put the advance inside the plot, so
sprites were placed from an already-advanced `corner_addr`. On odd frames the advance moves
`corner_addr` and not `crtc_addr`, so a stationary sprite landed one byte column further right,
alternating every frame in step with the scroll.
Source: [BUGS.md #7](https://github.com/kieranhj/edge-beeb/blob/master/BUGS.md).

**Follow a value through every routine that touches it before you transcribe the one that reads it.**
Instance: Paradroid's `AddBullet` shifts `deltaX`/`deltaY` down five. They look like the raw
droid-to-player offset and are not: `CalcDeltaAdd` has already normalised the pair so the longer
sits in 128-255. The port used the raw pixel offset, so bullet speed was proportional to distance,
and a droid fires at two characters' range - speed 0 or 1. Hence "the lasers crawl" and "I can walk
through them". Two more details were load-bearing: the shift is logical, and both speeds are
negated.
Source: [BUGS.md #11](https://github.com/kieranhj/paradroid-beeb/blob/main/BUGS.md).

**A guard that lives inside the callee in the original must live inside it in the port.**
Instance: `ReverseDroidDir` carries its debounce inside itself, and both C64 call sites reach it.
Paradroid's version left the guard out on a note that both callers had already tested; only one
had. Two overlapping droids reversed every pass and locked permanently. The other half: the latch
is cleared only on a pass with no collision at all, not at the top of every pass.
Source: [BUGS.md #7a](https://github.com/kieranhj/paradroid-beeb/blob/main/BUGS.md).

**CRTC shape registers change in the interrupt that owns the timing, at VSync, never from the
main loop "wherever the raster happens to be".**
Instance, twice: Paradroid's `SetupRupture` wrote R4 = 12 from the main loop, and the row counter
is usually already past 12, so the 6845 ran on to its wrap: fields of 300, 384 and 48 lines at
every handover. Edge Grinder's `title_page` writes R7 from the main loop and the VSync handler
schedules the T1 fires from `ttl_active`; one 272-line field at every titles switch (34,817 cycles
against 39,936), and two placements inside the apparent window were both worse. The diagnosis in
both: registers and schedule must change together, in `rupt_vsync`.
Source: [docs/raster-timing.md](https://github.com/kieranhj/paradroid-beeb/blob/main/docs/raster-timing.md),
[BUGS.md #14](https://github.com/kieranhj/edge-beeb/blob/master/BUGS.md) (open).

**Any teleport must go through the reframe.**
Instance: Paradroid's `COPYCHAR` writes a character's two halves in one 16-byte run, which is only
safe while `scrollS/8` and `mapHX` agree in parity. Respawning after a droid's shot assigned
`mapHX` outright without touching `scrollS`, the parity flipped, and the band draw wrote 8 bytes
past `&8000` into bank 4's charset source - re-read at every deck load, so the corruption survived
a deck hop. `DEBUG_MAPGUARD`, built for the wrong hypothesis (the tile map), read zero throughout,
and that zero is what pointed at the bank.
Source: [BUGS.md #10](https://github.com/kieranhj/paradroid-beeb/blob/main/BUGS.md).

---

## 8. Bank paging rules

**Nothing may page its own bank out from under itself.**
Instance: Paradroid's `DrAddBullet`, in bank 4, wanted one byte from bank 5 and did `PAGEBANK
SWRAM_SPR` while executing from `&8000`. The next instruction fetch came out of the blitter; it
crashed instantly at `PC = &B3C9` with a ROM paged in. Fix: a four-line lookup in main RAM.
Source: [docs/layer-7-combat.md](https://github.com/kieranhj/paradroid-beeb/blob/main/docs/layer-7-combat.md).

**Bank code may call main RAM; main RAM may page freely; a bank that is not the resting state
needs a trampoline.** Paradroid's `bufcore.asm` states it as a one-way rule; Edge Grinder's is
"bank 0 code may call into main RAM; bank 3 code may not", because the sprite engine pages banks 5,
6 and 7 as it needs them and puts the data bank back, so a bank 0 routine is still there when a
main-RAM call returns and a bank 3 one is not. The depacker follows the same rule: only one bank is
visible, so a copy in bank 4 cannot unpack into bank 5 - there is one depacker and it is resident.
Source: [CLAUDE.md](https://github.com/kieranhj/edge-beeb/blob/master/CLAUDE.md),
[CLAUDE.md](https://github.com/kieranhj/paradroid-beeb/blob/main/CLAUDE.md),
[docs/layer-11f-frontend.md](https://github.com/kieranhj/paradroid-beeb/blob/main/docs/layer-11f-frontend.md).

**The IRQ reads no bank unless it pages explicitly, saving and restoring what it found, and
writes the ROMSEL shadow first.** Paradroid's one exception is the 50 Hz sound tick, which saves
`ROMSHAD`, pages the data bank around `SndTick` and restores it - legal because `PAGEBANK` writes
the shadow before the latch. "Check that again before putting anything else in one." Edge
Grinder's music player runs from the VSync handler and reads eleven streams spread over four
regions, each with its own ROMSEL byte in the map it mounts from.
Source: [CLAUDE.md](https://github.com/kieranhj/paradroid-beeb/blob/main/CLAUDE.md),
[docs/layer-11e-sound.md](https://github.com/kieranhj/paradroid-beeb/blob/main/docs/layer-11e-sound.md),
[lib/vgiplayer.asm](https://github.com/kieranhj/edge-beeb/blob/master/lib/vgiplayer.asm).

**A write that runs past `&8000` lands in whichever bank is paged, and you will find out at the
next load.** Paradroid #10 above, and #18, where a runaway print walked out of the play buffer into
bank 7.

**The workspace you have taken from the filing system must be taken last, and BREAK must then
be a power-on reset.**
Instance: Edge Grinder's music lives in HAZEL (`&C000-&DFFF`), the filing system's own workspace,
so `MUSIC` is loaded last and nothing touches the disc after it; a soft BREAK leaves the wreckage
in place - measured: no DFS banner, `*CAT` returns nothing - so `OSBYTE 200, 3` makes BREAK a
power-on reset. That is the whole 8K, DFS's own pages included. Keep to `&C300-&DEFF` and DFS and
a soft BREAK both survive, within the limits in hardware-facts' HAZEL section. Paradroid's low
overlay at `&0E00-&10FF` is DFS's shared workspace and is copied down by the last filing-system
call; do it earlier and the next `*LOAD` hangs in the 8271 poll.
Source: [CLAUDE.md](https://github.com/kieranhj/edge-beeb/blob/master/CLAUDE.md),
[docs/memory-map.md](https://github.com/kieranhj/paradroid-beeb/blob/main/docs/memory-map.md).

---

## 9. The chip is not a frame buffer

**"Write the wrong value and then correct it" is not free on a device that is listening between
the two writes.**
Instance: Edge Grinder's mute ran the music player as usual and then `sn_reset`. A sound capture
showed channel 2 at attenuation 9 for 246 cycles - 123 us - before the reset took it off, fifty
times a second. Fifty edges a second is a 50 Hz buzz that rides the tune. No ordering closes the
window while the player still writes volumes, so muted, `sn_reset` runs *instead of* the player.
Verified by capturing every SN76489 write across ten muted fields: forty writes, all attenuation 15.
Cost: shipped and fixed the same day, on jsbeeb and b2 alike.
Source: [BUGS.md #11](https://github.com/kieranhj/edge-beeb/blob/master/BUGS.md).

**The MOS is listening too, if you ever hand the machine back.** Paradroid builds its charset over
`&0800-&08FF`, the MOS's sound queues and envelopes - safe only while the game owns IRQ1V. Any path
that returns to the MOS must flush the buffers first (`OSBYTE &0F, X=0`) or the MOS plays the
charset as notes. And R7 must not sit at the tail's VSync row while a filing-system call runs:
Paradroid hung in the 8271 poll that way. Stopping VSync no longer reproduces it on
jsbeeb 1.25.0 (hardware-facts section 6), so the shape, not the missing VSync, may be
what did it - keep the display out of the way of a load either way.
Source: [CLAUDE.md](https://github.com/kieranhj/paradroid-beeb/blob/main/CLAUDE.md),
[docs/layer-3-scroll.md](https://github.com/kieranhj/paradroid-beeb/blob/main/docs/layer-3-scroll.md).

---

## 10. Measured optimisations that lost

**A self-modified base address is an argument against unrolling, not a detail beside it. Count
the patches, and multiply them by the unrolled copies.**
Instance: Edge Grinder's performance page first proposed unrolling the scroll's three inner loops
for ~2,700 cycles. Two of them index off base addresses rewritten every character row; unrolling by
eight multiplies the addresses to patch from two per row to sixteen, about 64 cycles a row against
a saving of 24. Both net losses. The third loop had no patched base and did not want unrolling: it
wanted deleting, folded into the copy that already walked the same bytes. Predicted -1,692 cycles,
measured -1,690, and the code got 11 bytes smaller.
Source: [docs/performance.md](https://github.com/kieranhj/edge-beeb/blob/master/docs/performance.md).

**An addressing change is only cheap when the thing that varies can live in the index.**
Instance: "address the sprite save area absolutely, one patched byte per slot" was costed at
2,000-2,800 cycles a frame. The pointer changes every scanline, and there are seven store sites in
the ladder: 31 cycles of patching a scanline to save at most seven. About -500 cycles a sprite, a
factor of four the wrong way. Rejected after KC asked whether the self-modification cost more than
it saved.
Source: [docs/performance.md](https://github.com/kieranhj/edge-beeb/blob/master/docs/performance.md).

**Write the rejected ones down with their cost, so they are not re-litigated.** Paradroid's RAM
pass records: rolling the blitter's unrolls, +8,000-10,700 cycles a pass for 0.1-2.3K; computing
`palPanel`, +640 cycles inside the IRQ; the three `ALIGN`s recover nothing, by geometry.
Source: [docs/ram-pass.md](https://github.com/kieranhj/paradroid-beeb/blob/main/docs/ram-pass.md) "Costed and rejected".

**Measure how often the expensive path is actually taken before you speed it up.**
Instance: Edge Grinder's engine sent a sprite down a 97-cycle-a-byte walked path whenever
`bufp + 1968` crossed the buffer end. A row straddles only if its own seven columns do, a reach of
55 bytes: the test flagged 12% of sprites where about 1.4% really straddle. Made exact, then the
walked path was deleted outright, the one straddling character row drawn as two ordinary ladder
calls. Six straddling explosions: 127,368 cycles a frame to 85,326.
Source: [BUGS.md #9](https://github.com/kieranhj/edge-beeb/blob/master/BUGS.md).

---

## 11. Two correct measurements supporting a wrong conclusion

**Vary the variable that matters. Two sound measurements of the wrong variable will agree with
each other and with the wrong theory.**
Instance: Paradroid's rotor debris "survived freezing the rotor phase" - true, and irrelevant, the
fault being in the row walk - and "a single sprite is clean, 0 of 10240" - true at the position
tested, which had no row crossing the wrap. Sprite count was never the variable; scroll offset was.
`DEBUG_POS` now prints `scrollS` so that the variable that does matter is visible.
Source: [BUGS.md #6](https://github.com/kieranhj/paradroid-beeb/blob/main/BUGS.md).

**A measurement taken on a build with a hidden bug measures the bug.**
Instance: Edge Grinder's decision 19 deferred compiled sprites because eight interpreted sprites
measured 49,236 of 79,872 cycles. That figure was taken while #8 was skipping every sprite past
x = 140. When the frame was measured properly the budget table was optimistic by about 45%, and
the game dropped below 25 Hz while shooting. The decision row now says "the premise is now in
doubt" rather than being silently edited.
Source: [docs/decisions.md row 19](https://github.com/kieranhj/edge-beeb/blob/master/docs/decisions.md),
[BUGS.md #9](https://github.com/kieranhj/edge-beeb/blob/master/BUGS.md).

**A guard that reads zero is a result. Believe it.** Paradroid's `DEBUG_MAPGUARD` reported no
writes to the tile map through a live reproduction of the corruption, and the working document is
still named for the hypothesis it disproved. The zero moved the search to the bank.
Source: [BUGS.md #10](https://github.com/kieranhj/paradroid-beeb/blob/main/BUGS.md).

---

## 12. Docs that lie

**A free-byte figure is stale the build after it was written. Take live numbers from the listing.**
Instances: Paradroid's `CLAUDE.md` quoted bank 5 at 119 bytes free and it was 6, "stale by a
build"; the memory map quoted 36 free in `lowcode2` and it was 6; the RAM pass found the "&8A80
gap" a memory-map entry claimed does not exist; the debug bookmark's non-zero-page addresses were
all stale when checked (the door variables by `&63A`, `tilemap` from `&3800` to `&4600`); and #18's
numbers moved from 96 bytes and an 8-byte gap to 48 and ~49 within a week. Edge Grinder's memory
map opens by saying its figures "go stale the moment anything grows", and #13 records the build's
FREE line overstating the room for anything permanent by measuring to the wrong ceiling.
Source: [CLAUDE.md](https://github.com/kieranhj/paradroid-beeb/blob/main/CLAUDE.md),
[docs/memory-map.md](https://github.com/kieranhj/paradroid-beeb/blob/main/docs/memory-map.md),
[docs/ram-pass.md](https://github.com/kieranhj/paradroid-beeb/blob/main/docs/ram-pass.md),
[BUGS.md #18 and "Delivered: DEBUG_POS"](https://github.com/kieranhj/paradroid-beeb/blob/main/BUGS.md),
[docs/memory-map.md](https://github.com/kieranhj/edge-beeb/blob/master/docs/memory-map.md).

**"Copied unaltered" is a claim about two files, and it wants a diff.**
Instance: Edge Grinder's `CLAUDE.md` says in two places that `lib/vgiplayer.asm` is copied from
vgm-player-bbc unaltered, and `docs/performance.md` borrows that library's measured cost on the
same grounds. The file carries a `VGI_SPLIT` build flag the upstream has not got, added for
decision 48 so the eleven streams can live in four regions; the upstream meanwhile has a `VGI_V3`
flag this copy has not. *Measured for this document*: `diff` between the two reports about 250
changed lines. The `VGI_SPLIT=0` path is described as byte-identical to the original, which may
well be true of the assembled bytes - it is the "unaltered" that is false.
Source: [CLAUDE.md](https://github.com/kieranhj/edge-beeb/blob/master/CLAUDE.md),
[lib/vgiplayer.asm](https://github.com/kieranhj/edge-beeb/blob/master/lib/vgiplayer.asm),
[docs/performance.md](https://github.com/kieranhj/edge-beeb/blob/master/docs/performance.md).

**A copy of a copy carries the first project's comments into the second.**
Instances, both *measured for this document*: Edge Grinder's `tools/zx0.py` is byte-identical to
Paradroid's and its docstring still says "Used by export_bbc.py to compress the sixteen deck maps
into bank 4" - there is no `export_bbc.py` and no deck map in Edge Grinder. `tools/akl/akl_reference.py`
has since been forked the other way, into the arkos-player-bbc library, and the two have drifted:
the library's copy carries `ENV_BASE = 8` with a "THIS MUST MATCH THE PLAYER'S" warning, a bounds
check that raises on a read outside the song, a 257-hop limit on the loop walk and a `& 0xFF` mask
the Z80 implies; Edge Grinder's has `ENV_BASE = 12` and none of those. Edge Grinder's own
`docs/layer-7-music-arkos.md` and `tools/akl/README.md` still name `src/aklplayer.asm`, which is
`lib/aklplayer.asm` now.
Source: [tools/zx0.py](https://github.com/kieranhj/edge-beeb/blob/master/tools/zx0.py),
[tools/akl/akl_reference.py](https://github.com/kieranhj/edge-beeb/blob/master/tools/akl/akl_reference.py),
[docs/layer-7-music-arkos.md](https://github.com/kieranhj/edge-beeb/blob/master/docs/layer-7-music-arkos.md).

**Correct a document in place and say what it used to say.** Both ports do this and it is why the
trail is readable: Paradroid's blitter document keeps its 184-scanline paragraph under a "CORRECTED"
banner; its `CLAUDE.md` records that the unpadded-SSD rule was once an absolute and who softened
it; Edge Grinder's `CLAUDE.md` has a whole section headed "Facts about the current code that the
old docs got wrong", and its #9 entry says on its face that its "no missed flips" line is out of
date (7 in 2,000 frames by the next measurement).
Source: [docs/layer-5-blitter.md](https://github.com/kieranhj/paradroid-beeb/blob/main/docs/layer-5-blitter.md),
[CLAUDE.md](https://github.com/kieranhj/edge-beeb/blob/master/CLAUDE.md),
[docs/performance.md](https://github.com/kieranhj/edge-beeb/blob/master/docs/performance.md).

---

## Checklist before you say a layer is done

1. Every hardware number in the layer was measured in the emulator this week, not recalled or
   carried over from a document (classes 1, 2).
2. Every region has a `GUARD` or `ASSERT` at the ceiling that matters *in play*, not the one that
   matters at boot (class 3).
3. Nothing new was added to `SKIP`ped storage without a check that it is written before the first
   path that reads it - the front end and the IRQ included (classes 3, 6).
4. Every path the layer added has been driven at least once, on purpose, by forcing the branch if
   the game does not reach it (class 4).
5. The oracle, harness or diff was re-read for paths that did not exist when it was written, and
   its inputs cover odd and even, both axes, a second deck (class 4).
6. Every instrument used to produce a number was itself checked: patch applied, bracket closed,
   wrap impossible, interrupts accounted for (class 5).
7. The build was booted with RAM seeded non-zero, sideways RAM in a different set of slots, on a
   second emulator, and where a display is being tuned, on a display (class 6).
8. A transcribed routine was compared with the original for register use, call order and the
   guards inside its callees, and every value it reads was followed back to its writer (class 7).
9. No bank routine pages its own bank; nothing in the IRQ reads a bank without paging explicitly;
   nothing crosses `&8000` (class 8).
10. Anything that writes to a chip was captured at the chip, not inferred from the code (class 9).
11. Every optimisation has a predicted and a measured figure, single-frame, like against like, and
    the ones that lost are written down with their cost (classes 10, 11).
12. Every free-byte figure, "unaltered" claim and file path in the docs was re-measured before it
    was left standing, and a corrected document says what it used to say (class 12).
