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
- ***phX*** (Condense, Revision 2018; ported 2026-11-14 to 11-18, to a **Master 128**): the
  opposite size - a multi-part, multi-load 6128 demo of eighteen parts and a loader card on a
  two-sided disc, five minutes long, cycle-exact rasters, three tunes - and **its source is
  public** (No Recess's release, for education only). Sections 13-19 are what it added: the
  source read and reviewed, a reference that is the picture machine checked against WinAPE, the
  disc as the specification, the sequence built as a backbone first, colour, RVI and an offline
  music stream.

*None of the three repositories is public (the originals are not ours to redistribute, nor is
phX's source). Citations are to their paths: `isometrikum/docs/layer-3-display.md`,
`square-roots/tools/cpctime.py`, `phx/docs/winape-check.md`. The tools
are `template/tools/cpc/` (README there), `template/tools/shrinkler.py`, `size_report.py`,
`grind_bytes.py`, `verify_image.mjs`; the 6502 is `lib/ay2sn.6502` and `lib/unshrinkler.6502`;
the procedures are the skills `beeb-cpc-reference` and `beeb-crunch`.*

---

## 1. The rules this path adds

**The original is the specification, and for a single-file demo the specification is a 64K image
at the demo's entry.** Unpack it with the original's own depacker running on a Z80 core, never a
reimplementation, and give that one image to every tool. Nothing is read off a picture that a
record can say. A demo that loads itself in parts has no such image: its specification is **the
disc and the machine that reads it** (phX: every tool takes the DSK, section 15).

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
scene's, from memory, and not measured on a CPC** - it is checked by consistency (the original's
own cycle-counted delays land where their author put them; the demo runs to its end) and, since
phX, **partly against WinAPE**: phX's reference (this table, a type-0 6845, a Gate Array) matched
WinAPE's type 0 over 658 captures to a raster line, a byte column or a few pixels in every part -
OUT timing: a Gate Array write applied half a microsecond early, a line in the logo - except one
CRTC-model error, the outro's scanline order (section 14). Mark anything that rests on a beam position
PROVISIONAL until WinAPE (or a real CPC) has seen that part.

### The reference: the logical machine

**First decide whether the main loop is field-locked or free-running.** Find the wait loop, and
run coverage to see what runs between waits. This choice selects the reference:

| The original | The reference | Pacing the port |
|---|---|---|
| **Field-locked**: one pass of the main loop per field, the interrupts do the music and the CRTC (Isometrikum) | `cpc/cpcref_fieldlocked.py`: the Z80 **4x fast** (LINE = 1,024 T) so no pass overruns; **VSYNC read as an edge** (1 once per field, as the logo's delays see it on hardware); interrupts **queued** and taken only while the CPU sits in the wait loop (`&3616-&361B`); fields from a **fixed 312-line clock**, not the CRTC (the queued writes reach the CRTC late and it would never VSYNC). Records at every "field done" call | One pass a field; overrun is a bug (decision 6) |
| **Free-running**: the main loop draws as fast as it can and counts fields only while it waits; an interrupt does the "world work" (Square Roots) | `cpc/cpcref_units.py`: CPC timing (`cpctime`); the main loop cut into **units** at commuting boundaries (a span, a wait pass, a square's start, an edge's start, a side's move); the world-work interrupt **held out** of the few non-commuting regions (a span fill, a wait's decrement-to-latch) so it always lands between units; records at the **first unit after** a world work; `world.log` = how many units had started before each world work | A **schedule**: `make_sched.py` turns `world.log` into one byte per world work (units to the next), the port's main loop calls `unit_point` at each unit and runs world work *n* when exactly U(*n*) units have started and the interrupt has made it due |
| **Cycle-exact raster**: the effects are the beam's position - per-line palette and CRTC writes, ruptures, RVI - and the demo loads itself from disc (phX) | **The picture machine is the reference** (section 14): CPC timing, the 6845 at character resolution **of the CRTC type the demo's own test selects** (phX: type 0, decision 5), the Gate Array, the FDC and the disc (section 15); records per field of the picture and the I/O. Checked against WinAPE as a Layer 1 gate | One CPC field is one BBC field, each part's draw cycle-counted and entered at one beam position; every field that is not 19,968 us decided (section 14) |

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
  a time (`bass_pick`/`bass_claim`). Periodic noise is the fallback held in reserve - for a demo
  whose interrupts have room for a bass timer. **A cycle-exact raster demo takes periodic noise
  as the default** and converts offline (section 19): a software-bass interrupt would land inside
  a counted line.
- `sn_write` holds WE low 18+ cycles; a due half-cycle is serviced before a retune.
- **Measure the AY use before porting the converter**: over 7,200 fields Isometrikum's tune never
  wrote R11-R13, never set a volume's bit 4, used noise periods 2, 6 or 8 only, and had channel A
  carry the bass (periods 100-1,448). The envelope generator was removed on that evidence.
  **Which channel is the bass is a property of a section, not of a tune**: measure the lowest
  channel frame by frame over the whole demo before fixing one. phX's moved twice inside its
  tunes, and a per-tune rule turned a deliberate glitch into bass and the real bass line into
  one note (its decision 65, section 19).
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

## 13. The source, when it exists: read it first, review against it last

The 4K demos had no source. phX's authors published theirs (No Recess: the Z80 per part with
labels and comments, the converter that made its tables, a build whose DSK is byte for byte the
release's). It is not ours to redistribute, so it lives **outside the repository** beside the
original's archive, and is cited by path, never pasted.

**Read it before modelling a part** (phX's rules file says so in those words). Coverage still
finds what runs; the source says what it was *meant* to do, names the tables, and settles readings
a disassembly leaves open. **And finish with a source review**: each part's BBC code read against
the source for what the oracles cannot see - the reference's own errors, the fields between two
parts' checks, data the oracle shares with the code. phX's review (2026-11-17, after every
part's oracle passed, with WinAPE's frames beside it) found three defects no oracle had:

- **A fade between two checks** (its `BUGS.md` 9): the CPC fades the static Clown to white over
  fields 3,938-3,958; the port held the full-colour picture and cut to white. The Clown's oracle
  ended at field 3,497 and Epsilon's began at 3,971 (`docs/verification.md`, "Timeline coverage").
- **One row too many** (10): the source's loop draws 127 lines of the logo; the reference, and
  so the port and its expected picture, showed 128. WinAPE agreed with the source.
- **Mid-line palette writes half a microsecond early** (11): the reference's Gate Array model, and
  so every expected picture made from it.

The same reading found the original's own bugs, which then need a decision rather than a
transcription (phX's Balls: an `rra` after a wrapped `add` shifts the carry into an x
coordinate), and confirmed the rest one item at a time (every part's duration and row, the
curve tables byte for byte). The review's first finding came earlier, from the owner: the outro's
dark lines on a real Master were in the reference too, and the source showed why (decision 63,
section 14).

---

## 14. A third reference: the cycle-exact raster demo, checked against WinAPE

**When the effects are the beam's position, the picture machine is the reference.** Neither
logical machine of section 3 applies: the effects are the timing, and a machine that removes it
removes the demo. phX's `phxrun.py` (the kit's `template/tools/cpc/cpcboot.py`, with
`cpcvideo.py`, `fdc.py`, `disc.py`) is a 6128 at CPC timing (`cpctime.py`) with a
6845 at character resolution, the Gate Array, the uPD765 and the disc (section 15); it boots the
DSK and records each field's picture, CRTC and I/O. **Pick the CRTC type the demo's own test
selects**: phX's loader tests the CRTC and takes per-type paths, and the reference answers type
0, the Hitachi-style part closest to the BBC's (decision 5).

**Check it against a third-party emulator as a Layer 1 gate, automated, before any part rests on
it** - not "provisional until release". phX's gate (`docs/winape-check.md`):

- `winape_shot.ps1` drives WinAPE 2.0b2 (a 6128, CRTC type 0, no Plus, no PAL filter) through
  the whole demo from its DSK, a capture every 0.5 s: 658 captures, 0-330 s. WinAPE is a Delphi
  application: capture its largest visible window, not the process's main window handle.
- `winape_match.py` finds each capture's field in the reference (run one field at a time from
  checkpoints) and diffs it pixel by pixel at the CPC's three levels a gun, writing a match table,
  WinAPE's frame of each field (the frames to check the BBC by) and a three-way sheet per part.
- **The result**: identical in 161 of 163 captures of the Clown, Epsilon, the cube, the tunnel,
  Freddy, the Fishes and Condense and, after one fix, 177 of 177 of the outro; the residue was a
  raster line in the logo, a byte column of the plasma (a Gate Array write half a microsecond
  apart), single beam-race pixels, the Kefrens bars a line late in WinAPE, and WinAPE's top line
  black in every part. Between loads the timeline kept step to within 2 fields over a whole act;
  the loads did not (the Clown's took ~2.0 s longer in WinAPE, Freddy's ~1.0 s and the Fishes'
  ~2.6 s shorter: two drive models, and neither yet a real drive). The demo ends and restarts where the reference says.
- **The fix it forced** (decision 63): the outro's rows came out with their scanlines in the
  order (2, 0, 1) and a dark line through the text; the source says routine VLC*k* shows scanline
  *k*, WinAPE shows that, and the reference's CRTC model was a line out. The converter now
  follows the source ("a correction to the original, not a deviation"). **The reference
  is not an independent oracle**: the BBC copied its mistake into an expected picture that
  agreed with the port.

**List every reference field that is not 19,968 us, and decide each.** A cycle-exact original
drops a VSYNC where a part's race is lost, and its part changes run long or short. phX's first
pass: field 0 (15,360 us), 431-432 (8,432 + 11,486), 837, 882, 927 (19,840: the analyser),
3,299-3,300 (19,299 + **40,605**: the Clown's first stretch writes R9 a microsecond late and a
VSYNC is missed), 3,430, 3,976, 6,521, 6,914, 8,441, **8,448** (39,902: a second missed VSYNC, at
Flipscroll's start), 9,216, 9,231, 9,990, 10,420, 14,865, 15,170 - part changes, all of them.
Decision 10: **every BBC field is 50 Hz with its VSYNC**, and a 40 ms CPC field is two ordinary
BBC fields. The two missed VSYNCs are exactly the points to look at in the third-party
emulator's debugger.

---

## 15. Multi-load demos: the disc is the specification

**Boot the disc, and model the drive.** phX's first FDC model made seeks instant and caught
every track's first sector; the demo then crashed at field 6,569 - a sector loaded over the music
unpacker one frame before the first tune retired it. During a load the CPC plays one music frame
per sector, plus one a field from the interrupt only while the loader waits with interrupts on,
so **the music's lead over the load is set by how long the first sector after each seek takes**.
Modelling the 765's step rate (12 ms, AMSDOS's, from memory) made the loader miss sector 1 after
each seek and wait most of a turn, about ten frames more per track, and the demo ran to its end
and restarted (`phx/docs/layer-1-reference.md`). The specification of a multi-load demo is the
DSK **and** the drive that reads it: the format's gaps and ID positions (the zip's HFE image
had them), the step rate, the overrun deadline.

