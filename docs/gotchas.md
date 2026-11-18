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

Many entries also draw on **[1942](https://github.com/kieranhj/1942-beeb)** (Master 128,
September-October 2026), the third port, the first built with this kit and the first from an
arcade original; its `BUGS.md` numbers are cited as they stand there. Later entries draw on
**[Stryker's Run](https://github.com/kieranhj/strykers-run)** (Master 128 and Model B, October
2026), not a port but a BBC original rebuilt byte for byte from a disassembly and then optimised;
its bugs are the ones that come from changing a working game you did not write. The latest
entries draw on two **Amstrad CPC demos** (Isometrikum and Square Roots, November 2026; the
repositories are not public, so they are cited by path): a Z80 original with no source, and the
second port built overnight from the first (`docs/cpc-demo-porting.md`). The newest draw on
**phX** (a CPC demo ported to the Master 128, November 2026; not public, cited by path as
`phX/...`): multi-part, multi-load and cycle-exact, with the original's own source available,
a home-made reference CPC, WinAPE as a third opinion, two jsbeeb versions and KC's two real
Masters in the loop.

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


**Choose the reference by its bytes, and test what the annotations assume.**
Instance: Stryker's Run had two discs of the same release. Disc999's game had seven scenery bytes
zeroed that no code writes, and a different CRTC R8; the Stairway to Hell disc matched the
disassembly's tables, so it became the reference. The disassembly itself said the mountain layer
read the MOS ROM at `&C300`; a watch showed it reads HAZEL (on a Master the MOS leaves HAZEL paged),
and a brief built on the annotation had called a change "not doable" for a reason that was false.
Source: [strykers-run decision 1](https://github.com/kieranhj/strykers-run/blob/main/docs/decisions.md), [strykers-run BUGS.md #9](https://github.com/kieranhj/strykers-run/blob/main/BUGS.md).

**A reading of the original taken from pictures is a hypothesis, and so is a brief's.**
Instance: Square Roots' overnight brief, written from `cpcrun` frames, predicted "a palette fade,
the hard design question". The palette is written once at boot; the "fade" is 13 tile sets. The
brief's own rule - "verify before relying on it" - is what saved the night. Search the code for
what the picture suggests (every `OUT &7Fxx`: pens or RAM banks?) before designing for it.
Source: square-roots `docs/layer-7-colour.md` (CPC demo, 2026-11-08; not public).

**The home-made reference is an oracle too: it can be wrong, and the port copies it faithfully.**
Instance: phX's Python CPC showed the outro's three scanlines in the order (2, 0, 1), plus a
frame-restart "quirk" (a dark line through the text); the BBC reproduced both, 4,444 fields
checked identical, and KC saw the line on jsbeeb while his WinAPE screenshots were clean. The
demo's own source says routine k shows scanline k; WinAPE (CRTC type 0) agreed (decision 63, BUGS
8). The same review found the logo one row taller than the CPC's (BUGS 10) and every mid-line
Gate Array write half a microsecond early in the reference's video model (BUGS 11: 394 pixels over
25 captures, all one way). Each was invisible to the port's harnesses because every expected
picture was the reference's. Rule: **check the reference against a third-party emulator and,
where it exists, the original's source**, part by part, before the port's checks rest on it.
Source: `phX/docs/decisions.md` 63, `phX/BUGS.md` #8, #10, #11 (2026-11-17).

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

