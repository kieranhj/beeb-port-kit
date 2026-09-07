# Porting a C64 game to the BBC Micro

*The playbook. What two ports proved, written so the third starts from here.*

This is the method that took **Paradroid** (Model B, 34 days, 406 commits) and **Edge Grinder**
(Master 128, 5 days, 66 commits) from a C64 original to a playable BBC Micro disc. The second port
reused the first's process wholesale, and that is why it took a week where the first took a month.
What the second port still had to rediscover is what this kit packages.

It is written to be read by a coding agent, with a human directing it, and it assumes the
agent knows 6502 and BeebASM (the kit assembles with Baron, its successor - see
`docs/toolchain-baron.md`). That is why it is dense: an agent that has read all of this
measures instead of guessing. A human reader wants the one-page summary in
[`README.md`](README.md) instead. The hardware numbers are in
[`docs/hardware-facts.md`](docs/hardware-facts.md), the mistakes in
[`docs/gotchas.md`](docs/gotchas.md), the measuring methods in
[`docs/verification.md`](docs/verification.md), and the section at the end says how the two
ports actually ran with Claude Code.

The two ports are public and this document links into them for the worked examples:
[paradroid-beeb](https://github.com/kieranhj/paradroid-beeb) and
[edge-beeb](https://github.com/kieranhj/edge-beeb). Their `docs/` directories are the long form of
everything here.

---

## 1. The four rules

Everything else follows from these. They were set on the first day of the first port and neither
port found a reason to relax them.

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

---

## 2. Before you write any code

### 2.1 Get the specification and prove which one it is

You need the original's source, or a disassembly you can trust.

- Edge Grinder had 5,000 lines of clean, commented source (Cosine's Format War entry). That is
  the easy case: transcribe.
- Paradroid had a disassembly. It took two days to establish *which* Paradroid it was: the
  project believed it was the Redux build until all four C64 releases were unpacked under VICE
  and diffed against the listing (82 % match to the 1985 original). Do this on day one. A
  disassembly of the wrong version is a specification for a different game.
- **Verify the copy of the specification you read from.** Paradroid's annotated listing was
  produced by a script that silently dropped tab-separated byte columns: 43 % of the original's
  data tables were missing and the survivors misaligned, for three weeks, before a check script
  (`tools/verify_annotation.py`) caught it. Any tool that rewrites the source needs a
  round-trip check beside it.
- A screenshot of the original beats a model of it. Paradroid's play area was believed to be
  multicolour through three successive wrong models until someone looked at the C64 running.
  Keep reference screenshots in the repo (gitignored if they are not yours to redistribute).

### 2.2 Choose the machine

The baseline is a **BBC Model B with at least 16K of sideways RAM**, not necessarily 64K. Use
as few banks as the game can be made to fit in: every bank you require removes people who can
run it on real hardware. Paradroid needs four and that was a cost, not a target. The Electron has
a different set of constraints and is out of scope here.

**RAM will be tight for the whole port, whatever the machine.** Every source machine has more
base RAM than the BBC (the C64 64K, the Spectrum 48K), so the fight is not a phase that ends but
the condition the work is done under. Three consequences, all learned the hard way:

- Keep `docs/memory-map.md` reasonably current. It need not be byte-perfect after every commit,
  but it must not drift far: Edge Grinder's runtime table drifted into a region rewritten every
  frame and went four layers unnoticed.
- Expect to make quality and design decisions on RAM grounds, and record them as decisions:
  fewer sprite frames, a smaller panel, trading RAM for cycles and accepting the performance hit.
- The BBC's floppy drive is fast, reliable and effectively universal, so multi-part loading is
  feasible in a way it was not on the source machines. It is still disruptive. Treat it as a last
  resort and confine it to clean seams: loader, titles, main game, and nowhere inside play.

Some games will be Master-only, and you should decide that on day one rather than discover it in
week three. Edge Grinder's decision 1 is the model: its one-pixel scroll needs two full 16K
screens inside a hardware wrap region, one in main and one in shadow RAM. A Model B has one wrap
region and no shadow. Paradroid costed sub-4-pixel scrolling on a B, rejected every option, and
shipped 4-pixel steps.

What the Master gives you, measured in the Edge Grinder port: 20K of shadow RAM for a second
screen or a staging area; ANDY (4K at `&8000`) and HAZEL (8K at `&C000`) as extra RAM at the cost
of some MOS rules; four sideways banks you can assume are 4 to 7. What it costs: the B+, the B
and the Electron.

What Paradroid's Model B memory fight taught, and Edge Grinder's rules file says in as many words:
**do not adopt the Model B contortions unless a measurement says you must.** The low overlay in
DFS workspace, the snapshot of the filing system's workspace around a `*LOAD`, the in-place font
unpack with a measured landing address, the stack-page scavenging: each of these cost a bug, and
each exists only because the B had fifteen bytes free.

### 2.3 Write the proposal

Edge Grinder started with a written proposal
([`PROPOSAL.md`](https://github.com/kieranhj/edge-beeb/blob/master/PROPOSAL.md)) that read both
codebases, corrected five errors in the existing docs, tabulated what the previous port's practices
were and whether each transferred, proposed a memory map and a layer plan, and ended with five
decisions for the owner to take. It was written in a day and it is why Layers 0 to 2 took an
evening. Its "transfers?" table is the part to copy:

| Practice from the last port | Transfers to this one? |
|---|---|
| The original is the spec; decisions listed per layer | Yes, verbatim |
| One layer at a time, no HAL | Yes |
| Emulator for measuring, not recalling | Yes |
| Verify against the buffer, not the screenshot | Yes |
| Circular-strip play buffer with hardware wrap | Already how the old code worked |
| Three-cycle rupture for a static panel | Yes, cut to two cycles |
| Own IRQ1V, keyboard direct from the VIA | Yes |
| Sprite slot model, save-area geometry, mask from data, deferred-carry `SCANSTEP` | Yes |
| Tranche split and window scheduling | **No**: it exists only because the old port was single-buffered |
| Disc compression, `make_disc.py`, padded SSD, debug flags named at boot | Yes, lift the tools (compress with ZX02, not ZX0: half the depacker, twice the speed, +0.11% on size) |

Fill this in for your game and you have most of the plan. Section 5 of this document is the
list of patterns to consider.

### 2.4 Decide the scope of what is *not* the original's

The C64 Edge Grinder has no sound effects; the port added none. Paradroid's Redux features were
triaged one by one and most rejected for version 1.0. ESCAPE ending the game was accepted as a
port feature because it exercises the whole death sequence. Write these down as decisions too.
The rule is not "add nothing"; it is "add nothing quietly".

---

## 3. The artefacts

Both ports run on the same seven files. Each earned its place by a failure it caught.

| File | Job | Rule |
|---|---|---|
| **The rules file** (`CLAUDE.md` in both ports; call it `HACKING.md` if you are not using Claude Code) | Standing rules, the measured hardware facts, the memory outline, the build commands | Read at the start of every session. When a fact in it is wrong, fix it the same day: Paradroid's carried "jsbeeb will not boot an unpadded SSD" for a week after it was disproved |
| `PLAN.md` | What is left, and nothing else | Cut it when it stops driving the next decision. Paradroid's went from 535 lines to 156. Detail moves to `docs/` |
| `docs/decisions.md` | One table: every deviation from the original and every choice the hardware forced, numbered, dated, with the reason and a link | **This is its only copy.** An earlier era kept one in `PLAN.md` too and the copy fell out of date. Nothing is re-litigated without a new row saying why |
| `docs/layer-N-*.md` | Working notes per layer: what was measured, what was tried, what was costed and rejected | The rejected options are the valuable half. "Do not re-litigate the blitter unrolls" saved the RAM pass from repeating itself |
| `BUGS.md` | Defects with evidence, numbered | Fixed entries are never deleted; they record what was ruled out. Paradroid #5 and #6 is the model entry: two correct measurements supporting a wrong conclusion, and why |
| `docs/memory-map.md` | Every region, what is in it, how much is free, measured from the listing | Kept reasonably current through the whole port, because RAM is contended through the whole port. Every free-space figure says the date it was measured. "Take live figures from the build output, never from this paragraph" |
| `!BOOT` | Stamps the assembly time and names every debug flag that is on | A build cannot lie about itself. Add every flag to the stamp and to `DEBUG_ANY`; assert `DEBUG_ANY = 0` under `RELEASE` |

Commit slicing follows the same shape: one mechanism per commit, with the measurement in the
body ("byte-identical over 40 passes", "0 of 10,240", before-and-after cycles). Doc-sync commits
are separate and frequent.

---

## 4. The layer plan

Both ports went through the same sequence, whatever the game. Each layer is done when it is
visible in the emulator and its doc, decisions rows and plan update are written. The links are to
the layer docs in the two ports; read the relevant one before starting the layer, because each
records what was tried and rejected.

| # | Layer | Done when | Worked examples |
|---|---|---|---|
| 0 | **Toolchain.** Repo layout, build script, disc post-processor, emulator connected, docs skeleton. If there is existing code, split it into `src/` and prove the binary is unchanged | Same binary builds from `src/`; the docs are corrected; `PLAN.md` exists | [edge L0](https://github.com/kieranhj/edge-beeb/blob/master/docs/layer-0-toolchain.md), [paradroid L0](https://github.com/kieranhj/paradroid-beeb/blob/main/docs/layer-0-toolchain.md) |
| 1 | **Data pipeline.** Rip the original's graphics and tables, convert offline, commit the output, render it back to PNG to check | The game's data is in `src/data/`, regenerated by tools, and a picture of it matches the original | [edge L1](https://github.com/kieranhj/edge-beeb/blob/master/docs/layer-1-graphics-pipeline.md), [paradroid L1](https://github.com/kieranhj/paradroid-beeb/blob/main/docs/layer-1-graphics-pipeline.md) |
| 2 | **Display.** Screen mode, the CRTC rupture for the panel, own IRQ handler, frame lock, palette, direct keyboard | A static screen with the panel above the play area, at the target frame rate, keys read | [edge L2](https://github.com/kieranhj/edge-beeb/blob/master/docs/layer-2-display.md), [paradroid L2](https://github.com/kieranhj/paradroid-beeb/blob/main/docs/layer-2-static-render.md) |
| 3 | **Scroll or render.** The play area drawn from the map, scrolling if the game scrolls. **Build the buffer oracle here** (section 6) | The level scrolls end to end with 0 bytes of difference against the oracle at every awkward position | [paradroid L3](https://github.com/kieranhj/paradroid-beeb/blob/main/docs/layer-3-scroll.md), the port's largest doc and most of its CRTC knowledge |
| 4 | **Sprites.** The engine, measured: cycles per sprite, slots, save and restore | N sprites moving at the target rate with the cycle counts recorded | [edge L3](https://github.com/kieranhj/edge-beeb/blob/master/docs/layer-3-sprites.md), [paradroid L5 blitter](https://github.com/kieranhj/paradroid-beeb/blob/main/docs/layer-5-blitter.md) |
| 5 | **Player.** Movement, controls, collisions with the background, the original's speed model transcribed | The player moves and dies as the original's does | [edge L4](https://github.com/kieranhj/edge-beeb/blob/master/docs/layer-4-player.md), [paradroid L4](https://github.com/kieranhj/paradroid-beeb/blob/main/docs/layer-4-player.md) |
| 6 | **Game logic.** Enemies are usually the bulk of it, with the original's tables verbatim and its AI or wave manager, but it is everything the original's game loop does that is not the player: combat, doors, lifts, pickups, timers, scoring rules | The level is playable | [edge L5](https://github.com/kieranhj/edge-beeb/blob/master/docs/layer-5-enemies.md), [paradroid L6](https://github.com/kieranhj/paradroid-beeb/blob/main/docs/layer-6-droids-live.md), [L7](https://github.com/kieranhj/paradroid-beeb/blob/main/docs/layer-7-combat.md) |
| 7 | **Game flow.** Lives, score, HUD, the state machine, titles, game over, completion | The full loop from boot to game over and back | [edge L6b-6e](https://github.com/kieranhj/edge-beeb/blob/master/docs/layer-6c-state-machine.md), [paradroid L9](https://github.com/kieranhj/paradroid-beeb/blob/main/docs/layer-9-hud.md), [L11](https://github.com/kieranhj/paradroid-beeb/blob/main/docs/layer-11-sound-title.md) |
| 8 | **Sound and music.** See section 9 | The tune plays from the interrupt; effects if the original has them | [edge L7](https://github.com/kieranhj/edge-beeb/blob/master/docs/layer-7-music.md), [paradroid L11e](https://github.com/kieranhj/paradroid-beeb/blob/main/docs/layer-11e-sound.md) |
| 9 | **Loader and disc.** Compression, load order, boot blanking, the loading screen | Boot time measured; the disc is the release layout | [edge L9](https://github.com/kieranhj/edge-beeb/blob/master/docs/layer-9-loader.md), [paradroid loader](https://github.com/kieranhj/paradroid-beeb/blob/main/docs/loader-compression.md) |
| 10 | **Art.** The hand-authored pass and the pipeline for it. See section 8 | The artist's sheets go in through a validated path | [edge L8](https://github.com/kieranhj/edge-beeb/blob/master/docs/layer-8-art-pipeline.md), [paradroid L14](https://github.com/kieranhj/paradroid-beeb/blob/main/docs/layer-14-visual.md) |
| 11 | **Balance, memory, compatibility.** Verify before tuning; the RAM pass; real hardware; other machines | Plays like the original by measurement; runs on the machines it claims | [paradroid L12](https://github.com/kieranhj/paradroid-beeb/blob/main/docs/layer-12-balance.md), [L13](https://github.com/kieranhj/paradroid-beeb/blob/main/docs/layer-13-compatibility.md), [ram pass](https://github.com/kieranhj/paradroid-beeb/blob/main/docs/ram-pass.md) |
| 12 | **Release.** Release build, redefinable keys, pause, the padded disc, publication | Version line in `!BOOT`, every debug flag off, tested on hardware | [edge L9h](https://github.com/kieranhj/edge-beeb/blob/master/docs/layer-9h-keyredef.md), [paradroid L11f](https://github.com/kieranhj/paradroid-beeb/blob/main/docs/layer-11f-frontend.md) |

The order is not sacred. Paradroid moved doors and lifts ahead of the droid layers when it helped.
What is sacred is finishing a layer, with its doc, before the next one starts.

**Where the time goes**, from both histories, in order of size: memory (Paradroid from day 12
onward, Edge Grinder from Layer 6e onward, in both cases after the port believed the problem was
solved); music (three passes in Edge Grinder); performance re-litigation caused by an earlier
measurement being wrong (a sign bug made Edge Grinder's Layer 3 counts 45 % optimistic); and
chains of corrections where one inferred fact was built on.

---

## 5. Architecture patterns that transfer

These are the designs both ports share. They are patterns, not library code: the second port's
sprite engine shares its design with the first's and 4 % of its lines. The measured reasons are in
the layer docs linked above.

### 5.1 The play area is a circular strip under hardware wrap

The CRTC's address translator wraps the display at one of four sizes set by the System VIA's
addressable latch (20K, 16K, 10K, 8K; see the facts file for the settings). Put the play buffer in
that region, scroll by moving the CRTC start address, and draw only the leading edge. The display
window must fit inside **one** wrap: the translator subtracts once. Paradroid's 10K strip is 16
rows exactly, so smooth vertical scrolling cost a row of play area.

On a Master, Edge Grinder holds two copies of the strip, main and shadow, half a byte out of
phase, and flips the displayed bank every field. A CRTC step in MODE 2 is two pixels; the odd
pixel is the other bank.

### 5.2 A static panel above a scrolling area is a CRTC rupture

Two or three CRTC cycles a field: the panel at a fixed address, then the play area at the
scrolling address, with VSync in the last cycle. The System VIA's T1 timer fires the stage
changes; the handler is a small state machine indexed by stage. The register write-window rules
are the whole difficulty. The principle is that a register must be written before the counter
that compares against it reaches the value: R4 in its own cycle before C4 gets there; R6 and R7
likewise inside the current cycle as long as the row they name has not already passed, which in
practice means the previous cycle whenever the row is early; R12/R13 are latched at cycle start
so always the previous cycle; R5 never near a boundary. Fires that blank or unblank
must land in horizontal blanking, and the phase is measured with a cycle counter modulo the
scanline. Both ports' `rupture.6502` carry the table in their headers.

A rupture with one shape is easy to hand over between screens. A rupture with **two** shapes (Edge
Grinder's titles use four cycles and switch the display bank mid-frame) needs the switch made
atomically inside the VSync handler, and that was the one bug still open when this was written.

### 5.3 Own IRQ1V outright

Take the interrupt vector, service VSync and T1 yourself, and give the MOS nothing. No MOS tick, no
OS sound, no OSBYTE keyboard. Consequences, all measured: filing-system calls must happen before
the takeover (DFS needs the MOS interrupt); the MOS's sound workspace at `&0800` is yours only
while you hold the vector, so flush the buffers before handing back; and on a Master, HAZEL is the
filing system's workspace, so if you take it, BREAK must be a power-on reset (`OSBYTE 200,3`) or
the next boot finds no DFS.

One thing neither port measured and a future one should: whether DFS needs the MOS to service the
VSync interrupt to work correctly. Both ports load everything before taking the vector, so the
question never arose. What is known is narrower: in jsbeeb the 8271 poll hangs if the CRTC stops
producing VSync at all.

The frame lock lives in the VSync handler: the main loop parks a finished frame and a ready flag,
the handler flips the display when `FRAME_LOCK` fields have passed. A slow frame costs whole
fields, never a tear. Edge Grinder ticks the game logic twice per display frame so the C64's 50 Hz
constants transcribe unaltered at 25 Hz.

### 5.4 Keyboard direct from the VIA

Drive the keyboard matrix through the System VIA (latch line 3 down, `DDRA = &7F`, key number to
the no-handshake port, read bit 7 back): 69 cycles against OSBYTE's 243. The internal key
numbers are a table, measured once and kept in
[`docs/hardware-facts.md`](docs/hardware-facts.md) section 7; use it, and measure only a key that
is not in it (SHIFT and CTRL are below OSBYTE 121's floor and need the INKEY route). Redefinable
keys are a release feature in both ports and are why every debug key needs CTRL.

### 5.5 The sprite engine

Eight slots (the C64's arrangement), each owning a save area. The five ideas that transferred:

1. **The save area mirrors the screen's geometry**, so one index addresses both the buffer and the
   save, and restore is the draw replayed.
2. **The mask comes from the data byte.** Logical colour 0 is transparent everywhere; black inside
   a sprite is a second logical black (8 in MODE 2). Fixed roles for the logical colours is what
   makes a sprite byte its own mask. Paradroid did the same with MODE 1's four colours.
3. **Pre-shifted copies**, one per pixel phase, in sideways banks laid out identically so the
   engine adds the shift to the bank number and every address is the same.
4. **`SCANSTEP` with the page carry deferred**: step the pointer down a column without a 16-bit add
   per scanline. Worth 668 bytes in Paradroid's bank when it was adopted.
5. **Restore all, scroll, draw all**, in that order, and restore in reverse draw order.

Compile only what is always on screen (the player, the bullet) and interpret the rest with bounding
boxes, but **measure first**: Edge Grinder deferred compiling until Layers 4 and 5 showed the
real load, and its interpreted engine was cheap enough. Clip at the edges rather than cull if
things enter from off-screen; culling makes them pop.

A wrap that is not row-aligned (16,384 / 640 = 25.6 rows) means a sprite's columns can straddle
the buffer end. Test once per sprite, not per row, and take the cheap path when it cannot.

**Neither port has explored the other BBC sprite schemes**, and a game with a different balance
of sprites to background should cost them before copying this one:

- **Two 2bpp layers in a 4bpp mode.** Split the four bits per pixel into a background plane and a
  foreground plane and plot sprites with EOR, so drawing and erasing are the same operation and
  there is no save area at all. It halves the colours available to each layer and changes the
  whole art pipeline, which is why a port that inherits a 16-colour original did not take it.
- **The Exile plotter.** Zero-page addresses chosen to match the pixel byte masks, so the address
  of a palette entry *is* the mask that selects it and the inner loop loses its lookups. It
  combines with the layered scheme above, and it is the same family of trick as Paradroid's
  mask-from-data.

### 5.6 Sideways RAM

Put code beside the data it reads. "The constraint was code space, and moving code into a bank
fixed it, repeatedly" (Paradroid). The rules, each learned the hard way: bank code may call main
RAM, main RAM may call a bank only with it paged in, and nothing may page its own bank out. The
interrupt handler touches no bank unless it saves and restores the selection itself. On a Model B,
probe the banks at boot and take the highest four; do not assume 4 to 7. On a Master they are 4
to 7.

### 5.7 The disc: compress everything, one resident depacker, load in order

Every data file ships compressed and the loader unpacks it. Boot time in Paradroid went from
14.4 s to 10.4 s; the lever is sectors, not file count. Use **ZX02** (`lib/zx02depack.6502`,
`py/zx02.py`): 131 bytes of depacker against ZX0's 257 and 2.14x the decode speed for +0.11% on
the packed size, measured 2026-09-07 over both ports' data. The two shipping ports are ZX0 discs
because they predate the measurement; `lib/zx0depack.6502` and `py/zx0.py` stay for them. Pick one
format for a project and never mix them - nothing checks that the disc and the depacker agree. There is one depacker and it is resident;
Paradroid had two copies for a while and loaded one of them twice a session. A stream may not be
overtaken by its own output, so an in-place unpack needs a measured margin and the build should
fail if it is violated. On a Master, load the file that takes HAZEL last and touch the disc never
again.

The mode change is the first thing boot does if there is a loading picture and the last if there
is not; either way every load is blanked (R8, and R10 for the cursor) and every screen is revealed
complete.

### 5.8 Memory bookkeeping

`GUARD` every region and `ASSERT` every ceiling, in the assembler, naming the routine. Print a
gauge per region every build. Beebasm's `CLEAR` releases the overwrite guard, and a table that
drifts a page into a region rewritten at runtime assembles cleanly and fails quietly. On a Master
the ceiling for anything read in play may be lower than the ceiling for the image: Edge Grinder's
sprite save area sits above its code, and boot-only code is allowed there because it is dead before
the first sprite draws.

---

## 6. Verify against the buffer, not the screenshot

Screenshots have said "fine" when it was not, in both ports, repeatedly. The check that works is
an **oracle**: an independent rendering of what the play buffer should hold, diffed byte for byte
against what the game drew, at the awkward positions (odd and even scroll units, non-zero
scanline offsets, diagonals, both bank parities). Paradroid's is a full redraw on a debug key,
and nearly every commit message from Layer 3 on ends "0 of 10,240". Edge Grinder promised one in
its rules file and never built it; its layer docs say so from Layer 3 to Layer 5, and that gap is
the one thing to do differently.

Build the oracle in Layer 3, before the scroll is trusted. The recipe, and the traps in it (NOP
*every* draw site, take both dumps inside one pass, let the view settle first), are procedure 3 in
[`docs/verification.md`](docs/verification.md).

The same document has the other checks that proved themselves: breakpoint-pair cycle timing,
frame-drop counting, sound capture matched against a rebuilt reference stream, the byte-identical
build check for a change meant to be mechanical, and the listing-stream diff that proves no
instruction moved. The habit behind all of them: **never check a thing against itself, and say
which oracle a number came from.**

---

## 7. The tool pipeline

Both ports converged on the same shape in Python, with Pillow:

```
rip_*.py      original data  ->  PNG in tools/output/       for eyes
export_*.py   original data  ->  src/data/*.bin, *.asm      committed
render_*.py   src/data       ->  PNG                        the check that the export is right
verify_*.py   anything       ->  pass/fail                  never against itself
make_disc.py  the assembler's SSD -> the bootable disc      compress, relocate, order, pad
```

Rules that came out of using it:

- **`src/data/` is committed**, so an exporter change shows as a diff, and the build script does
  not run the exporters.
- A file the owner will edit by hand (a scroll text, a briefing) is exported once to a text file
  the build reads, and the exporter refuses to overwrite it.
- The renderer that draws the data back is what proves the export and the tables agree; run it
  from the game's own box tables, not the exporter's.
- The disc tool round-trips every compressed stream through a Python decompressor before it will
  write the image, refuses a stream that overlaps its own output, and lays files out in boot
  order.
- The build stamps `!BOOT` with the time and the flags, and the release build is a
  command-line symbol. (BeebASM had no `IFDEF` and no choice; Baron has `DEFINED()`, and the
  kit still passes the flags every time so that a build says what it is.)

The reusable halves of these tools are in this kit's [`py/`](py/) directory. Fork them.

---

## 8. Working with an artist

Edge Grinder's Layer 8 is the reference. The mechanical conversion from the C64's colours is what
the game ships with until the artist starts; the artist repaints a *working game*, seeded from
that conversion, and the pipeline reads PNG sheets at 2:1 (MODE 2's pixels are twice as wide as
tall) with a palette PNG beside them.

- Every sheet carries the logical colours it may use, and the validator refuses an off-palette
  colour, a half-width pixel or misplaced transparency, naming the sheet, cell and pixel. Grey is
  see-through, orange is "not drawn yet" and falls back to the conversion.
- The artist paints characters; tiles and the map are index tables and stay the original's, so the
  256-character budget cannot be overrun. A tool exports any stretch of the level as one picture,
  and imports it back by voting across the instances of each character, refusing a conflict.
- A grid layer, separate from the canvas, shows cell boundaries and the fat-pixel pairs. The
  validator refuses a sheet with transparency in it, transparency being proof it is the guide and
  not the art.
- Exchange by shared folder or e-mail; the port commits. No git on the artist's side.

The decision behind it (Edge Grinder's decision 3) is worth copying: the redraw is free inside
the existing tile boundaries. Detail, gradients and dithering with all the colours, but the
outlines, the character grid, the tile definitions and the map stay the original's, because the
collision tables depend on them.

---

## 9. Music and sound

The C64's SID tune is usually a binary by someone else and does not convert. Both ports found
another route:

- **Paradroid** transcribed the SID effects driver to the SN76489 and has no tune.
- **Edge Grinder** converted the Amstrad CPC port's Arkos Tracker song. Two chains exist and both
  are libraries in their own repositories: a **register log** through
  [vgm-player-bbc](https://github.com/kieranhj/vgm-player-bbc) (offline conversion with whole-song
  analysis, larger data, cheaper decisions) and a **tracker replay** through
  [arkos-player-bbc](https://github.com/kieranhj/arkos-player-bbc) (the AKL, AKM and AKY players
  with the AY-to-SN layer; a fifth of the data, re-voiced at run time). The second repo's
  README says which to choose and why; start with AKM.

Whichever you use, verify it the way Edge Grinder does: capture the sound chip writes out of the
emulator and search for them inside a reference stream rebuilt from the data the build actually
includes. A wrong address plays happily for thousands of frames before it runs off the end.

Do not add sound effects the original does not have.

---

## 10. Release

- `RELEASE` is a build symbol passed on every invocation; `DEV` is its complement; every
  `DEBUG_` flag is folded into `DEBUG_ANY`, which is asserted zero under `RELEASE`.
- `!BOOT` prints the version line in a release and the flag list otherwise.
- Every debug key needs CTRL once the play keys are redefinable.
- Pad the SSD to 200K before publishing; a published size that differs from the last publish is
  a useful signal that the wrong file went out.
- A second emulator before the release candidate, and real hardware before release. jsbeeb is
  the instrument for measuring; **b2 or beebjit** is the second opinion (b-em is no longer used).
  Both ports found things one emulator could not show: a rolled field that only b2 rendered, a
  NuLA register mistake that reached hardware, a mid-frame bank switch that only one emulator
  had been checked on.
- Publish work-in-progress builds to a stable URL so playtesters' links keep working.

---

## 11. What it costs

| | Paradroid | Edge Grinder |
|---|---|---|
| Source | Disassembly, version proved on day 2 | Clean source |
| Machine | Model B + SWRAM | Master 128 |
| Layers 0 to 6 | ~3 weeks | 2 days |
| To release candidate | 30 days | 5 days (art and one music decision open) |
| Commits | 406 | 66 |
| Docs | ~15,000 lines | ~7,000 lines |
| Decisions of record | ~60 in layer docs | 74 in one table |

The gap is the process, carried over, and the machine. The first port's month bought the second
port's week. The purpose of this kit is to make the third port's Layer 0 an afternoon.

---

## 12. How the ports ran with Claude Code

Both ports were built with Claude Code doing the typing and the owner directing, reviewing,
playing and deciding, and this kit assumes the next one will be too. What made that work, in
order of importance:

1. **The rules file is `CLAUDE.md`** and it is loaded every session. The four rules in section 1
   go at the top, in those words. "Do not write hardware code from recalled facts" is the single
   instruction that matters most.
2. **The emulator is connected as an MCP server** (`jsbeeb-mcp`, `.mcp.json` in the repo), so the
   assistant can boot the disc, run frames, read memory, set breakpoints and capture sound without
   asking. Every measured fact in this kit was taken that way.
3. **The owner decides, the assistant builds.** Decisions are asked as numbered questions and
   answered before code; the answers go in `decisions.md`. Taste calls (a speed, a colour, an
   auto-fire rate) are played, not calculated, and the doc says whose number it is.
4. **Bugs are found by playing**, on a second emulator (b2 or beebjit) and on hardware. Most of
   both `BUGS.md` files were reported by the owner or a playtester, not by the assistant.
5. **The skills in this kit** ([`skills/`](skills/)) are the repeated procedures written as
   checklists the assistant can follow: the smoke test, cycle timing, measuring a key or a
   register, the buffer oracle, closing a layer. Copy the directory into your project's
   `.claude/skills/`.
6. **Session memory** keeps the emulator's quirks (it zeroes RAM; memory reads above `&8000`
   return whichever bank is paged) across conversations, so they are not rediscovered.

---

## 13. Where to look in the ports

The documents that were read most often during the second port, and are the ones to read before
the third:

- [Edge Grinder `PROPOSAL.md`](https://github.com/kieranhj/edge-beeb/blob/master/PROPOSAL.md):
  the plan for a port written from another port's experience.
- [Paradroid `docs/layer-3-scroll.md`](https://github.com/kieranhj/paradroid-beeb/blob/main/docs/layer-3-scroll.md)
  and [`docs/raster-timing.md`](https://github.com/kieranhj/paradroid-beeb/blob/main/docs/raster-timing.md):
  the CRTC, the rupture, and how its timing was measured and then corrected on hardware.
- [Edge Grinder `docs/layer-3-sprites.md`](https://github.com/kieranhj/edge-beeb/blob/master/docs/layer-3-sprites.md)
  and [Paradroid `docs/layer-5-blitter.md`](https://github.com/kieranhj/paradroid-beeb/blob/main/docs/layer-5-blitter.md):
  the sprite engine twice, for two modes.
- [Paradroid `docs/ram-pass.md`](https://github.com/kieranhj/paradroid-beeb/blob/main/docs/ram-pass.md):
  what a memory squeeze looks like when it is done by measurement.
- [Edge Grinder `docs/layer-8-art-pipeline.md`](https://github.com/kieranhj/edge-beeb/blob/master/docs/layer-8-art-pipeline.md):
  the artist pipeline and the argument for it.
- [Edge Grinder `docs/performance.md`](https://github.com/kieranhj/edge-beeb/blob/master/docs/performance.md):
  four optimisations costed, three of them net losses.
- Both `BUGS.md` files, end to end.