**Vary the disc, because a real one is not phase 0 at 300 rpm.** Runs at index phase 0, 40 and
120 ms and at 297 and 301.5 rpm moved the end of the Clown's load by up to 75 fields, and at 120 ms
and exactly 300 rpm **the demo hung**: every overrun was the first byte of a track's sector 1, lost
while the music interrupt ran; at 300 rpm a turn is 10.016 fields, so each retry met the interrupt
in the same place, up to four turns in a row, and the Clown's wait for the music's frame counter to
*equal* a value was passed. Half a percent off speed breaks the lock. So the reference keeps
phase 0 and 300 rpm, where nothing locks, and says so; `--index-phase` and `--rpm` are there to
look further.

**The clock is music time, not CPC fields** (phX decision 33). During a load a CPC field carries
0 or 2 music frames, and the parts after it wait on the music's frame counter, so the demo's
timeline is the music's own. The BBC plays one frame a field and keeps the CPC's silent load gaps
at their lengths (218 and 319 rows): **BBC field = L + row**, L the field the music starts, every
part on its CPC music row. Extract the AY stream in music time (one row per frame, in order) and
the CPC's irregular fields vanish: tune 1 ends 12 BBC fields earlier than the CPC's field count,
and nobody hears the difference.

---

## 16. A demo sequence: the backbone first

