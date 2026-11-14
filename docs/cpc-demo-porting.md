# Porting a CPC demo: a Z80 original, a field-exact effect, and the smallest file

*The kit's third path. `PORTING.md` assumes a game with source; `docs/arcade-porting.md` a game
with none, captured in MAME. This is a **demo** from the **Amstrad CPC**: no source, a packed Z80
binary, every effect tied to the field, and - once it plays - a size that matters. Distilled from
two ports of Vanity's CPC 4K demos (Isometrikum, 2018; Square Roots), done one after the other in
November 2026:*

- ***Isometrikum*** (2026-11-07 to 11-09; then a size crunch): the method built from nothing in
  two days, 16 decisions, every layer exact against a Z80 reference on both models and both
  colour sets; then shrunk from 10,623 to 7,582 bytes (decision 15, `docs/crunch.md`).
- ***Square Roots*** (2026-11-07/08, **one unattended night**): the second, from Isometrikum as
  its template, with five decisions taken provisionally by precedent. What it found different -
  a free-running main loop, a 304-line frame, a 6128 bank - is the half of this document that the
  first port could not have written.

*Neither repository is public (the originals are not ours to redistribute). Citations are to
their paths: `isometrikum/docs/layer-3-display.md`, `square-roots/tools/cpctime.py`. The tools
are `template/tools/cpc/` (README there), `template/tools/shrinkler.py`, `size_report.py`,
`grind_bytes.py`, `verify_image.mjs`; the 6502 is `lib/ay2sn.6502` and `lib/unshrinkler.6502`;
the procedures are the skills `beeb-cpc-reference` and `beeb-crunch`.*

---

## 1. The rules this path adds

**The original is the specification, and the specification is a 64K image at the demo's entry.**
Unpack it with the original's own depacker running on a Z80 core, never a reimplementation, and
give that one image to every tool. Nothing is read off a picture that a record can say.

**There are two CPCs in the loop, and only one of them is the reference.** A *picture* machine
(`cpcrun.py`: scanline CRTC, Gate Array interrupts, AY, at CPC speed) shows what the demo looks
like and finds the code. A *logical* machine (`cpcref*.py`) removes the timing that the BBC will
not reproduce anyway, and writes the records every model and every 6502 routine is scored
against. Choosing what the logical machine removes is a decision, numbered and agreed (§3).