**An index that fits today wraps tomorrow: put `ASSERT count * stride <= 256` beside every
indexed table.** Instance: 1942's sprite records outgrew an 8-bit index at the busiest waves only,
393 clean ticks into a run. Source: [1942-beeb BUGS.md #6](https://github.com/kieranhj/1942-beeb/blob/master/BUGS.md).

**`&FFFF` is a bad self-modifying placeholder.** Indexed through `,X` or `,Y` it wraps into zero
page, so a routine whose operand was never patched writes the zero page and the machine hangs far
from the cause. Use an address that faults visibly, or ASSERT the patch site was written.
Source: [1942-beeb BUGS.md #5](https://github.com/kieranhj/1942-beeb/blob/master/BUGS.md).

**Three shifts left lose the ninth bit.** `asl` x3 on a glyph index is right below 32 and wrong
from 32 up; `lsr` on the high byte of a signed 16-bit value turns -1 into +32767, so a sprite at
play X -1..-4 was never drawn (for a month - nothing drove one there). A coordinate's high byte can
take three values (-1, 0, 1), not two. Source: [1942-beeb BUGS.md #23, #84, #7](https://github.com/kieranhj/1942-beeb/blob/master/BUGS.md).

**A branch after `sta` tests the PREVIOUS instruction's flags.** `sta` sets nothing; a `bpl`
written as if it tested the stored value tested the load two instructions up. Source: [1942-beeb BUGS.md #54](https://github.com/kieranhj/1942-beeb/blob/master/BUGS.md).

**Derive a threshold from the width it guards.** A wrap test written as a literal for a 5-column
blit survived the blit growing to 9 columns, and the escaping writes landed in the paged bank,
where the strip oracle could not see them. Source: [1942-beeb BUGS.md #31](https://github.com/kieranhj/1942-beeb/blob/master/BUGS.md).

**Baron's `NOT` is bitwise.** `IF NOT(RELEASE)` is true for `RELEASE = 1` (NOT 1 = -2, non-zero),
and a release disc shipped the debug keys. Write `IF RELEASE = 0`. Source: [1942-beeb BUGS.md #40](https://github.com/kieranhj/1942-beeb/blob/master/BUGS.md).

**Baron's `AND` is bitwise too, `FOR 1..0` runs twice, and a `SECTION` cannot span two `IF`s.**
`IF HW AND PART = 0` parses as `HW AND (PART = 0)`, a bitwise AND: write `HW <> 0 AND PART = 0`.
A `FOR` whose range may be empty counts down instead and runs twice; guard it with an `IF` (the
same trap note records phX's `WAIT 3` macro giving 7 cycles until it was fixed, with an `ASSERT`
that n is 0 or at least 2). And a `SECTION` cannot open inside one `IF` and close inside another:
wrap the whole file.
Source: `phX/CLAUDE.md` Traps, `phX/docs/hwtest.md` "Traps found on the way" (2026-11-14 to 11-16).

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

**A guard belongs at the first address SOMEONE ELSE writes, and the OS counts as someone else.**
Instance: 1942's code guard sat at its next variable, but `VDU 22` erases `&3000-&7FFF` after
`*RUN` loads the image and before it runs, so code past `&3000` was gone before it executed - the
disc stopped booting with no diagnostic, because the diagnostic had been erased too. Source: [1942-beeb BUGS.md #17](https://github.com/kieranhj/1942-beeb/blob/master/BUGS.md).

**A map of what the OS leaves is not a map of what is free: read what the PORT already put
there.** Instance: ANDY was measured free of the MOS, a 116-byte routine moved into it, and its
first `jsr` ran into the port's own text tables (a generated lookup table whose first byte is
`&00`: BRK, BASIC paged in, "Mistake"). Source: [1942-beeb BUGS.md #24, #29](https://github.com/kieranhj/1942-beeb/blob/master/BUGS.md).

**Bound a run-time fill at run time, and refuse rather than overrun.** 1942's save-under store and
object buffer both ran into the next region under loads no test had reached; the fix was a refusal
in the emitter (a sprite dropped for a tick), not a bigger assert, because the worst case is a
property of play, not of the build. A buffer sized by a count written out by hand (4 entries, not
`TEXT_SLOTS`) did the same on stage 28 only. Source: [1942-beeb BUGS.md #30, #52, #90](https://github.com/kieranhj/1942-beeb/blob/master/BUGS.md).

**A figure must say what its run covered.** A save-store peak of 798 bytes, measured on one stage
with no fire held - nothing died, no explosion was ever drawn - sized a reservation, and stage 28
then wrote 516 bytes into game state; 36 oracle runs failed at once while every boss-facing oracle
passed. Source: [1942-beeb BUGS.md #48, #52](https://github.com/kieranhj/1942-beeb/blob/master/BUGS.md).


**Assert the end of every region, not just the code's.**
Instance: Stryker's Run's bank 4 holds the renderer, then its sprites, then its workspace. The
ASSERT guarded the renderer's own end; the sprite data after it grew past `&B000` into the
workspace the renderer writes as it draws, and the last 230-300 bytes of sprites drew as garbage.
Found only because two builds that should have agreed parted at pass 4,139 of a 5,000-pass screen
lockstep. Source: [strykers-run BUGS.md #6](https://github.com/kieranhj/strykers-run/blob/main/BUGS.md).

**Under Baron's allocator, a routine reachable from an interrupt handler and from the main loop
shares zero page with the interrupt's own variables.** Baron assumes code reachable from a
`ZA_INTERRUPT` handler runs only inside it, so it may pack that handler's variables onto the
routine's. Instance: Square Roots' screen routines were reachable from a raster fire and from the
main loop; the allocator put the music interrupt's `mus_c`, `mus_a`, `mus_b` on the span's `so`,
`sl`, `sn`, the music preempted a span, and the first full run failed at record 207. Rule: never
share a routine between an interrupt and the main loop; give the interrupt its own copy with its
own variables, or move the work out of the interrupt.
Source: square-roots `docs/layer-5-world.md` "Found by measurement", commit f35d56f (2026-11-08).

**While a gate demands an identical image, pin the zero page.** Removing one unrelated variable
lets Baron's allocator repack the rest, and every operand that names one moves. Isometrikum's
crunch rounds 1-3 pinned the allocation to the reference build's.
Source: isometrikum `docs/crunch.md` (2026-11-08; not public).

**The OS's hooks in low RAM are regions too, and a program that copies over page 2 can take one.**
Instance: phX arms the MOS's BREAK intercept (the `JMP` at `&0287-&0289`, `*FX 247-249`) so every
BREAK reboots as from power-on. One of its overlays, copied into page 2 196 fields into the run,
overwrote the `JMP`; every later BREAK was a soft one into the demo's workspace, and on KC's
Master the DFS could not be selected afterwards. 1942 met the same three bytes with two variables
(its BUGS #92). Lay every page-2 overlay around them, and check with a PLAIN BREAK at many points
(SHIFT+BREAK reboots the disc either way, so phX's SHIFT+BREAK check passed throughout).
Source: `phX/docs/decisions.md` 59 (2026-11-16).

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

**A library routine that has only ever been assembled is a path nothing has called.**
Instance: the kit's `loader.6502` generalised Edge's `unpack_andy` and wrote down that it took
its destination in X:A. Then it paged ANDY in through A and called `unpack_to`, which read A as
the destination's low byte: `ROMSHAD OR &80`. `test_lib.6502` assembled it from the first day. The
1942 port was the first thing ever to call it, and its in-play text code ran 135 bytes out of
place, with a `BRK` in a table. Measured afterwards in the kit on jsbeeb's Master: a stream meant
for `&8100` ended at `&81C9` with bank 9 paged. ANDY at `&8100` was untouched.
Rule: a lib routine gets a disc that runs it (`lib/test/andy_test.6502`) or a header that says
it has never run. The first port to call it should treat it as its own new code.
Source: [1942-beeb BUGS.md #21](https://github.com/kieranhj/1942-beeb/blob/master/BUGS.md), `lib/README.md` "Proving it runs".

**A debug shortcut measures a different game.** 1942's stage-skip key set a refill flag that
repaired exactly the corruption the real stage seam caused, and the stage oracle drove every seam
with that key; the boss key made its own swarm; a poke-to-stage route ran the wrong script. Drive
the REAL path in any oracle that claims it. Source: [1942-beeb BUGS.md #35, #36, #43, #54, #58](https://github.com/kieranhj/1942-beeb/blob/master/BUGS.md).

**A harness reads state back; it never echoes what it asked for.** 1942's stage oracle reported
`stage = STAGE + 1` from its own argument, and a 6-frame key tap that fell inside a masked disc
load vanished - so every run past the first boss scored an EARLIER stage than it named, for six
days. Hold the key until the state byte moves, and report the byte. Source: [1942-beeb BUGS.md #39](https://github.com/kieranhj/1942-beeb/blob/master/BUGS.md).

**A harness covers only what it drives, for as long as it runs.** 1942's sprite oracle pressed
SHIFT to boot and never another key: nothing ever died, no explosion or power-up was drawn, and the
load was half the real one. Holding fire found the bug at 6,000 ticks and not at 2,600. A settle
period hides the opening seconds; a suite on level 1 does not see level 28. Make the harness
REPORT its coverage and fail on a path it never took. Source: [1942-beeb BUGS.md #31, #11, #25, #90](https://github.com/kieranhj/1942-beeb/blob/master/BUGS.md).


**A watch proves only the paths it ran. Run every phase, deaths and game over included.**
Instance: Stryker's Run's new random number generator went at `&92`/`&93` on a watch that saw "no
access after boot in 30,000 frames". The original's death routine keeps the dying mover's slot in
`&92` across a call (`STY &92 : ... : LDY &92`), so every death set the generator's low byte; the
scripted runs had died, but not in the 30,000 frames watched. Found when the original and the
rebuild played the same game side by side and parted at pass 571. The replacement bytes were chosen
by a watch over the front end's checks, deaths, both helicopter flights and the whole world.
Source: [strykers-run BUGS.md #12](https://github.com/kieranhj/strykers-run/blob/main/BUGS.md).

**An optimiser that changes a routine's first bytes breaks every `JSR label+n` caller.**
Instance: Stryker's Run's micro-grind dropped `keydown_int`'s leading `TXA`; observer mode called
`JSR keydown_int + 1`, now into an operand, and no key worked there. Play, the front end and
define controls never take that path, so neither the proof gate nor the proposal's skeptics saw
it. Search for `label+` callers before changing an entry, and put every rarely-taken path in the
gate. Source: [strykers-run BUGS.md #11](https://github.com/kieranhj/strykers-run/blob/main/BUGS.md).

**Per-part oracles leave the fields between parts unchecked.**
Instance: phX's CPC fades the static Clown to white over 21 fields and holds it white before the
next part; the reference had it, WinAPE had it, and the BBC played only the earlier flash, holding
the full-colour Clown to the cut. One part's check ended at CPC field 3,497 and the next began at
3,971, so nothing compared the fields between; a source review found it. Rule: **lay the oracles'
windows end to end over the whole timeline and fail on a gap**, or give the hand-overs a check of
their own (phX's `verify_clown_end.mjs`, 530 of 530 after the fix).
Source: `phX/BUGS.md` #9 (2026-11-17).

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

**An oracle that shares the port's table, formula or substitute cannot see it be wrong.** 1942's
oracles agreed with the port ten times: every one scored zero against the same wrong sprite table
(a screenshot caught it), a model computed `base + heading` exactly as the port did and scored
697/697 on a broken stage, an exporter checked 8 anchor headings of 64, an oracle copied a palette
literal, another the port's entry timing, another the wrong award tick. **Prove every new oracle
FAILS on the unfixed build** - 1942's later fixes each record "verify_X fails the old build" - and
assert invariants taken from the original, not from the port. Source: [1942-beeb BUGS.md #16, #27, #34, #61, #69, #74, #91](https://github.com/kieranhj/1942-beeb/blob/master/BUGS.md).

**A well-formed answer of zeros is a failure.** An oracle returned a JSON object of zeros with exit
code 0 for weeks while its target was dead; another, with a hard-coded address, said 51 objects fit
a tick where 13 do. An instrument refuses to report zero samples. Source: [1942-beeb BUGS.md #9](https://github.com/kieranhj/1942-beeb/blob/master/BUGS.md).

**A moved label's breakpoint looks like a hang.** Hard-coded addresses in a harness go stale on the
next edit; the breakpoint never fires and the run times out "in the game". Resolve every address
from the build's symbol dump, and exit 2 on a missing name. Source: [1942-beeb BUGS.md #44, #81](https://github.com/kieranhj/1942-beeb/blob/master/BUGS.md).

**When every oracle fails at once, suspect the tools.** A new assembler release changed the
listing format and every parser threw; a jsbeeb major version changed `keyDown` from a number to a
string and every harness "never reached" its target. Both read exactly like a corrupt build.
Source: [1942-beeb BUGS.md #26](https://github.com/kieranhj/1942-beeb/blob/master/BUGS.md). (jsbeeb: `hardware-facts.md` §11.)

**A counting oracle is defeated by a variable that counts the same thing.** The kit's own
`verify_dynamic`, rebuilt to assert, still passes when handed the address of `flip_field` in place
of `field_count`: both advance 100 in 100 fields. Check a second property that only the right
variable has, or say in the oracle's header which wrong address it cannot catch.
Source: `template/tools/verify_dynamic.mjs`, 2026-10-25.

**Dump the machine on the way out.** PC, ROMSEL, ACCCON, the stack and the MOS error block at
`(&FD)` printed on a harness's exit settled in one run what three rounds of reading code had not.
Source: [1942-beeb BUGS.md #24, #29](https://github.com/kieranhj/1942-beeb/blob/master/BUGS.md).


**A Baron symbol dump has labels AND assignments; a loader that reads only labels compares nothing.**
Instance: Stryker's Run's renderer records (`rec_*`, `REN_BASE + n`) and every zero-page name are
assignments. `worldcheck` read only labels, so every address was `undefined`, both sides read the
same byte, and "6,119 records, none differing" proved nothing. A harness takes every address from
the dump, both kinds, and a missing name is an error. Source: [strykers-run BUGS.md #10](https://github.com/kieranhj/strykers-run/blob/main/BUGS.md).

**A top-level name and a scope's local label can share a name.** Stryker's Run's zero-page `lives`
(`&95`, an assignment) and two routines' local `.lives` labels: a symbol loader that also offers
the leaves of scopes refused `lives` as ambiguous. The exact top-level name wins.
Source: the kit's `harness.mjs`, 2026-10-25.

**Map one build's program counters to another's by every section that covers them, not by the
nearest label.** Matching a shifted build to its control by "the nearest label below the PC" gave
false divergences where main RAM is overlaid (a loader's code under the game) and where generated
code runs more than 512 bytes past its last label; and a hand-written shift map went stale when
one bank's padding changed direction (Stryker's Run's own `tracediff.mjs` on its current pair).
Derive the map from both symbol dumps. Source: the kit's `tracediff.mjs`, 2026-10-25.

**An interrupt entry with System VIA T1's flag up is not one MOS tick.** Counting the MOS's ticks
by IRQ entries with T1's flag set gave 3,192 entries for 1,176 ticks from BASIC, and double counts
300 cycles apart on a game disc: interrupts nest and re-enter. Place ticks on a grid at T1's period
(20,000 cycles). Source: the kit's `sfxcapture.mjs`, 2026-10-25.

**A breakpoint in sideways RAM must check ROMSEL.** Two of Stryker's Run's harnesses hooked a PC
in bank 7 and fired on bank 6's code at the same address: 30 false failures, and 0 ticks counted.
Source: strykers-run commits `1fd31bd`, `76bff0b`.

**Measure what the user sees, not when it was written.** Stryker's Run's HUD rupture was checked by
the beam position of every CRTC and ACCCON write, and the writes were right; but with ACCCON's D set
the video read ANDY below `&3000`, so the HUD flickered garbage on every shadow field (the
screenshots happened to be main-screen fields). The check now samples what the video reads at
every instruction while it displays. The same goes for a capture: a picture cropped from the
CRTC's registers is wrong under a rupture, which reprograms them mid-field, and a silent clip may
be a silent game - count the chip's writes before blaming the capture.
Source: [strykers-run BUGS.md #15](https://github.com/kieranhj/strykers-run/blob/main/BUGS.md).

**Sample a harness at the port's own tick, not at the emulator's frame.** Square Roots keeps the
CPC's 304-line frame, so its T1 drifts against jsbeeb's 312-line frames; `verify_music` read the
player's state mid-tick and differed every 39th tick, on channel 2 only. Hook the tick, or lock
the timer to the frame the harness counts.
Source: square-roots `docs/layer-2-music.md` "Found by measurement" (2026-11-08; not public).

**A record and a pass may be one apart, and the harness must say which.** Isometrikum's pass runs
after its field's music tick; the reference's record is taken before it. Its flash variables are
compared one pass back, by design, and the harness says so.
Source: isometrikum `docs/layer-5-world.md` (2026-11-07; not public).

**With code in two sideways banks at `&8000`, an address hook fires in both, and before boot it
fires in a ROM.** Isometrikum's hook at `plot_test_done` fired at the same address in the other
bank; on the Master a ROM was running at `main_loop`'s address before the boot paged the code
in, and the harness read a bank number that had not been written yet. Gate every address hook on
ROMSEL and on the boot having happened; read state with the bank named.
Source: isometrikum `docs/layer-4-plotter.md`, `docs/layer-5-world.md` (2026-11-07; not public).

**Compare at a point where the original's state is canonical.** Square Roots compared memory at
each world-work interrupt and failed: the main loop's scratch state was half way through a
square's setup. At the first main-loop unit after it, the state is canonical and the setup it
interrupted commutes with the work. A whole-demo comparison is only as good as where it samples.
Source: square-roots `docs/layer-1-spec.md` "Why snapshots at units" (2026-11-08; not public).

**jsbeeb's frame count is not a field count: it steps only when C4 = R6.** phX's logo cut its
display with R8 and never met R6, so `frameCount` stood still: every harness passed headless,
and on bbc.xania.org the picture went white, because the web display decays its phosphor by that
count. A harness that steps frames, or trusts the count as a clock, fails unless the count moves
one a field - make that a check (phX's `verify_frame.mjs` does), and end every frame's display with
one R6 match inside blanked lines (`hardware-facts.md` §11).
Source: `phX/docs/layer-3-6845.md` "jsbeeb versions" (2026-11-14).

**jsbeeb's raster row starts at HSync, not at C0 = 0.** `video.bitmapY` advances at HSync (about
C0 104 with R2 = 100), so a harness grouping fetched bytes by raster row puts C0 104-127 with the
next CRTC line. phX's R12/R13 window looked broken until that was seen.
Source: `phX/docs/layer-3-6845.md` "What was measured" (2026-11-14).

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

**Nothing displayed below `&3000` while ACCCON's D is set on a Master. Emulators disagreed there;
the hardware has now answered.**
Instance: Edge Grinder's panel at `&2000` displayed correctly in jsbeeb under both shadow states;
b-em showed garbage on alternate frames. This entry used to say that what the video fetches below
`&3000` with D set was emulator-dependent and not verified on hardware. It is now: with D set the
6845 reads ANDY and HAZEL there (jsbeeb 2.10, Stryker's Run's HUD), and **a real Master reads
HAZEL** (phX's hardware-test card I, KC's Master, 2026-11-15: the lines showed the green HAZEL had
been filled with, not main RAM's blue). b-em was wrong. Edge's panel moved to `&3000` and is drawn
into both banks; the rule now is D = 0 over any row below `&3000`. The mid-frame display-bank
switch the titles rely on is also measured on real Masters now (1942's panel; phX's card A: at
the character written, odd or even C0).
Source: [docs/decisions.md row 17](https://github.com/kieranhj/edge-beeb/blob/master/docs/decisions.md),
[CLAUDE.md](https://github.com/kieranhj/edge-beeb/blob/master/CLAUDE.md), `phX/docs/hwtest.md`
"Results: tests I-L".

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


**jsbeeb zeroes HAZEL too, and a game that reads it shows it.** Stryker's Run's mountains are
picked by bytes the DFS leaves in HAZEL. Booted straight into the game on jsbeeb only one mountain
sprite ever appeared; after the release disc's menu touched the disc, an undithered sprite nobody
had tested appeared, and users saw it first. A/B harnesses now fill HAZEL alike in both machines.
Source: [strykers-run BUGS.md #9](https://github.com/kieranhj/strykers-run/blob/main/BUGS.md), decisions 70, 71.

**Move the resources to find the bugs that depend on where they are.** Stryker's Run found three
by moving things: the source shifted by whole pages (decision 7) showed the ground's texture was
read from zero page the sprite unpacker happened to leave (BUGS #1); the game's banks moved from
4-7 to 0-3 showed a scroll path that had paged bank 0 for seven days, harmless while bank 0 was
empty (BUGS #16), and a table walk that ran off its table into the bank numbers (BUGS #17). A
permuted bank map, an odd load address or a pre-filled HAZEL is a cheap fault injector.
Source: [strykers-run BUGS.md #1, #16, #17](https://github.com/kieranhj/strykers-run/blob/main/BUGS.md).

**What jsbeeb ignores, a real machine may not: never set ACCCON bits 5-7.** jsbeeb ignores TST,
IFJ and IRR, so a write that sets them passes every emulator check; phX's analyser draw once wrote
CRTC R0 values into ACCCON. What a real Master does with them was not observed - which is the
point: watch every ACCCON write over the whole run (phX's `tools/acccon_watch.mjs`) and change
ACCCON a bit at a time with `tsb`/`trb` (one instruction, so no IRQ lands between its read and its
write) or by a masked compose (`hardware-facts.md` §4).
Source: `phX/CLAUDE.md` Traps (B7 step 0).

**A real 1770 is faster than jsbeeb's at the end of a command, and the difference hangs a
chained-NMI loader.** On KC's Master, Gotek and real floppy alike, phX's first published WIP stopped
at its first ID: READ ADDRESS's INTRQ rose almost at once after the sixth byte (jsbeeb 2.10.2: ~96
us later), while DRQ was still up or the byte routine still armed, so no NMI edge came again. Then,
fixing it, a nested NMI overwrote the A its routine kept in zero page, and could store a seventh
byte. Other differences the port met: jsbeeb 2.10.2 settles the head 30 ms on every command with E
and skews each track ~3 sectors; FORCE INTERRUPT needs a wait before the next command. Rule: in
the last byte's NMI look at BUSY rather than wait for the INTRQ, keep A on the stack, put a
watchdog over every step, and **put real hardware in the loop at the disc driver's first step**
(phX's decision 36). jsbeeb main 2.22.1 reworked the 1770's timings (#1860).
Source: `phX/docs/hwtest.md` "B7", `phX/CLAUDE.md` Traps (2026-11-15); `hardware-facts.md` §6.

**The Master's MOS is not the Model B's in the corners.** `&028C` (the current language) read
`&FF` under a `*RUN` boot, and restoring ROMSEL from it paged ANDY over the DFS; save ROMSHAD
(`&F4`). And a `*RUN` from `!BOOT` arrives with interrupts disabled, so a boot program that waits
for a key in OSRDCH waits for ever until it does `cli` (the kit's boot stub never waits, so never
met it). Both jsbeeb Master; `hardware-facts.md` §4.
Source: `phX/docs/hwtest.md` "Traps found on the way" (2026-11-14).

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

**Two paths that keep one invariant will disagree; make warm-up and steady state the same code.**
1942's level fill and its main loop ran the same three steps in opposite orders; `game_init` drew
the caption before the boot computed its digits; the arcade's restart silences every looping sound
and the port's did not. Source: [1942-beeb BUGS.md #4, #33, #44](https://github.com/kieranhj/1942-beeb/blob/master/BUGS.md).

**One name for two clocks is two bugs.** A variable that meant arcade frames in one routine and
game ticks in another was right in both and wrong between them. Source: [1942-beeb BUGS.md #11](https://github.com/kieranhj/1942-beeb/blob/master/BUGS.md).

**A register held in an awkward place is an argument.** Passing a bank in A where A was the
filename's low byte handed the filing system a name beginning with a ROMSEL value; read the
register allocation before changing a signature, and isolate by disabling the new code and seeing
whether the fault stays. Source: [1942-beeb BUGS.md #49, #80](https://github.com/kieranhj/1942-beeb/blob/master/BUGS.md).


**The logic may read what the drawing code leaves behind.** Stryker's Run's game logic reads the
zero page its plotter leaves (`mover_x_low` stepped column by column as it draws, the screen
address): a build whose plot calls did nothing diverged within 1,745-4,261 passes, and soldiers
already skipped 1-6 columns in the original where clipping left the x advanced (BUGS #4). When
the drawing moves out of the logic, the logic's calls still walk the sprite as the plotter did.
Source: [strykers-run decision 21](https://github.com/kieranhj/strykers-run/blob/main/docs/decisions.md), [strykers-run BUGS.md #4](https://github.com/kieranhj/strykers-run/blob/main/BUGS.md).

**Two substitutions each safe alone can clash.** Stryker's Run's NMOS conversion chose each
65SC12 instruction's NMOS form from the flags and registers free at its site; a `CLC : ADC #1`
form put before a `BRA` that had been turned into a branch on C changed the C it tested, and a `BIT
abs,X` form changed the V a later `BVS` read. Each check of one site passed; only a second check
on the converted build, of what each form newly reads, sees the pair.
Source: [strykers-run docs/briefs/model-b-lite.md](https://github.com/kieranhj/strykers-run/blob/main/docs/briefs/model-b-lite.md) step 1.

**An annotation goes stale when the sources move.** A tool that matches the analysis's annotated
lines to today's sources by line reports failures that are only drift (Stryker's Run's own
`nmosify` gave 47 against an annotation the kit's, which reads the annotation alone, gave 0). Re-
annotate before trusting a line-matched result. Source: the kit's `nmosify.py`, 2026-10-25.

**A walk past a table's end reads the next table as data, harmlessly until that table changes.**
Stryker's Run's scenery walk, near the end of the world, reads past `scenery_data_two` into the
bank each layer pages. While those were the logical banks 4-7 it drew what the original drew;
when a Model B build patched them to the machine's banks, 28-32 frames of background changed. Found
by recording every instruction in two machines from pass 11,360 and taking the first PC that
differed. Source: [strykers-run BUGS.md #17](https://github.com/kieranhj/strykers-run/blob/main/BUGS.md).

**On the 6502 a store sets no flags; on the Z80 the arithmetic before it did.** A Z80 `ADD A,A`
(or a `LD` then a test) transliterated as `STA` then `BPL` tests the instruction before the store.
Isometrikum's music went wrong at tick 260, channel 2, from exactly that; `CMP #&80` fixed it.
Source: isometrikum `docs/layer-2-music.md` (2026-11-07; not public).

**A self-modified operand is at the instruction's address + 1.** The only bug in Isometrikum's
first full world-model run was `&35DF` - the operand of an `ADD` - taken for the `CP` at `&35E0`,
whose operand is `&35E1`. Name every one after its own address (`cpc_35E1`) in the model and the
port. Source: isometrikum `CLAUDE.md` "The models" (2026-11-07; not public).

**A player that dispatches into the middle of instructions cannot be read from a linear
listing.** Isometrikum's command `F6` is the `LD A,(DE)` inside `LD H,&1A` at `&22C1`. Disassemble
along coverage (`template/tools/cpc/covdis.py`); port the dispatch as a word table and an
RTS-jump, with `ZA_CANJUMP` after it. Source: isometrikum `PROPOSAL.md` (2026-11-07; not public).

**A free-running original's behaviour depends on its speed, so its emulator's timing is part of
the specification.** At raw Z80 T (4 per microsecond) Square Roots runs 10-25% fast, its trees land
at other scroll phases, and at field 1,354 a span runs from `&F800`'s block into `&0000` and writes
over the interrupt vector. Under a CPC timing model it runs to its end. A field-locked original
(Isometrikum) does not care. Find out which you have before trusting a reference.
Source: square-roots `docs/layer-1-spec.md`, `tools/cpctime.py` (2026-11-08; not public).

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
overlay at `&0E00-&10FF` is DFS's shared workspace and is copied down after the last filing-system
call; do it earlier and the next `*LOAD` hangs in the 8271 poll. **And the workspace is only yours
once `OSBYTE 140` has had the filing system detach** - or while you own the machine outright and
make no OS call at all (`hardware-facts.md` "The MOS and DFS", `lib/loader.6502`).
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


**Cost on the real distribution, not the average.** Stryker's Run's row-major sprite format was
costed on the sprite set's average row; the player's real rows are short (about 3.8 bytes) and
clipped parts frequent, and built it was slower: 166 late frames of 1,498 against 41.
Source: [strykers-run docs/step2-layer4-costing.md](https://github.com/kieranhj/strykers-run/blob/main/docs/step2-layer4-costing.md).

**Model a reordering before building it.** Running the logic a pass ahead of the render was agreed
on an estimate that a pass costs the larger of its logic and its render, as if both ran at once.
Replaying the measured passes under the new order (`pipesim.py`, one CPU, vsync every 39,936
cycles) gave 73 late frames against 75: no gain, not built. Modelling 50 Hz the same way first
saved a dead-end build (decision 35).
Source: [strykers-run docs/step2-layer3.md](https://github.com/kieranhj/strykers-run/blob/main/docs/step2-layer3.md).

**Under an LZ packer, merging repeated code saves almost nothing; deleting saves.** Shrinkler's
matches already pack a repeated block nearly free, and a loop's control costs bytes that do not
repeat. Isometrikum's crunch measured three merges: `disp_start` as a table loop +20 bytes,
`objects` as a three-voice loop +19, the edge clear and copy as one routine -3 on one executable
and +10 on the other. A round planned on raw bytes at 900-1,200 delivered 502; the planned big
merge was abandoned. In the byte grind, 20 of 99 candidates made the packed stream larger. Price a
size change by the packed length, alone, before building on it.
Source: isometrikum `docs/crunch.md` round 5 (2026-11-09; not public).

**Machinery a previous port needed is not evidence that this one does.** Square Roots imported
Isometrikum's stable-raster slide: its write windows were whole 512 us rows, so the slide cost up
to 80 us a fire, six fires a field, for nothing (its decision 19). It also imported the world work
in the interrupt (lost fires, and the zero-page aliasing in class 3) and a T1 restart from a
guessed constant (70 us of drift a field). Measure the windows and the budget before importing the
mechanism. Source: square-roots `docs/decisions.md` 19, `docs/layer-3-display.md` (2026-11-08; not public).

**A re-armed periodic timer drifts; chain its latch.** Restarting T1 each field from a constant
drifted 70 us a field, and one late entry shifts it against the CRTC for good. Lock T1 once; each
fire loads the latch for the interval to the next. Source: as above, "The fires".

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


**Count the artefact the player sees.** Stryker's Run's Model B build fixed a flickering player by
holding its draw a field: torn frames fell from 38 to 2, and the player was shown a column off
centre instead (ghosting), which the count of torn frames could not see and KC did. Counting the
fields the player missed its frame in (`beamcheck --slot`) led to the real fix, drawing it straight
after the scroll's column: 48 missed to 4.
Source: [strykers-run decisions 77, 78](https://github.com/kieranhj/strykers-run/blob/main/docs/decisions.md).

**After a fix, compare against the old build with the bug undone, or you compare two games.**
Stryker's Run's proof gate reported a fix as 71.6 and 499.0 cycles a pass slower; from the first
death the old build's clobbered generator had played another game. Undoing the clobber inside the
old build's emulator (`--unclobber`) made it the same game: 33.0 and 28.3 cycles faster.
Source: [strykers-run BUGS.md #12](https://github.com/kieranhj/strykers-run/blob/main/BUGS.md).

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

**Regenerate from code, never from a comment.** 1942's sprite set needed twelve build arguments
that lived in a stale comment; a nearly-right command built a plausible wrong set. One switch now
reads them out of the code. Source: [1942-beeb BUGS.md #60](https://github.com/kieranhj/1942-beeb/blob/master/BUGS.md).

**A degenerate generated value is dead code.** `SPR_MAX_TILES = 1` was printed on every build and
nobody acted: 224 bytes of table and a loop that could never iterate. Source: [1942-beeb BUGS.md #45](https://github.com/kieranhj/1942-beeb/blob/master/BUGS.md).

**Smoke-test a generated page before publishing it.** A page whose script throws half way renders
every section below the throw EMPTY for the reader, and a known-wrong label stayed published for
two days because the generator itself threw. Source: [1942-beeb BUGS.md #38](https://github.com/kieranhj/1942-beeb/blob/master/BUGS.md).

**Decode what reaches the chip; do not count it.** An overnight build counted the sound chip's
writes, saw the right number, and shipped three corrupted tunes at the wrong pointer stride. Ship
no sound data until the player's own model has read it back. Source: [1942-beeb BUGS.md #66, #67](https://github.com/kieranhj/1942-beeb/blob/master/BUGS.md).

**A rules file loaded every session has a size budget.** 1942's `CLAUDE.md` grew to 167K by
accretion - every trap, every figure, the story of each fix - and was cut to 31K by moving the
oracle catalogue to its own doc and dropping dated figures and history (2026-10-25). Keep rules and
traps there, one line each with their bug number; detail goes to `docs/`.

**A project made from a template keeps the template's documents until someone diffs them.**
Square Roots, built from Isometrikum's in one unattended night, shipped `BUGS.md`, the memory map
and three other docs byte-identical to the kit template's - the memory map describing a rupture
at `&1900` the demo does not have - and headers that went stale as the design changed (a
"runs only inside fire W" that no longer did; a rules file stating the ring assignment backwards;
two docs citing tools that do not exist). End such a run with `diff -q` against the template and
a grep for every cited path. Source: square-roots (2026-11-08; not public).

**Number each project's decisions on its own.** Square Roots numbered its new decisions 15-19 "so
the two records line up" with Isometrikum's 1-14; Isometrikum took 15 and 16 for other things the
next day. Cite the other project's decision by project and number instead.

---

## 13. The tools around the build

*These are the traps of the session rather than of the machine - the shell, git, the publishing
round trip - met by an agent doing the work, and each cost real work or a wrong report.*

**A shell heredoc can eat backslashes. Write a script with the file-writing tool, then run it.**
phX's edit scripts lost their backslashes passing through a heredoc; the rule is now in its rules
file: write Python edit scripts with the Write tool. Source: `phX/CLAUDE.md` Traps.

**Commit before building a disc you will publish: the stamp names the last commit.** phX's
`tools/build_stamp.py` writes `BUILD_COMMIT` from `git rev-parse --short=7 HEAD`, with `+` when
the tree is dirty, and the link KC is sent carries the same hash. A build from uncommitted work is
stamped with the commit before it (and a `+`), so neither the disc's `INFO` nor the link says what
was tested. Source: `phX/tools/build_stamp.py` (KC, 2026-11-17).

**A WIP link carries its version, URL-encoded, and a cached disc looks exactly like a new one.**
KC's rule since 2026-11-17: every published WIP link names the commit as `?v=<hash>` on the disc
URL, encoded inside the emulator's `disc=` parameter (`...phx-wip.dsd%3Fv%3D244a965`). Without it
a bare link cannot say which build was tested, and the web host's cache can serve the previous
disc under the same name: a stale disc, not a 404. GitHub Pages serves each URL with
`Cache-Control: max-age=600` (measured from the response headers, phX 2026-11-18), so a link opened
before the deploy lands can give the old disc for up to ten minutes: check the served file's hash
against the local one before handing the link out. Source: KC's phX session notes, 2026-11-17/18.

**`git worktree remove --force` and recursive deletes follow Windows junctions.** phX's worktrees
share `work/` and `extracted/` - measurement data not in git - with the main checkout through
directory junctions; on 2026-11-18 a tidy-up deleted part of the main checkout's `work/` through
one before a permission error stopped it. Before removing a worktree or folder, list the links
(PowerShell `Get-ChildItem -Recurse -Attributes ReparsePoint | ? LinkType` - **filter on `LinkType`,
because OneDrive's placeholder files are reparse points too**), unlink each
(`[IO.Directory]::Delete(path, $false)`), check none is left, then delete. Never `--force` there.
Source: KC's phX session notes, 2026-11-18.

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
   its inputs cover odd and even, both axes, a second deck, and every phase a watch was meant to
   cover - deaths, game over, the front end (class 4).
6. Every instrument used to produce a number was itself checked: patch applied, bracket closed,
   wrap impossible, interrupts accounted for (class 5).
7. The build was booted with RAM seeded non-zero (HAZEL too, on a Master), sideways RAM in a
   different set of slots, on a second emulator, and where a display is being tuned, on a display
   (class 6).
8. A transcribed routine was compared with the original for register use, call order and the
   guards inside its callees, and every value it reads was followed back to its writer (class 7).
9. No bank routine pages its own bank; nothing in the IRQ reads a bank without paging explicitly;
   nothing crosses `&8000` (class 8).
10. Anything that writes to a chip was captured at the chip, not inferred from the code (class 9).
11. Every optimisation has a predicted and a measured figure, single-frame, like against like, and
    the ones that lost are written down with their cost (classes 10, 11).
12. Every free-byte figure, "unaltered" claim and file path in the docs was re-measured before it
    was left standing, and a corrected document says what it used to say (class 12).