A 4K demo is one effect at a time. Eighteen parts in 128K and four disc windows are not: **design
the backbone before any part is built** (`phx/docs/design-backbone.md`), and build it with
placeholders.

- **The clock and the timeline**: each part's first and last row, its entry from the part before
  (seamless, black fields, a static screen), cycle-counted or static.
- **Memory over time**: every region of the machine, each part's need, residency act by act, and
  the peaks (phX: the start of the logo, all of act 1 resident; the start of Multi-FX).
- **The hand-overs**: where the CPC shows no black between two parts, both screens must be in
  CRTC-visible memory at once, in disjoint places, and the next part's `enter` runs in the
  vertical blanking of the last field before. **Heavy set-up is a background job** run in the
  main loop during earlier parts (the CPC's own "unpack the next part in spare time"); the switch
  field runs the `enter` and the first update, nothing more.
- **The disc windows** (below), with **placeholder files at each part's estimated packed size**,
  so the load margins are measured before the parts exist. phX's B4 measured them (jsbeeb 2.10.2,
  2.21.1 identical; beebjit's drive a little faster): W1 +17 fields (the card simply waits), W2
  +347, W3 +93 (the tightest hard deadline, as designed), W4 +176.
- **Parts solo, then merged**: each part built and checked on its own branch by a one-part build
  (`main.6502` builds one part, `phx.6502` the sequence), then merged into the sequence in demo
  order, its oracle taking a field offset so it runs on both. Placeholders keep every part's rows,
  black fields and music, so the whole demo plays from the first day.
- **WIP part-select keys and a load-margin readout, on the WIP disc only** (decision 37): a jump
  reloads its window first (110-516 fields a jump), runs the jobs the part depends on, and starts
  the music at its row. A playtester reaches minute four without watching minutes one to three.

**The disc only behind static screens** (decision 32), as the CPC itself loads. A 1770 FM byte
arrives every 64 us by NMI, which `SEI` does not mask: a 35-cycle NMI at a phase that drifts
against the raster, inside every counted line. A sector (16.4 ms) does not fit the 2.7 ms vertical
blanking. So phX loads in four windows, the CPC's own (the loader card, the Clown's static
picture, Freddy and the Fishes after their reveals), checks that every NMI and every 1770 command
fell in a window field (`verify_disc.mjs`), and **warms the drive with a seek about 40 fields
before each window**, landing its one NMI in the vertical blanking. Two lessons about the loader:

- **Chain it on its own interrupts.** A loader whose next command waits for the main loop or an
  IRQ loses a revolution whenever an IRQ outlasts the gap before sector 0 (phX B4: a placeholder's
  5K-cycle draw). phX's issues every next command from the NMI: the seek's INTRQ issues READ
  ADDRESS, the ID's the first run (the next sector to the end), the run's last byte the second run
  (sector 0 up to it): one revolution and a sector whatever the track skew, and a turnaround that
  no IRQ's length can move. A 40-field watchdog restarts a track from its ID.
- **Put the owner's real Master in the loop from the disc-driver step** (decision 36), with a
  Gotek and a real drive. A real 1770 raised READ ADDRESS's INTRQ at once after its sixth byte -
  jsbeeb at least 48 us later - and the first chained loader hung on it (`docs/gotchas.md`).

A two-sided `.dsd` (decision 58: the later windows on side 1, from the cylinder where side 0's
files end, so the head only moves inward) is laid out by the build.

---

## 17. Colour for a big CPC demo

Section 10's rules hold; eighteen parts add these, each a phX decision taken before the part was
built:

- **One fixed checker** (decision 8): RTW's pair for each CPC colour, pixel (x, y) taking half
  (x + y) AND 1, fixed to the screen - even where the CPC artwork is itself dithered on the same
  phase and shows one half only (the Clown's olive came out 93% green). Alternating each colour
  against itself restored the hue but was judged too noisy.
- **The checker travels with moving rows** (9, 12, 27): where a picture moves by rows (the logo,
  the Clown's stretch, the plasma's logo, Flipscroll's scroller, the outro), each row keeps its
  stored checker wherever it lands, so it can be out of step with the screen's - one stored copy,
  not one per phase.
- **CPC mode-1 parts are BBC MODE 1** (19): 384 pixels kept, each CPC pen a solid BBC colour, the
  best 4 of the 8 per part (per line where the CPC rasters pens per line). Where the nearest
  colour by a metric breaks a hue family, **map by hand** (47: lavender to blue, olive to green,
  not CIE76's magenta and yellow).
- **Fades are ladders** (15, 64): a CPC fade to black steps each logical colour down white,
  yellow, cyan, green, magenta, red, blue, black from where it starts, on the CPC's own step
  fields; a fade to white is the same ladder upwards. Not the CPC's intermediate colours, which
  the stock BBC does not have.

---

## 18. RVI on the Master

phX's decision 11: **a row that must start mid-character is done by RVI** (vertical rupture
interlace: one-scanline CRTC frames, each pointed anywhere), not by copying; memory to show beyond
main RAM comes from shadow RAM, with code and data in ANDY and HAZEL. What the real Masters taught
(`phx/docs/hwtest.md`, `layer-3-6845.md`):

- **Each R0 write in its one 1 MHz slot** (R0 = 1 at C0 0 or 1): one slot late or early and the
  line runs on to C0 255. CRTC writes land on 1 MHz boundaries (jsbeeb), so cycle-count the lead,
  then measure every write's C0 in a harness.
- **The burnt lines display**: with R1 above a short line's R0 the display stays on, and their
  characters show as strays. Blank them with a **black left-hand column** in the memory they
  show (13), simpler than the teletext-bit blank.
- **Never light the back porch** (41): a burnt line that shows colour after HSync shifts an RGB
  monitor's black-level clamp. On KC's Sony every colour of the picture went wrong; the CUB was
  unaffected. Burnt lines show black from HSync's start to the end of the back porch (about 8
  characters after HSync).
- **End every frame on the long line** (test L): a 6845 frame ending on an R0 = 1 (2-character)
  line lost sync on the Sony and bent on the CUB. jsbeeb, differently, never ends a frame there.

Each of these was found by a numbered test on the hardware-test disc (`PORTING.md` section 12),
and none by an emulator: no emulator models a monitor.

---

## 19. Music offline: the AY stream for a raster demo

Section 9's `ay2sn` runs on the 6502 every field. A cycle-exact demo cannot spare its interrupts,
so phX converts **offline** (the kit's `template/tools/music_extract.py`, `music_convert.py` on
`py/beeb_port_kit/ay2sn.py`, `music_pack.py`, with the tunes and bass sections in a JSON config:
`music_config_example.json`; skill `beeb-ay-offline`) and the 6502 only replays bytes:

- **The stream**: one record a field, a count n then n bytes exactly as the SN takes them (tone
  latch and data, attenuation, noise control), only what changed against what the chip holds - a
  tone changed while silent is sent when it is next heard; tone 2 is always sent while it clocks
  periodic noise. Each tune packed from a fresh chip so it can start alone. The whole demo:
  14,691 records, 52,128 bytes raw, 15,713 ZX02, never more than 10 writes a field; the tick
  measured 540 cycles worst, 167 mean.
- **Periodic-noise bass, always** (decision 4): no software-bass interrupt, so nothing interrupts
  a counted line. The bass voice is periodic noise clocked by tone 2 at N/15 whatever its pitch;
  a drum takes the noise for at most its first 4 fields and the bass rests meanwhile (KC's ear:
  the kit's rule, bass to noise only below the floor, switched timbre too often); other channels'
  notes below the floor rise an octave at a time.
- **The envelope as a timbre**: Factor6's tunes write R13 = 12 (the repeating sawtooth) at a tune's
  start and lock the envelope period to the tone (tone 703, envelope 22: 22 x 32 = 704), so the
  tone gives the pitch and the envelope only the buzz. Such a channel becomes a square at full
  volume at its tone's pitch (at the envelope's own, period x 16, if its tone is off). Stepping the
  envelope once a field cannot work: the sawtooth repeats at the tone's own audio rate.
- **The bass channel by section** (decision 65): measured as the lowest audible tone per frame
  over every tune, tune 1's bass moves from A to B at row 4,159 (where A starts a 7-step arpeggio
  glitch) and tune 3's from B to A at 13,176. `BASS_SECTIONS` in the converter holds the
  boundaries; each section converts alone with the chip state carried across.