**Every model is scored N of N against the records, then every 6502 routine against the model at
the same point.** "7,600 of 7,600 ticks identical" (Isometrikum's player), "7,595 of 7,595
records, all 64K but the stack" (its world) - a percentage is not a result. A routine is checked
against model state, never against pixels.

**A demo's speed is part of its specification.** A game can lose a frame; a demo that loses one
moves every later event. Decide up front how the port is paced (Isometrikum's decision 6: one
main-loop pass and one music tick every field, no overrun copied) and make an overrun a bug the
harness reports, not a thing to look for.

---

## 2. Getting the binary out

1. **The disc.** `cpc/dsk_extract.py` reads both formats - standard `MV - CPCEMU` (Square Roots:
   one track size in the header at `&32-&33`, sector size `128 << N`) and `EXTENDED` (Isometrikum:
   DATA format, sectors `&C1-&C9`, 1K blocks) - and strips the 128-byte AMSDOS header, keeping it
   as `.hdr` (load, exec, length). Isometrikum's `ISOMETRI.KUM`: load `&8000`, exec `&8E50`,
   3,944 bytes. The kit's `py/beeb_port_kit/cpc/dsk.py` is Edge Grinder's reader of the same
   formats; either will do.
2. **The packer.** Both demos were Shrinkler, with the same stub. `cpc/depack.py FILE OUT LOAD
   EXEC ENTRY` loads the file at its address, makes the firmware's `TXT OUTPUT` (`&BB5A`) a `RET`,
   runs the stub on kosarev's `z80` until the PC reaches the entry, and saves the 64K. Isometrikum:
   `&1D00-&36DC`, entry `&2D0A`. Square Roots: `&0C5C-&37FF`, entry `&164B`.
3. **The build re-extracts every time** (`tools/extract_original.py` in both): zip or 7z -> DSK ->
   AMSDOS -> depack -> the slices the port includes, and an `orig.6502` of the original's
   addresses and initial values (`CPC_I_xxxx`). The archive stays out of git; so do `extracted/`
   and `work/`. Make the extractor **assert the facts the port relies on** (Isometrikum's checks
   that the sprite corners are zero; layer-4-plotter.md).
4. **Static views, for orientation only**: `cpc/z80dis.py` (SkoolKit's `sna2skool` over the image)
   and a walk of any bytecode the demo interprets (Isometrikum's `music_walk.py`: 100 calls into
   21 patterns, 95 transposes, 16 loops, 549 notes). Do not read code from a linear listing (§4).

Python traps: kosarev's `z80` installs to user site-packages, so **run these tools without
`python -I`** (Square Roots' brief) - the isolation flag the harness rules suggest for untrusted
data hides it. Extract the archive into its own empty directory first.

---

## 3. The two machines

### The picture: `cpcrun.py`

One 64 us scanline at a time, modelling only what a demo touches: the Gate Array (pens, border,
mode, the 52-HSYNC interrupt counter with its VSYNC resync and acknowledge), the 6845 (VCC, VLC,
MA, the R5 adjust, R7's 16-line VSYNC, R12/R13 latched at each CRTC frame start so ruptures
work), the PPI (port B bit 0 = VSYNC, ports A/C driving the AY), the AY register file, and since
Square Roots the 6128's `&7Fxx` RAM configurations `&C0-&C7` (the video always reads the base
64K). Register writes take effect at the end of their scanline. Out: `frames.npy` (hardware
colour per mode-1 pixel), `ay.log`, `out.log`, `regs.log`; `sheet.py`/`frames2png.py` render them.

**Its timing is the trap.** A Z80 at raw T (4 per us) runs a CPC program 10-25% fast, because the
Gate Array stretches every memory and I/O cycle onto a 1 us grid. For Isometrikum it did not
matter (the main loop waits for every field). For Square Roots it was fatal: at raw T a span ran
from `&F800`'s block into `&0000` and wrote over the interrupt vector at field 1,354.
`cpc/cpctime.py` charges each instruction `ceil(T/4)` us with the known exceptions (PUSH 4, RST
4, taken RET cc 4, DJNZ not taken 3, OUT (C) 4, LDI/OUTI 5, the `(IX+d)` forms 6-7) plus 5 us an
interrupt; `RAW=1` restores raw T. About 3x slower: 7,000 fields in 80 s. **The table is the CPC
scene's, from memory, and not measured on a CPC** - it is checked only by consistency (the
original's own cycle-counted delays land where their author put them; the demo runs to its end).
Mark anything that depends on it PROVISIONAL until a real CPC or WinAPE/ACE confirms it.

### The reference: the logical machine

**First decide whether the main loop is field-locked or free-running.** Find the wait loop, and
run coverage to see what runs between waits. This choice selects the reference:

| The original | The reference | Pacing the port |
|---|---|---|
| **Field-locked**: one pass of the main loop per field, the interrupts do the music and the CRTC (Isometrikum) | `cpc/cpcref_fieldlocked.py`: the Z80 **4x fast** (LINE = 1,024 T) so no pass overruns; **VSYNC read as an edge** (1 once per field, as the logo's delays see it on hardware); interrupts **queued** and taken only while the CPU sits in the wait loop (`&3616-&361B`); fields from a **fixed 312-line clock**, not the CRTC (the queued writes reach the CRTC late and it would never VSYNC). Records at every "field done" call | One pass a field; overrun is a bug (decision 6) |
| **Free-running**: the main loop draws as fast as it can and counts fields only while it waits; an interrupt does the "world work" (Square Roots) | `cpc/cpcref_units.py`: CPC timing (`cpctime`); the main loop cut into **units** at commuting boundaries (a span, a wait pass, a square's start, an edge's start, a side's move); the world-work interrupt **held out** of the few non-commuting regions (a span fill, a wait's decrement-to-latch) so it always lands between units; records at the **first unit after** a world work; `world.log` = how many units had started before each world work | A **schedule**: `make_sched.py` turns `world.log` into one byte per world work (units to the next), the port's main loop calls `unit_point` at each unit and runs world work *n* when exactly U(*n*) units have started and the interrupt has made it due |

Isometrikum's two corrections to its own reference, found the hard way: a late acknowledge must
not clear the Gate Array's counter (or ~5% of interrupts are lost), and nothing may be taken at
the "field done" call itself (or 3 snapshots include the field's first interrupt). Square Roots'
holding back moved 273 of 4,798 world works by 1.04 lines on average, 4 at most; with
`NODEFER=1` the unit counts and tree starts were identical and the screen differed in 357
records by at most 13 bytes - **measure what the holding back changes before calling it
harmless**.

**Snapshot where the state is canonical.** Square Roots compared at the world work first and
failed: the main loop's scratch state was mid-setup. At the next unit it is canonical, and the
setup it interrupted commutes with the world work.

**Records.** `passes.bin`: a header (field, units, ticks, ...) and `zlib(64K XOR the previous
record)`, so 7,600 64K records fit; `ticks.npy`: the player's state after every music call;
`ay.log`, `r.log` (every `LD A,R`), `crtc.log`, `songs.log`/`trees.log`, `boot.bin`. Isometrikum's
ran in ~35 s.

**Races are settled by the reference, once.** Under `cpcrun` Isometrikum's main loop read music
channel 1 about two lines before the tick and channels 2-3 after it. The reference fixes one
order (a pass sees the music as it stood at the start of its field, decision 8) and the port
copies it, so the comparison is exact rather than "within a tick".

**When the capture has an artefact, build an ideal reference from the proven model.** Isometrikum's
logo clears 16K with an `LDIR` that holds the queued interrupts back and then plays ~14 ticks in
a burst. The port ticks once a field (decision 12); `ideal_ref.py` runs the model with 41
interrupts before the first pass then 6 a field, and the LFSR's bits for `LD A,R`. It agrees with
the capture to record ~6,641 and is the reference from the logo on. Square Roots' boot needed the
same: its 19 boot-time world works fell **inside** the original's 32K `LDIR` clears, and running
"tables first, then the world works" left 42 bytes wrong; `boot_model.py` replays each at the
`DE` of the clear it fell into, exactly.

**A second colour set needs its own reference.** Re-dithered data changes screen RAM, so the
stock set is checked against the *model* run on the re-dithered image along the original's own
schedule (`ideal_ref.py --stock`; Square Roots' `stock_ref.py`), with the self-check that run on
the original's data it gives 0 records different.

---

## 4. Reading the code: coverage first

`cpc/cpccov.py` (or `cpccov_raw.py` before a reference exists) makes every address a one-shot
breakpoint, cleared on first hit, so one run costs one stop per instruction start: Isometrikum
1,844 starts, Square Roots 1,659 (all in `&0038` and `&164B-&2333`). `cpc/covdis.py MEM cov.txt
START END` disassembles **only along executed starts**, with a gap marker where execution never
went. Use it, never a linear listing:

- **Z80 players enter handlers mid-instruction.** Isometrikum's command `F6` is the `LD A,(DE)`
  inside `LD H,&1A` at `&22C1`. A linear listing shows neither.
- **kosarev stops between a DD/FD prefix and its opcode**; covdis drops the second stop.
- Coverage is also **the list of paths never taken** - which later proved, with the whole-demo
  check, which code could be cut (Isometrikum decision 16a, §8).

Find, in this order: the interrupt chain (on the CPC each handler often rewrites the vector at
`&0039` for the next: Square Roots' six), the wait loop, the field-locked/free-running question,
every `OUT &7Fxx` (pens or RAM banks? Square Roots' were all RAM configurations - its palette
never changes after boot), every `LD A,R`/`LD A,I`, every AY register written (envelopes?).

---

## 5. The models, and Z80 to 6502

Each effect is a Python model (`fx_music.py`, `fx_world.py`) that **runs on the original's own 64K
image**, so self-modified operands live at their Z80 addresses (Isometrikum's mixer `SET`/`RES`
opcode at `&2321`, rewritten at runtime), scored record by record. Writing a model corrects the
first reading: Isometrikum's period table was at `&2351`, not `&2269`; a tune start sets counts to
1. Every model in both ports reached N of N; Square Roots' music did on its first run (5,198 of
5,198), its world after two driver fixes (the wait unit was `&171E` not `&16FF`; snapshot at units).

The transliteration traps, each met:

- **`STA` sets no flags.** `ADD A,A` sets the flags it is tested on; a `STA` then `BPL` tests the
  previous instruction. Found at tick 260, channel 2 (Isometrikum layer-2-music.md).
- **An operand is at instruction + 1.** The only bug of Isometrikum's first full world run:
  `&35DF`, ADD's operand, taken for the CP at `&35E0`. Name each one after its Z80 address in
  both the model and the 6502 (`cpc_35E1`), or the off-by-one is invisible.
- **Mid-instruction dispatch** becomes a word table and an RTS-jump, declared to Baron with
  `ZA_CANJUMP` straight after the computed jump (`ZA_CANCALL` after a computed `jsr`), or the
  zero-page allocator overlaps what it cannot see.
- **`LD A,R` is timing**, not data: it becomes a seeded LFSR (Galois, taps `&B400`, seed
  `&ACE1`), mirrored in the reference, and is compared **by density** (50.1% against the
  capture's 53.2%), not bytes (decision 7). Search for it first; Square Roots had none.
- **`SLL`** (shift in a 1), `LDIR`'s `DE`/`BC` after the copy, `DJNZ` delays (on the CPC a timing
  loop; on the BBC the field wait) - transcribe the effect on memory, then decide the timing.
- **The original's quirks are the specification.** Square Roots computes every screen address as
  the Z80 does, including `INC HL` across a 2K block (it continues a scanline lower) and spans
  wider than the screen (they spill onto the next row): reproduced, not fixed.
- **Off by one pass.** The port's pass runs after its field's tick; the reference's record runs
  before it. Compare such variables one pass back, and say so in the harness.

---

## 6. The display: CPC geometry on a BBC

**CPC mode 0 is MODE 2 with the bit order changed.** Same pixel clock, same pixel shape, the
same interleave (left pixel in bits 7,5,3,1), so masks (`&AA`/`&55`) and sprite bytes are
identical and screen RAM is byte-comparable after an address transform. **CPC pen *p* is BBC
logical colour *p* with bits 0 and 3 swapped** - in a NuLA palette and in any re-dither.
One CRTC character is 2 bytes on the CPC and 1 on the BBC, so the BBC steps horizontally a
byte natively: the CPC's R3 HSYNC-width half-step trick is not needed (Isometrikum decision 9) -
but see the right-edge consequence below.

**The overscan, on a Model B with no shadow RAM.** Isometrikum's 192 x 280-f picture: MODE 2 with
R1 = 96; the top 160 lines in the 16K hardware ring `&4000-&7FFF` (latch lines 4 and 5 low); the
bottom from a **software ring** of 1,446 cells at `&0FD0-&3CFF` with mirrors either side
(`&0CD8-&0FCF`, `&3D00-&3FFF`) so a row may straddle either end, shown as one CRTC cycle or two
where the ring wraps inside it, chosen per field. Square Roots, scrolling vertically only (160 x
280, R1 = 80), put it the other way round: **the bottom page in the hardware ring**, because it
ends in an R5 adjust that reads on into the next row and only the hardware ring wraps for free,
and the top in a 20-row software ring `&0E00-&3FFF` that needs no mirrors. `&0D00` became screen
in both, so the NMI's RTI is gone: acceptable once the filing system is released.

**Size a software ring by replaying the original's writes, not by arithmetic.**
Isometrikum's copy rows are skewed by up to 4 bytes; `ring_size.py` replays every write into a
ring of R cells and checks every displayed byte: 1,440 cells -> 1,218 fields of 1,499 wrong,
1,442 -> 1,089, 1,444 -> 170, **1,446 -> 0**. The same replay proved the right-edge clear
(`edge_clear.py`): with the native 1-byte step, on R3 = 6 fields the last byte of each row is the
next row's first, and the port clears exactly those cells early - proved exact because the
original's own column clear zeroes them a pass later (one exception saved and restored). The
replay had three bugs of its own before it was right: replaying *changed bytes* instead of
writes, folding offsets around +-1,024 instead of the window, and a misread clear column.
**Run the model on a filled page to see what it writes** before modelling the write pattern.

**The frame may not be 312 lines.** Square Roots' CPC frame is 304 lines (2,127,627 lines in
7,000 fields: 51.4 Hz). Keeping 304 on the BBC keeps the scroll speed and the tempo exact; 312
would make the demo 2.7% slower (its decision 17, PROVISIONAL). Measure the original's field
before assuming 50 Hz.

**Rupture by System VIA T1, phase-locked once and never restarted.** Five fires a field
(Isometrikum), six (Square Roots); CA1 never enabled. **Chain the latch** - each fire loads T1's
latch for the interval to the next - and never restart T1: a first Square Roots version re-armed
T1 at fire 0 from a guessed constant and drifted 70 us a field. The main loop builds each
field's **fire program** (the CRTC values per fire) into whichever of two blocks is not live
(`disp_build`), fire 0 swaps them, and pass *k*-1 is what field *k* shows, as on the CPC; a fire 0
that finds no new block is an overrun, counted (`disp_miss`). The display keeps **its own copy
of the scroll recurrence**, stepped in the interrupt, so a late pass cannot glitch the CRTC.

**A stable-raster slide only where a window is narrow.** Isometrikum's fires compute `e = loaded
- T1CL` and jump into a page-aligned NOP slide (self-modified low byte; `ASSERT HI(slide) =
HI(slide_end)`), so the CRTC writes land on the same cycle every field: 80 us of slide held one
position in 2,994 of 2,999 fields; 64 us split the writes two cycles apart. Square Roots copied it
and found every write window a whole 512 us row: the slide cost up to 80 us a fire, six a field,
and bought nothing (its decision 19). **Measure the write windows before importing timing
machinery from a previous port.**

**jsbeeb facts the display met** (jsbeeb 2.10.2): VSync starts **the instant C4 = R7**, so R7 = 0
may be written only after the last cycle is past its row 0 (Isometrikum's one-row case leaves
lines 310-311; the write landed at 310:39 - the riskiest item for real hardware); A's R4 must be
3 before A's row 0 ends, because the last cycle's R4 may be 0; a fire's first CRTC write lands 4
lines after its nominal line with no correction (CA1 flag timing + IRQ path + slide), and
`T1_SYNC_TUNE = -3*SL` puts every write 1 line + 5 characters after it. Fires landed late in 15
of 6,399 fields because a bass interrupt was already running - inside their windows, but the
slide cannot absorb it.

---

## 7. The pass and the field

The BBC field is 39,936 cycles (Square Roots' 304-line field, 38,912); after fire 0 about
36,500 are left for the pass. Isometrikum's first complete pass overran at pass 458; the worst
pass went 49,252 -> 34,892 by table-driven `disp_build`, unrolled column clears, pointer-stepped
copy and clear, straight-line plot programs (16, one per behind/front x line phase: a cube 4,780
-> 2,019 -> 1,859 cycles) and moving `ay2sn` from fire 0 to fire 1 so the pass starts at the top of
the field. **Deferring work to the next pass only moves the load**: the heavy passes are the ones
that do not end with a clear. The harness prints the least slack (Isometrikum: 1,752 cycles, 4%,
at record 7,427) and the gate keeps a floor under it.

**Work out of the interrupt.** Square Roots first ran its world work in fire W as the CPC does.
A row-copy field's work took 17K cycles, longer than the 95 lines to fire 0; a second T1 underflow
while the handler ran merged into one IFR flag and **a fire was lost**. Worse, Baron assumes code
reachable from a `ZA_INTERRUPT` handler runs only inside it, so it **packed the music interrupt's
zero page onto the screen routines'** (`so`/`mus_c`, `sl`/`mus_a`, `sn`/`mus_b`): the music
preempted a span and the first full run failed at record 207. Moving the work to the main loop,
paced by the schedule (§3), fixed both. **No handler may outlast the gap to the next fire, and no
routine may be shared between an interrupt and the main loop under Baron's allocator** (or the
interrupt gets its own generated copy with its own variables).

**Late work, measured as a table.** Square Roots counted world works that start after the next
field's first line, of 4,780, change by change: 312 in the main loop at first; 251 with a BBC
side of the line table; 139 with whole top-ring lines; **92** copying straight into the hardware
ring; 103 with spans through the unrolled block (reverted); 81 with the slide off; **50** with
finer units (a square's setup cut where it commutes). The harness's `delay` line (each world
work's start after its fire) is that port's slack; `WORLD_LATE=1` lists the late ones. 50 is
still an open bug against decision 6, and was reported as one.

---

## 8. Sideways RAM with code in both banks

The Model B + 32K baseline (decisions 1, 5): BANK (the higher bank: display, music, main loop)
and PLOT (the lower: the plotter and its 6.6K cache), **both running code at `&8000`**. LOW
(`&0400-&0CFF`) holds the IRQ entry (it pages the code bank, `ROMSHAD` saved and restored), the
trampolines (`far_plot`: set ROMSHAD+ROMSEL, JSR, back to the code bank) and everything both
banks read (`sc_*` scroll state, `pl_*` plot inputs). In the IRQ, T1 (raster) first, then the
bass. The disc's chooser finds the banks (`swr_find`: ROMTYPE-empty banks only, 16 distinct probe
values against aliasing boards, each bank's byte restored under its own select) and passes them
in zero page.

Harness consequences, all met: **an address hook must check ROMSEL** (a hook at
`plot_test_done` fired at the same address in the other bank); **read state from the code bank**
(`readMemory(a, n, {bank})`); on the Master a ROM was running at `main_loop`'s address before the
boot had paged the code in, so a hook read the wrong bank's number - **gate hooks on the boot
having happened**.

---

## 9. Music: the AY on an SN76489, in real time

`lib/ay2sn.6502` (Square Roots' copy; Isometrikum's crunch then cut what its tunes never do) is
Unspoken's fork of arkos-player-bbc's `ay2sn`, set back to the CPC's 1 MHz AY:

- **The clock**: SN period N = 2P, a shift, no tone table. (The kit's offline `ay2sn.py` takes
  clocks as parameters for other machines.)
- **The bass floor**: below the SN's 122 Hz is AY P >= 512. Those notes go to **software bass**:
  the claiming channel's tone is parked at period 1 (inaudible) and the User VIA's T1,
  free-running, toggles its attenuation at the note's frequency (`bass_irq`); one sticky claim at
  a time (`bass_pick`/`bass_claim`). Periodic noise is the fallback held in reserve.
- `sn_write` holds WE low 18+ cycles; a due half-cycle is serviced before a retune.
- **Measure the AY use before porting the converter**: over 7,200 fields Isometrikum's tune never
  wrote R11-R13, never set a volume's bit 4, used noise periods 2, 6 or 8 only, and had channel A
  carry the bass (periods 100-1,448). The envelope generator was removed on that evidence.
- **Cost**: the VSync IRQ's music 2,337 cycles a field (5.9%); bass 1.95 interrupts a field at
  152 cycles. **Weakness: latency.** The bass interrupt waits behind the fires and the music, so
  toggles land up to +-4,700 cycles late: within 8 cycles of the period 85.5% of the time at Layer
  2, 77.5% as fires were added (Square Roots: 69% once its world work ran in the main loop). The
  cure, not yet built in either: let the bass nest (CLI after each fire's CRTC work).
- **Verify by writes**: `verify_music.mjs` captures every SN write and tells the bass's from
  `ay2sn`'s by the return address on the stack (`irq_after_bass`); `ay2sn_model.py` is the
  6502 in Python for the expected bytes; skip the Master MOS's own SN writes before boot.
  **Sample at the port's tick, not the emulator's frame**: Square Roots' 304-line T1 drifted
  against jsbeeb's 312-line frames and its harness read state mid-tick every 39th tick.

---

## 10. Colour: the stock BBC and VideoNuLA

**Find out whether the palette changes at all** before designing a palette scheme. Square Roots'
brief predicted "a palette fade, the hard design question" from `cpcrun` pictures; the palette is
written once at boot, and the "fade" is 13 background tile sets. Every `OUT &7Fxx` in that code
was a RAM configuration.

**The stock set: re-dither, per face, with RTW's chart.** RTW's dither chart maps each of the
CPC's 27 colours to a BBC two-colour checker (`cpc/palette_map.py` `RTW`, keyed by firmware
colour 9G + 3R + B). A face drawn as a checker of two pens takes, on its even pixels, one colour of
the even pen's pair and on its odd pixels one of the odd pen's, choosing the combination whose
average is nearest the face's (nominal CPC levels 0, 1/2, 1; ties in CIELAB with linear light,
middle level 0.22, then RTW's order). **Per face, not per pen**: a pen appears in several faces.
Square Roots learned the next rule by getting it wrong: **re-dither per byte, alternating per
line, not per pixel parity** - by parity a pen half-toned on one phase always took one colour of
its pair, and dark red came out black. Measured error, CPC against stock averaged over 8 x 8
cells: 0.02-0.16 on a 0-1 scale, worst on greys (RTW's grey is a magenta/green checker).
`palette_preview.py` writes the side-by-side for the owner, who judges it.

Logical colours in MODE 2: 0 transparent black, 1-7 the physical colours, 8 an *opaque* black
(the CPC's pen 4, black but counted as filled), 9-14 the faces involving a flashing pen
(re-pointed by 6 ULA writes in fire 0), 15 spare. **A palette change can often be avoided by data
analysis**: Isometrikum's pen 5 change needed no write because its colourways are drawn only
before or only after it, and the screen is all pen 0 at that moment.

**The NuLA set: the original's bytes, the CPC's palette.** Screen RAM byte-identical to the CPC's.
Write `&FE22 = &40` (reset; also resets the two-write protocol), then `&11` (palette mode 1:
logical colour = NuLA entry, the ULA's palette bypassed), then 16 entries, entry L = the CPC
colour of pen `swap03(L)`. CPC levels 0/1/2 -> NuLA 0, 8, 15; the Gate Array's 32 colours become
a table of NuLA's two-byte values. **Interrupts off between the two bytes** if an IRQ also writes
the palette.

**Detecting a NuLA** (after stnicc-beeb's loader): a stock ULA decodes only A0, so `&FE22` aliases
`&FE20`. Time MODE 7 fields with ULA control `&10`, write `&44` to `&FE22`, time again: a NuLA
resets and the fields keep their rate; a stock ULA takes `&44` as control, its clock bit clear,
and runs at half rate. Measured (jsbeeb): stock 9,452 then 18,909 (0.50); `video_nula` 9,453 then
9,452 (1.00); decide NuLA when 4E >= 3G. **Interrupts off, counting the CA1 flag in a loop**:
with the MOS running, its own `&FE20` writes made a NuLA read 29/57.

**One disc, two sets.** The chooser (`Game`) detects the NuLA and runs `ISO` or `ISON` (or loads
`BANK`/`BANKN`); the chooser itself is assembled identically in both, and `make_disc.py` checks it.

---

## 11. The crunch: the smallest file that plays identically

A 4K demo's port will be asked how small it is. Isometrikum's was 34,311 bytes raw, 12,271 as
ZX02 streams, 10,623 as Shrinkler streams, against the original's 3,944. Decision 15 made the
goal **the smallest executable that plays identically, whatever the load time**; 7,582 bytes
after five rounds. What transfers:

**The measuring stick first (round 0).**

- **Shrinkler, vendored, with an oracle.** `template/tools/shrinklersrc/` (askeksa 17cff11,
  unmodified; any C++ compiler or `zig c++ -O2`) used as `-d -b -p -9` (raw data, no parity
  context). `template/tools/shrinkler.py` is upstream's decoder transcribed line for line, and
  every stream is decoded and compared with its input before the build uses it.
- **`lib/unshrinkler.6502`**: Dudek and Fusik's unShrinkler (zlib licence), translated from MADS
  to Baron instruction for instruction, `PARITY=0 FAST=0`: about 320 bytes, 1.5K of page-aligned
  workspace, **~4,000 cycles a byte** (the original's 6.6K in 13.5 s; Isometrikum's single
  executable unpacks in 34 s, which the owner accepted for the size). ZX02's depacker is 131 bytes
  at 54 cycles a byte: Shrinkler wins only when size is all that counts.
- **`template/tools/size_report.py`**: packs the payload, decodes it with the oracle charging
  every bit's `-log2 p` to the output byte it produced, and totals by section, source file and
  label from Baron's symbol dump. **Aim at the packed cost, never the raw size**: a table of zeros
  costs nothing, a page of hand code most of its length.
- **The identity gate**: `template/tools/verify_image.mjs` compares memory at two hooks
  (`bank_main`, `main_loop`) against a golden image, with a mask, both models, both sets. While a
  round changes only how the bytes *arrive*, the gate is the identical image; once code changes,
  it is the whole suite plus a slack floor. **Pin the zero page** during identity-gated rounds:
  Baron's allocator repacks when an unrelated variable disappears and moves operands.

**What paid, round by round** (stock / NuLA executable):

| Round | Bytes | What |
|---|---:|---|
| 1 | 10,771 / 10,957 | One file per set: a stub plus LOW, BANK and PLOT streams, each packed alone |
| 2a | 9,197 / 9,392 | **Generate at boot**: 6,124 bytes of tables, edge chains, copy/clear blocks and ramps rebuilt by `src/gen.6502` as the original's own `&2EC2` builds them. `make_disc.py` ships every `genr_*`..`genr_*_end` range **as zeros**, so the assembler still lays out every label and the harnesses' symbols still resolve |
| 2b | 8,485 / 8,500 | The sprite cache and the 16 plot programs generated at boot (the assembler's macros re-run as 6502); PLOT ships 214 packed bytes |
| 3a | 8,298 / 8,311 | The sideways-RAM check moved into the chooser |
| 4 | 8,084 / 8,089 | The kit's grind retargeted to bytes (below) |
| 5 | **7,582 / 7,573** | By hand, decision 16: dead code (-128), never-taken player paths (-147), tune call targets made absolute by the build (-80), harness-only state moved into the harness (-80), the timeline as an event table (-31), a clear as a page loop over more screen-off fields (-16), the logo's data laid out by column and a table built at boot (-20) |

**The rule the crunch paid for: deletions pay, merges do not.** Shrinkler's matches already pack
repeated code nearly free, so folding three copies into a loop saves little and the loop's
control costs more: `disp_start` as a table loop +20; `objects` as a three-voice loop +19; the
edge clear and copy as one routine -3 on one executable and +10 on the other. Raw-byte estimates
over-counted merges 3-10x: round 5 was planned at 900-1,200 bytes and delivered 502. **Measure
each change alone, packed, before building on it.** What paid: deleting (dead paths, write-only
variables, zeroing state that ships as zero), generating (tables at boot, workspace as zeros),
moving harness bookkeeping out of the shipped code (the harness snapshots at hooks instead), and
**re-laying data for the context model** (the logo by column; absolute tune targets, which made
identical patterns literally identical). Measured as no help: Shrinkler's stronger settings (0),
merging LOW and PLOT into INIT (~25, eaten by copy code), one stream for everything (~32, likewise),
splitting the tunes' opcode and argument streams (a loss), a formula for the period table (11 of
12 notes match). The original's own player packs to 688 bytes and its tunes to 904; the port's
tunes were at par (917) - **the whole gap was code**.

**Cutting what the demo never runs needs a decision.** "Never taken" comes from coverage over the
whole demo and is proved by the whole-demo music and world checks on every build; it reverses
"transcribe verbatim", so it is a numbered decision (Isometrikum's 16a), as is re-encoding the
original's data (16b) and spreading invisible screen-off work over more fields (16c).

**The byte grind.** `beeb-micro-grind` with windows weighted by packed cost
(`grind_bytes.py profile` turns the cost map into `pcprof.mjs`'s shape) and the executables'
lengths as the measure (`grind_bytes.py measure`); `grind_config.py`'s `UNIT = 'bytes'` and
`SCORE`. 328 agents, 99 candidates: 56 kept, **20 made the packed stream larger**, 20 stale, 2
failed the suite, 1 refuted; the many 1-3 byte raw claims often measured 0 packed. Slack rose
from 1,724 to 2,327 as a side effect. Run it once, after the generation rounds; then work by hand
on what the cost map says, deleting.

---

## 12. The second port: a previous port as the template

Square Roots was built in one unattended night from Isometrikum. What made that work, from its
brief (`Projects/square-roots-PROMPT.md`):

- **A reading order**: the template's rules file, plan, decisions, done and every layer doc,
  then its write-ups, then the kit.
- **Pre-measured facts about the new original, dated and flagged "verify before relying on
  it"**: the DSK format, load, exec, entry and unpacked range. All were right and saved Layer 0.
- **The targets answered up front** ("the same as Isometrikum"), so most decisions became
  defaults, and a rule for the owner's other decisions: never wait; decide by precedent, build
  it, mark it PROVISIONAL with its evidence and alternatives, list it for the morning.
- **The template's traps copied into the brief**, a named check per layer on both models, a
  commit per layer, and a defined end state: the WIP published, the write-ups, a `PLAN.md` that
  opens "For KC in the morning".

What went wrong, so the next brief says it:

- **The brief's reading of the original was wrong** ("the palette fades": it is tiles), and so
  was the template's machinery imported without measuring: the stable-raster slide (no narrow
  windows), the world work in the interrupt (lost fires, zero-page aliasing), a T1 restart from a
  guessed constant (drift). **Re-measure every mechanism the template brings.**
- **Template documents left unadapted**: `BUGS.md`, the memory map and three other docs were
  byte-identical to the kit's template, and headers went stale as the design changed overnight -
  the rules file stated the ring assignment backwards. **End the night with a doc pass that
  `diff -q`s every doc against the template and greps for files that do not exist** (skill
  `beeb-doc-pass`).
- **The whole template `tools/` was copied**, so harnesses for the other demo sit unused beside the
  new ones. Copy what the new original needs.
- **Decision numbers were aligned with the template's** ("so the two records line up"), and the
  template went on taking numbers for other things the next day. Number each project's decisions
  on their own and cite the other's by project.
- Layers were batched into combined commits (0+1, 4-6), against "a commit per layer".
- The overrun target was not met (50 late world works) - and was reported as open, not done.
  That is the right failure.

---

## 13. Order of work

0. **Layer 0**: the kit's template, the original's archive outside git, `extract_original.py` in
   the build, the depacked 64K image, the tools in `template/tools/cpc/` adapted to its entry.
1. **Layer 1 - the specification**: coverage and `covdis` reading; the field-locked or
   free-running question; `cpcrun` contact sheets; the logical reference with its decision; every
   effect a model scored N of N; the AY's register use measured; `LD A,R` searched for.
2. **Layer 2 - music**: the player on the 6502 against the model's tick state, `ay2sn` at the
   source machine's clock, the SN writes against the model, both models.
3. **Layer 3 - display**: the fires, the rings sized by replay, the frame length, write windows
   measured, every field's CRTC program checked against the reference.
4. **Layers 4 onward - the effects**, each against the model's records, with the slack (or the
   late count) printed and floored.
5. **Colour**: the palette's behaviour measured, the stock re-dither with its own reference, the
   NuLA set, one disc.
6. **Release**: the suite on both models and sets, b2 and real hardware (neither demo has been
   seen on either), the WIP published.
7. **The crunch**, if size matters: the measuring stick, the identical-image rounds, generation,
   then deletions measured one at a time (skill `beeb-crunch`).