- **WAVs for the owner's ear**: the AY as it plays (envelope included) and the SN as the BBC will,
  the whole stream in music time with the gaps silent. The bass and drum rules were settled
  by KC listening to the two side by side, not by a metric.

---

## 20. Order of work

0. **Layer 0**: the kit's template, the original's archive outside git, `extract_original.py` in
   the build, the depacked 64K image (or, for a multi-load demo, the DSK and a drive model), the
   tools in `template/tools/cpc/` adapted to its entry; the source, if it exists, outside git
   beside the archive.
1. **Layer 1 - the specification**: coverage and `covdis` reading; the field-locked or
   free-running question; `cpcrun` contact sheets; the logical reference with its decision; every
   effect a model scored N of N; the AY's register use measured; `LD A,R` searched for.
   A cycle-exact demo: the picture machine booting the disc as the reference, the WinAPE gate
   run on it, every odd-length field listed and decided, the source read part by part.
2. **Layer 2 - music**: the player on the 6502 against the model's tick state, `ay2sn` at the
   source machine's clock, the SN writes against the model, both models.
3. **Layer 3 - display**: the fires, the rings sized by replay, the frame length, write windows
   measured, every field's CRTC program checked against the reference.
   With it, the hardware-test disc (`PORTING.md` section 12) for every knife edge the parts will
   stand on, on the owner's machines and monitors.
3b. **A multi-part demo: the backbone** (section 16) - the sequencer, every part a placeholder at
   its rows, the whole music, the disc windows with placeholder files and their margins, the real
   Master in the loop from the disc driver; then the parts, each solo and then merged, in demo
   order.
4. **Layers 4 onward - the effects**, each against the model's records, with the slack (or the
   late count) printed and floored.
5. **Colour**: the palette's behaviour measured, the stock re-dither with its own reference, the
   NuLA set, one disc.
6. **Release**: the suite on both models and sets and both jsbeeb versions, b2 and real hardware
   (neither 4K demo has been seen on either; phX was on KC's Masters from its first disc), a
   source review where there is a source (section 13), the WIP published.
7. **The crunch**, if size matters: the measuring stick, the identical-image rounds, generation,
   then deletions measured one at a time (skill `beeb-crunch`).
