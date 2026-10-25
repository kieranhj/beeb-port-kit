# Porting a game to the BBC Micro

*The playbook. What three ports proved, written so the fourth starts from here.*

This is the method that took **Paradroid** (Model B, 34 days, 406 commits) and **Edge Grinder**
(Master 128, 5 days, 66 commits) from a C64 original to a playable BBC Micro disc, and then took
**1942** (Master 128, seven weeks, 483 commits, 161 decisions) from a Capcom arcade board with no
source at all. The second port reused the first's process wholesale, and that is why it took a
week where the first took a month. The third reached Edge Grinder's pace for its first 18 days -
Layers 0-8 for stage 1 in six - and spent the rest on RAM hunts, defects found late by playing,
taste, the oracle suite and a release that kept taking features; the sections below say what
would have saved each. What the ports still had to rediscover is what this kit packages.

It is written to be read by a coding agent, with a human directing it, and it assumes the
agent knows 6502 and BeebASM (the kit assembles with Baron, its successor - see
`docs/toolchain-baron.md`). That is why it is dense: an agent that has read all of this
measures instead of guessing. A human reader wants the one-page summary in
[`README.md`](README.md) instead. The hardware numbers are in
[`docs/hardware-facts.md`](docs/hardware-facts.md), the mistakes in
[`docs/gotchas.md`](docs/gotchas.md), the measuring methods in
[`docs/verification.md`](docs/verification.md), and the section at the end says how the three
ports actually ran with Claude Code.

The three ports are public and this document links into them for the worked examples:
[paradroid-beeb](https://github.com/kieranhj/paradroid-beeb),
[edge-beeb](https://github.com/kieranhj/edge-beeb) and
[1942-beeb](https://github.com/kieranhj/1942-beeb). Their `docs/` directories are the long form of
everything here. A game with no source - an arcade ROM, or any binary you can only run under
emulation - also wants [`docs/arcade-porting.md`](docs/arcade-porting.md).

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

You need the original's source, or a disassembly you can trust - or, when there is neither, the
original's binary running under an emulator you can instrument (section 2.1b).

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

### 2.1b When the original is an emulated binary

1942 had no source and no trusted disassembly: the specification was the arcade ROM, running in
MAME. Every rule above still holds; what changes is that **a ROM read is a hypothesis until it is
scored against a capture of the running game**. The background map format was guessed wrong from
the ROM twice before the tilemap RAM was captured out of the running machine and used as ground
truth. The method that replaced guessing has two halves. **Capture**: per-frame RAM dumps out of
MAME's Lua, and the game DRIVEN to whatever a recording never reaches (a held pending-state byte,
the input read patched in ROM, invincibility through the game's own "already hit" path, an
autopilot over the whole game) - because *a state byte that is constant in the recording has not
been measured*. **Model**: a Python transliteration of each ROM routine, scored frame by frame
against the capture to **0 wrong, every excluded frame named**, and then made the exporter's only
decode and replayed over the port's own trace, so the arcade's oracle and the port's are one
model. [`docs/arcade-porting.md`](docs/arcade-porting.md) is the guide - rotation and named spaces,
the hardware-format traps, DIP switches as a measurement, the ROM checksum, the sound CPU - and the
skills `beeb-arcade-capture` and `beeb-rom-model-probe` are the two procedures as checklists.

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

**Price the WHOLE game's data against RAM in week 1, before the first level is built.** Inventory
every level - its tiles, its map, its sprite pictures, its scripts, its sounds - and put the total,
raw and packed, beside what the machine has, per region. 1942 had the tool that did this
(`tools/inventory32.py`) on its third day, and priced stage 1 alone until its seventh: stage 1's
layout was fixed by then, and the other 31 stages' need arrived as six RAM hunts over the next
month. From then on every feature opened with a RAM ledger ("main RAM 3 bytes; anything new needs
a lever first"). The inventory decides the shape the game streams in (1942: a set of four stages
is one map group plus one breather stage, one file a set, decision 87), what is resident and what
loads at a seam, and whether a feature is affordable at all - questions far cheaper to answer
before the layout than after it. Count the DFS catalogue too: its 31 entries bound before the
sector count did.

Some games will be Master-only, and you should decide that on day one rather than discover it in
week three. Edge Grinder's decision 1 is the model: its one-pixel scroll needs two full 16K
screens inside a hardware wrap region, one in main and one in shadow RAM. A Model B has one wrap
region and no shadow. Paradroid costed sub-4-pixel scrolling on a B, rejected every option, and
shipped 4-pixel steps.

What the Master gives you, measured in the Edge Grinder port: 20K of shadow RAM for a second
screen or a staging area; ANDY (4K at `&8000`) and HAZEL (8K at `&C000`) as extra RAM at the cost
of some MOS rules; four sideways banks at 4 to 7, once its LK18 and LK19 links are set. What it
costs: the B+, the B and the Electron. Of ANDY, the MOS writes three pages: on `*KEY`, on every
mode change and soft BREAK, and on `VDU 23`. All 4K is yours only if you fill it after the last
mode change and never call `*KEY` or `VDU 23` afterwards; `docs/hardware-facts.md`, ANDY, has
the page map.

**Decide on day one whether the game ever reads the disc after it starts** - levels loaded
between waves, music streamed off the disc, a saved high-score table. It decides how the game
and the filing system share the machine, and it is expensive to change late. A game that loads
ONCE calls `OSBYTE 140` when the last load is done, the filing system detaches, and its
workspace and zero page become the game's. A game that keeps loading can never call it (there
is no way back from the tape filing system): it keeps the filing system live, owns the machine,
and makes NO OS call at all for as long as it runs. `lib/loader.6502`'s header has the contract
and `docs/hardware-facts.md` the evidence - a port that got this wrong hung on real hardware.

**On a Master there is a third answer: own the 1770 yourself.** 1942 loads through the DFS at
boot only, then calls `OSBYTE 140` like a load-once game - and every later load, at every stage
seam, goes through its own disc driver (`lib/qdisc.6502`, from scarybeasts' quicdisc): the WD1770
driven direct, NMI-fed at 35 cycles a byte, non-blocking, with the catalogue cached at boot. So
the filing system's workspace is freed as if the game never loaded again, the game keeps its
interrupts and its rupture running through a load (a seam holds the picture 0.36 s with the sound
playing), and a rationed background read during play becomes possible (1942's bomber and its
break-up stream into a bank while it is on screen, decisions 153 and 154). The costs: Master (or
any 1770 machine) only; the driver must take the DFS's current drive and step rate, which only a
real drive showed (1942 `BUGS.md` #85); and a real 1770 settles the head 15-30 ms on every read
command with E set, which jsbeeb 2.3.x did not model (fixed upstream, PR #1226) - so any disc
access inside play is gated on real hardware, not on the emulator.

**Then decide which configurations of that machine it will run on**, as decisions too: second
processors, `*SHADOW`, sideways RAM that isn't at 4-7, a filing system softloaded into
sideways RAM, other DFSs, a machine with no BASIC. `docs/target-portability.md` lists them, with
what each costs, which emulator can test it, and the kit's defaults that handle most of them for
a few bytes of loader. Paradroid met them all at once in its last week, from a contributor's
checklist (its issue #18). A port that decides on day one meets them one at a time.

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

The first two ports ran on the same seven files, and 1942 added two more - `docs/done.md` and the
briefs. Each earned its place by a failure it caught.

| File | Job | Rule |
|---|---|---|
| **The rules file** (`CLAUDE.md` in all three ports; call it `HACKING.md` if you are not using Claude Code) | Standing rules, the measured hardware facts, the memory outline, the build commands | Read at the start of every session. When a fact in it is wrong, fix it the same day: Paradroid's carried "jsbeeb will not boot an unpadded SSD" for a week after it was disproved. **Give it a size budget, about 40K**: rules, measured facts and traps only. 1942's was touched in 198 of 483 commits and grew 22K -> 167K, every session paying to load it, before it was cut to 31K by moving the story to `done.md` and the oracles' long descriptions to a docs file of their own |
| `PLAN.md` | What is left, and nothing else | Cut it when it stops driving the next decision. Paradroid's went from 535 lines to 156. Detail moves to `docs/` |
| `docs/done.md` | What has landed, per layer or brief, with the number that says it landed | The other half of `PLAN.md`: a finished line leaves the plan by moving its evidence here, never by being deleted. Also where the rules file's history goes, so the rules file can stay small |
| `docs/brief-*.md` | One per job that a layer table does not fit (section 3.1) | Says at its top whether it is a PROPOSAL, a PLAN, BUILT or SUPERSEDED, and keeps that line current |
| `docs/decisions.md` | One table: every deviation from the original and every choice the hardware forced, numbered, dated, with its **status**, the reason and a link | **This is its only copy.** An earlier era kept one in `PLAN.md` too and the copy fell out of date. Nothing is re-litigated without a new row saying why. Section 3.2 has the lifecycle |
| `docs/layer-N-*.md` | Working notes per layer: what was measured, what was tried, what was costed and rejected | The rejected options are the valuable half. "Do not re-litigate the blitter unrolls" saved the RAM pass from repeating itself |
| `BUGS.md` | Defects with evidence, numbered | Fixed entries are never deleted; they record what was ruled out. Paradroid #5 and #6 is the model entry: two correct measurements supporting a wrong conclusion, and why |
| `docs/memory-map.md` | Every region, what is in it, how much is free, measured from the listing | Kept reasonably current through the whole port, because RAM is contended through the whole port. Every free-space figure says the date it was measured. "Take live figures from the build output, never from this paragraph" |
| `INFO`, and `!BOOT` | The stamp - assembly time, version line, every debug flag that is on - is a **disc file**, `INFO`, which the boot shows and `*TYPE INFO` reads back at any prompt. `!BOOT` *TYPEs it in a dev build, and a release stub prints its own copy | A build cannot lie about itself, and the question "which build is this?" is usually asked of a disc image someone was given a week ago, not of a screen that is still scrolling. Write the stamp ONCE (one macro, both files) or they drift. Add every flag to it and to `DEBUG_ANY`; assert `DEBUG_ANY = 0` under `RELEASE` |

Commit slicing follows the same shape: one mechanism per commit, with the measurement in the
body ("byte-identical over 40 passes", "0 of 10,240", before-and-after cycles). Doc-sync commits
are separate and frequent.

### 3.1 After the layers, work comes as briefs

The layer table carries a port to one playable level. What comes after - the other levels, a boss,
the front end, a RAM hunt, a second enemy engine - does not fit it: each job cuts across several
layers' code. 1942 wrote 36 briefs, one per job, before the job and finished after it, and
`template/docs/brief-TEMPLATE.md` is their shape:

- a **status line** at the top (PROPOSAL / PLAN / BUILT / SUPERSEDED), kept current;
- **the original, measured** - what the specification does, and what it was scored against;
- **a RAM ledger** - free now, read off the build, against what the job wants, per region,
  cycles and disc entries included;
- **the options, costed**, every figure labelled MEASURED (a tool run), COUNTED (off the listing)
  or PROJECTED (arithmetic on a count). Counted figures were wrong by a fifth and once by 2.5x in
  1942; one costing said -13 cycles a blit where the build measured +7. The brief says where its
  own figures could be wrong;
- **the decisions for the owner**, written as table rows;
- **the steps**, each one a commit with its measurement and its oracle;
- **what was costed and put down**, with the number that refused it;
- and, when it is done, **what landed and what it cost**, measured, beside the projection.

The brief is committed before the code, which is what lets a job interrupted half way - a session
limit, an overnight run - be resumed from its named step rather than reconstructed.
[1942's boss-as-background brief](https://github.com/kieranhj/1942-beeb/blob/master/docs/brief-boss-as-background.md)
is a complete one, proposal to "what landed".

### 3.2 Decisions have a lifecycle

About 30 of 1942's 161 decisions were superseded or reversed, and with no Status column the status
went into the Date cell ("ANSWERED 2026-09-17", "REVISED ...") and the rows grew into essays - one
ran to 10K. The template's table has a **Status** column: `OPEN` (raised, nothing built on it),
`PROPOSED` (an answer costed, waiting), `TAKEN` (the agent took it while the owner was away,
provisionally, and the job's report lists it), `AGREED`, `SUPERSEDED by N`, `REJECTED`. Three
rules came with it:

- **Merging a branch agrees the decisions it carries** (KC, 1942, 2026-10-06). An owner who merges
  has read the brief; a decision that should not have gone in is a new row, not a quiet revert.
- **A "Rejected, do not re-litigate" table** sits under the main one: what was considered, the
  number that refused it, and when. A rejection reversed by a new measurement becomes a row above.
- **Taste is settled from test discs, not argument.** Colours, outlines, how many compass
  directions a plane needs: build the alternatives side by side, each one switch away (an
  environment variable or a `-D` whose default is the shipped value), and let the owner play them.
  1942's eight-or-sixteen headings question was answered from three test builds in one sitting
  (decision 85).

Keep the row short and the evidence in the brief. `python -m beeb_port_kit.check_decisions
docs/decisions.md` (the kit's `py/`) checks the table still renders - a blank line between two rows
silently ends a Markdown table, and 1942's had six - and that every status is one of the six.

### 3.3 Generate what is per asset, and read figures off the build

Every hand-kept page in 1942 that described the build went wrong: the memory map (written by hand,
it described the kit's template for two days), the cell sheet, the 32-stage chart, the decisions
table's Markdown. The rule that replaced them: **anything per level, per asset or per region is a
generated page**, rebuilt by a tool from the build and the data (`tools/memmap.py --write` from the
listing; the cell sheet from the exporter's own packer, so the page and the disc cannot describe
different layouts), and **any figure that moves on an edit is read off the build**, with the doc
saying where to read it, not what it was. A generated page that cannot be generated is a page whose
defects cannot be fixed: smoke-test a generated page's script before publishing it.

---

## 4. The layer plan

All three ports went through the same sequence, whatever the game. Each layer is done when it is
visible in the emulator and its doc, decisions rows and plan update are written. The links are to
the layer docs in the first two ports; read the relevant one before starting the layer, because each
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
| 12 | **Release.** Release build, redefinable keys, pause, the padded disc, publication | Version line in the stamp (`INFO`), every debug flag off, a `*RUN` boot, tested on hardware | [edge L9h](https://github.com/kieranhj/edge-beeb/blob/master/docs/layer-9h-keyredef.md), [paradroid L11f](https://github.com/kieranhj/paradroid-beeb/blob/main/docs/layer-11f-frontend.md) |

The order is not sacred. Paradroid moved doors and lifts ahead of the droid layers when it helped.
What is sacred is finishing a layer, with its doc, before the next one starts.

**Where the time goes**, from all three histories, in order of size: memory (Paradroid from day 12
onward, Edge Grinder from Layer 6e onward, 1942 in six RAM hunts from its second week, in every
case after the port believed the problem was solved - section 2.2's inventory is the answer);
music (three passes in Edge Grinder); performance re-litigation caused by an earlier
measurement being wrong (a sign bug made Edge Grinder's Layer 3 counts 45 % optimistic); and
chains of corrections where one inferred fact was built on.

**Before building a new engine for something, cost doing it with hardware the port already
drives.** 1942's boss is an aircraft wider than the playfield. The first answer was a sprite with
a blitter of its own - three decisions (105-107), about three days, three save-store defects, and
a fight tick measured at 180,824 cycles against a 79,872-cycle budget, so every fight frame was
late. Decision 114 threw it away: the boss became **background**, composited row by row into the
scrolling ring as its rows enter, and moved by the scroll itself, backwards included. The fight
tick fell to 28,733 cycles at the median and the blitter left the build. For any large object,
price background-plus-scroll against a sprite before writing either: the scroll, the CRTC and the
background fill are engines the port has already paid for.

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
rows exactly, so it had no spare row and smooth vertical scrolling cost it one of the visible
sixteen. **That is the wrap's cost, not the scroll's**: size the strip with a row in hand and the
scroll's sub-row sliver comes out of the vertical total adjust for nothing (see 5.2).

On a Master, Edge Grinder holds two copies of the strip, main and shadow, half a byte out of
phase, and flips the displayed bank every field. A CRTC step in MODE 2 is two pixels; the odd
pixel is the other bank.

1942 uses the same two copies as a **double buffer** - the loop draws the back one, the VSync
shows it (its decision 43) - and the discipline that kept it correct is worth copying whole:

- **ACCCON is never read back.** Its value is always composed from the port's own state (1942:
  the back-buffer X bit, OR the displayed buffer's D bit, OR the fixed bits), and **every write
  goes through one routine** that composes and stores with interrupts masked across the two, so
  an IRQ that writes ACCCON itself cannot land between them.
- **X names the back buffer only while drawing.** Anything else in `&3000-&7FFF` - game state, a
  filename, a table - is read with X = 0. 1942 kept game state in that window and read a hold flag
  with X still on the back buffer, so the stage end ignored the hold on every other tick.
- **State inside the switched window is per buffer**, deliberately or by accident. Bookkeeping
  that must follow a buffer (each buffer's restore list, its text) lives there on purpose; state
  that must be shared lives outside it. A copy of one buffer onto the other must take that
  bookkeeping with it: 1942's first ring copy took the picture alone, and left text drawn on one
  buffer that nothing would ever lift.
- **A panel can live in shadow only**: a timer fire in the horizontal blanking just before the
  panel's first line flips D for its lines and the VSync puts it back, so the main-RAM copy of the panel becomes
  plain RAM (1942 decision 141: 896 bytes, measured on jsbeeb and agreed on a real Master).

### 5.2 A static panel and a scrolling area are a CRTC rupture - and the scrolling area goes FIRST

Two or three CRTC cycles a field: each cycle at its own start address, with VSync in the last one.
**If the play area scrolls vertically by scanlines, put it in the first cycle and the panel in the
last.** Sub-scanline scrolling comes from a pair of vertical total adjusts (R5) summing to 8: the
scrolling cycle takes `line`, the other takes `8 - line`. Put the panel above and that `8 - line`
lands between panel and play area, where it is visible, has to be blanked, and reads as a gap;
put the scrolling area first and it lands in the top border, where it costs nothing and the first
visible line sits at a fixed distance from the VSync edge whatever `line` is. The bottom sliver
then comes out of the scrolling cycle's own adjust, which displays when `R6 = rows + 1`. The
facts, the measurements and what the shape assumes are in the facts file under *The vertical total
adjust displays*; the primary source is Rich Talbot-Watkins's write-up and demo disc, and it is
worth reading before designing the frame. `template/examples/vscroll` is the shape as a working
program - the play strip first, scrolled a scanline a field at 50 Hz under the cursor keys, with its own
buffer oracle - and `template/docs/vertical-scroll.md` is what it measured.

Paradroid puts its panel above the play area anyway, and its layer-3 doc says why it then needs a
third cycle: with the panel on top, two cycles would leave the variable adjust between VSync and
the panel and slide the panel itself. That is a consequence of the ordering, not a reason for it.
A third port copied Paradroid's shape wholesale, paid two visible 8-line gaps, three extra timer
fires and half its blanking budget, and then rebuilt the frame the other way round for nothing.
**Ask what a technique's own author does before assuming the nearest previous port got it right.**

Whichever order, the panel sits at a fixed address and the play area at the scrolling one, with
VSync in the last cycle. The System VIA's T1 timer fires the stage changes; the handler is a small
state machine indexed by stage. The register write-window rules are the whole difficulty. The
principle is that a register must be written before the counter that compares against it reaches
the value: R4 in its own cycle before C4 gets there; R6 and R7 likewise inside the current cycle
as long as the row they name has not already passed, which in practice means the previous cycle
whenever the row is early; R12/R13 are latched at cycle start so always the previous cycle; R5
never near a boundary. Fires that blank or unblank must land in horizontal blanking, and the phase
is measured with a cycle counter modulo the scanline. Both ports' `rupture.6502` carry the table
in their headers.

A rupture with one shape is easy to hand over between screens. A rupture with **two** shapes (Edge
Grinder's titles use four cycles and switch the display bank mid-frame) needs the switch made
atomically inside the VSync handler, and that was the one bug still open when this was written.

**Overscan buys the panel without taking play lines.** 1942's playfield is the arcade's 256 lines
exactly, so the panel had nowhere to go but outside them: the frame lights **272 lines**, the
playfield's 256 then two panel rows, out of a 312-line field, leaving 40 lines of blanking against
PAL's nominal 25. The overscan comes out of blanking, not out of the field, and the playfield-first
order is what keeps it free - the `8 - line` adjust lands in the top border. It is the one
load-bearing assumption in such a frame, so it went onto a real display early (1942 decisions 14,
16, 19; fine on a real Master). Keep one knob that moves the picture up the tube
(`PANEL_R7`, Paradroid's `FRAME_DROP_ROWS`) and one fallback symbol that takes play rows away if a
display cannot cope, and light the panel's first and last lines so its extent can be seen.

### 5.3 Own IRQ1V outright

Take the interrupt vector, service VSync and T1 yourself, and give the MOS nothing. No MOS tick, no
OS sound, no OSBYTE keyboard. Consequences, all measured: the MOS's sound workspace at `&0800` is
yours only while you hold the vector, so flush the buffers before handing back; and on a Master,
if you take all of HAZEL, as Edge does by unpacking over 8K from `&C000`, DFS's own pages
included, BREAK must be a power-on reset (`OSBYTE 200,3`) or the next boot finds no DFS. The
window `&C300-&DEFF` is a different case: DFS keeps working and a soft BREAK still finds it, with
limits by call type (hardware-facts, HAZEL).

**DFS does not need the MOS to service interrupts.** Both ports load everything before taking the
vector and assumed that was why loading worked, but the assumption was never tested; measured now,
it is false. An 8 KB, 32-sector `*LOAD` completes byte-for-byte with IRQ1V pointed at a handler
that only clears the two VIAs' flags and returns - the MOS tick never runs, `TIME` does not
advance, and 232 interrupts pass through the null handler while the load proceeds. The same load
completes with interrupts masked outright (`SEI` across the whole call, an interrupt counter
proving none was taken), and again with the CRTC's VSync stopped as well. The 8271's transfers are
NMI-driven, and NMI is reachable in all three cases.
Measured: 2026-09-09, jsbeeb-mcp 3.4.0 / jsbeeb 1.25.0, `B-DFS1.2`, MODE 7, purpose-built one-file
disc.

**That is a Model B with an 8271. On a Master the null handler HANGS.** Same idea, same shape,
Master 128 / MOS 3.20 / Acorn 1770 DFS: masked with `SEI` the load is byte-identical, and a
handler that does its own work and ends `JMP (old vector)` is byte-identical too - but a handler
that *swallows* the MOS's interrupts never returned from the load, with the MOS spinning in its
service-call dispatcher. So did changing System VIA T1's latch under a chaining handler, and so
did disabling T1's interrupt. **Either mask, or chain and change nothing** - which also means a
rupture's own T1 cadence cannot run across a filing-system call, and that a chaining handler
hands back the tick that writes `&0800-&08FF`. Chunking is no escape: a call costs ~15
centiseconds plus ~4 a sector, so even a one-sector load blocks for nine fields.
Measured: 2026-09-13 by 1942-beeb, jsbeeb, **on its own target** - it is a Master-only port, so
these are the rows that matter to it, not an excursion. `docs/hardware-facts.md` has the table,
the provenance and the caveat that the three hangs want a b2 or real-Master run before anything
is designed against them.

**Which machine you ship for decides which rule you need.** A Master-only port takes the Master
rules above. A B-only port has the looser result. **A port targeting both takes the Master's** -
it is the stricter of the two, and the B has never been shown to need the looser one for anything.

Load before you take the vector anyway - the reasons that survive are real ones: DFS pages its ROM
in over `&8000`, its workspace is live until the last call returns, and a load in the middle of a
running display costs whole frames. Just do not expect a takeover to break the disc **on a B**.

**Or take the drive away from the filing system** (section 2.2's third answer): after the boot's
last DFS load and `OSBYTE 140`, a Master port can read the disc through its own 1770 driver
(`lib/qdisc.6502`), with the NMI its own and nothing of the MOS involved - so neither mask nor
chain applies, the rupture and the sound run through a load, and a rationed read can even run in
the background of play. 1942 has loaded every stage seam that way since its decision 116.

The frame lock lives in the VSync handler: the main loop parks a finished frame and a ready flag,
the handler flips the display when `FRAME_LOCK` fields have passed. A slow frame costs whole
fields, never a tear - **as long as a late frame waits for the next VSync.** 1942 chose otherwise
(its decision 65, the owner's call): on a double-buffered Master a frame that misses its VSync is
shown at once by its D bit, mid-field, and only its scroll registers wait for the VSync, so an
overrun of a few thousand cycles costs one torn field instead of a whole held one. The tear shears
the **sprites** at the cut and never the background, because both buffers hold the same level
bytes at the same addresses - which is also why no screenshot of the background can show it. And
it is switched off while text is on screen (decision 64), where a shear reads as a fault. Choose
one, write it down, and make an oracle fail on a late flip where the policy forbids one.

Edge Grinder ticks the game logic twice per display frame so the C64's 50 Hz constants transcribe
unaltered at 25 Hz. 1942 did the same for an arcade at 59.6 Hz by **treating it as 50** (its
decision 10): logic at 25 Hz, every per-frame delta doubled, so the arcade's one pixel every two
frames became exactly one play-pixel a tick and the scroll stayed integral. Where the original's
per-object routine is transliterated rather than doubled, call it twice a tick - and then **one
call is one original frame**: a new mover written "per tick" inside it moves double.

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
   engine adds the shift to the bank number and every address is the same. **The phase count is
   a memory decision, made per family, and costs no cycles** when the phase only selects which
   table the blit's base pointer comes from (1942, decision 15). 1942 shipped four phases for its
   aimed bullets and the small planes' rolls, two for explosions, shots and the big aircraft, one
   for anything whose X never changes parity. **Rigidity beats exactness**: every picture of one
   sequence (a take-off, a landing) shares one phase set, so at worst the whole sequence sits a
   pixel left and nothing in it shifts against anything else (decision 81). Measure whether a
   family's X changes parity before dropping its phase; every 1942 family that shipped at more
   than one did.
4. **`SCANSTEP` with the page carry deferred**: step the pointer down a column without a 16-bit add
   per scanline. Worth 668 bytes in Paradroid's bank when it was adopted.
5. **Restore all, scroll, draw all**, in that order, and restore in reverse draw order.

Compile only what is always on screen (the player, the bullet) and interpret the rest with bounding
boxes, but **measure first**: Edge Grinder deferred compiling until Layers 4 and 5 showed the
real load, and its interpreted engine was cheap enough. Clip at the edges rather than cull if
things enter from off-screen; culling makes them pop.

Three more that 1942 measured, once its cast outgrew the descriptor table (decisions 82, 83, 102,
103, 132):

- **Derive descriptor fields rather than storing them.** A field computable from another, or
  constant across every entry, costs a few cycles a blit to derive and a byte an entry to store,
  and the table grows downward into the code. Omit an all-constant array outright, generate every
  count the code and the oracles share, and `ASSERT` the table's end against the code ceiling.
- **Fuse a multi-tile object into one wide cell.** 28.6% of 1942's blits were the second tile of
  a two-tile plane, paying the whole setup again and reading the shared middle byte twice.
- **Generate a compiled sprite from the shipped bytes**, never from a second copy of the art: the
  compiled enemy bullet is written by a tool from the same cell the interpreted path draws, so an
  art change cannot leave the two disagreeing (and the tool must run after every art change).

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
probe the banks at boot and take the highest four; do not assume 4 to 7 (`lib/swram_probe.6502`).
On a Master they are 4 to 7 when its LK18 and LK19 links are set. Without them it has two, and
the probe says which links to move.

**When code space runs out**, in the order 1942 learned them: **move data, not code** - a
read-only table that any bank can read goes to low RAM and frees its bank for code (decision 57);
**look in the bank the code already has paged**, not only in main RAM - code that only ever runs
with a sprite bank in can live in that bank (decision 106); on a Master, **keep HAZEL paged for
the whole of play** once the filing system is gone, so HAZEL code and data need no paging and no
mask (decision 96); and **use the MOS's low-RAM pockets that a measurement says are unwritten**
through a whole driven game, BREAK included (decision 141's measurement: `&0100-&01BF`,
`&0220-&027F`, `&02B0-&03FF` and more, `docs/hardware-facts.md`). A map of what the MOS leaves is
not a map of what is free - read what the port already put there.

### 5.7 The disc: compress everything, one resident depacker, load in order

Every data file ships compressed and the loader unpacks it. Boot time in Paradroid went from
14.4 s to 10.4 s; the lever is sectors, not file count. Use **ZX02** (`lib/zx02depack.6502`,
`py/beeb_port_kit/zx02.py`): 131 bytes of depacker against ZX0's 257 and 2.14x the decode speed for +0.11% on
the packed size, measured 2026-09-07 over both ports' data. The two shipping ports are ZX0 discs
because they predate the measurement; `lib/zx0depack.6502` and `py/beeb_port_kit/zx0.py` stay for them. Pick one
format for a project and never mix them - nothing checks that the disc and the depacker agree. There is one depacker and it is resident;
Paradroid had two copies for a while and loaded one of them twice a session. A stream may not be
overtaken by its own output, so an in-place unpack needs a measured margin and the build should
fail if it is violated. On a Master, a file unpacked over HAZEL's DFS pages is the last disc
access; one kept inside `&C300-&DEFF` is not, provided later disc calls are OSFILE loads, saves or
deletes (hardware-facts, HAZEL).

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

### 5.9 Text with no character layer

An arcade draws its captions and tallies on a fixed character layer over the play area; the BBC
has none. 1942 draws the text **into the back buffer after the sprites, every tick, and saves what
it covers in the sprite save store**, so the ordinary restore lifts it with the sprites and the
scroll never has to know (decisions 62-64). Every glyph has a black edge, so it reads over any
ground in four colours. The cost is shared: **anything that takes save-store room takes the
text's** - 1942's text skips a line that does not fit, and a later feature that borrowed store
space made the caption's lines blink under load (`BUGS.md` #82). Price text and sprites against
the store together, at the game's busiest moment, with text on screen.

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
- The build stamps `INFO` - a disc file the boot shows and `*TYPE` reads back - with the time
  and the flags, and the release build is a command-line symbol. (BeebASM had no `IFDEF` and no choice; Baron has `DEFINED()`, and the
  kit still passes the flags every time so that a build says what it is.)

The reusable halves of these tools are in this kit's [`py/`](py/) directory. Fork them.

---

## 8. Working with an artist

### 8.1 Before any artist: reducing a large palette

A C64's 16 colours reduce to a BBC mode with some loss; an arcade's hundreds do not reduce at all
without a rule. 1942's four pens (black, blue, green, red; MODE 1) came out of these, in this
order (decisions 20, 80, 117, 128, 142, 151):

- **Reduce by role, not by nearest colour.** Every perceptual metric mapped the muted greens and
  browns to black. Give each pen a role (sea, land, the player, danger) and map each source colour
  to its role, with thresholds placed in measured gaps of the source's distribution; a pen
  reserved for one thing (the player's red) can leave a whole class of source colours with nowhere
  to go until it is given a second role.
- **Dither the terrain in 2x2 patterns phased on the SCREEN, not the tile**: tile phasing seams
  wherever a flipped tile meets an unflipped one. A screen-phased dither has no flip aliases, so it
  costs tile memory - price it.
- **Keep the sea to two pens, and make the sprites solid pens**, so a plane stands off dithered
  ground by texture: green planes vanished over a green jungle until they were solid.
- **Free extras inside the box**: a black outline baked into each cell inside its existing
  bounding box costs no byte and no cycle; chequer shading of a big sprite's mid-tones is free to
  the byte too.
- **Watch for things told apart by colour alone** (a power-up's colour, a formation that is the
  one to shoot) - they need a pen or a shape of their own.
- **Every rule is an environment variable whose default is the shipped value**, with a preview
  sheet per rule, so the owner chooses from test discs (section 3.2).

### 8.2 The artist pass

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

- **1942** had only the arcade's sound ROM: a Z80 sound CPU driving two AY-3-8910s. It **ripped the
  sound CPU headlessly** - the sound program run on a Python Z80 with the latch and AY ports as
  callbacks and the IRQ at its measured rate - scored that model RAM for RAM against MAME, 0 wrong,
  and then **converted the AY register stream to the SN76489 offline, per field**: the game's own
  channel priorities, periodic-noise bass below the SN's floor, the three loudest voices kept
  sticky, with WAV renders of both chips for the ear. Everything upstream of the conversion is
  exact; only the conversion is judged by ear. The converter is `py/beeb_port_kit/ay2sn.py`, useful
  to any AY source (CPC, Spectrum 128, MSX, arcade), and `docs/arcade-porting.md` has the route.

Whichever you use, verify it the way Edge Grinder does: capture the sound chip writes out of the
emulator and search for them inside a reference stream rebuilt from the data the build actually
includes. A wrong address plays happily for thousands of frames before it runs off the end.

Do not add sound effects the original does not have.

---

## 10. Release

- `RELEASE` is a build symbol passed on every invocation; `DEV` is its complement; every
  `DEBUG_` flag is folded into `DEBUG_ANY`, which is asserted zero under `RELEASE`.
- The stamp (`INFO`, and what the boot prints) carries the version line in a release and the
  flag list otherwise. **Every disc boots by `*RUN`, `*OPT 4,2`** - `!BOOT` is a stub that
  prints the stamp and runs the game. Never `*EXEC`: it needs a language ROM, and it writes
  into `&1100-&1900`, so it cannot coexist with `OSBYTE 140` or with a game that lives there
  (`lib/boot_stamp.6502`, `lib/loader.6502`, `docs/target-portability.md` 16).
- Every debug key needs CTRL once the play keys are redefinable.
- Pad the SSD to 200K before publishing; a published size that differs from the last publish is
  a useful signal that the wrong file went out.
- A second emulator before the release candidate, and real hardware before release. jsbeeb is
  the instrument for measuring; **b2 or beebjit** is the second opinion (b-em is no longer used).
  Both ports found things one emulator could not show: a rolled field that only b2 rendered, a
  NuLA register mistake that reached hardware, a mid-frame bank switch that only one emulator
  had been checked on. **And real hardware long before release for anything that touches the
  disc, the CRTC's timing or BREAK** - section 12.
- Publish work-in-progress builds to a stable URL so playtesters' links keep working. A WIP is
  **two discs from one commit**, the debug build and the release build (1942: `-wip` and `-rc`),
  because the release differs in kind (no debug keys, the title it ships with), and each disc's
  `INFO` names the commit. "Give me a build" means the local disc; publish only when asked
  (skill `beeb-publish-wip`).
- **Freeze features at the first release candidate.** After rc1 only fixes go in, and a feature
  restarts the count. 1942's rc1 to v1.0 took nine days and five candidates because three features
  landed inside it, one of them a whole enemy engine between rc4 and rc5. Skill `beeb-release` is
  the checklist: the release build and the suite on it, the target matrix, real hardware, every
  `BUGS.md` row closed or accepted, the catalogue and sector budget, `INFO` naming the commit.

---

## 11. What it costs

| | Paradroid | Edge Grinder | 1942 |
|---|---|---|---|
| Source | Disassembly, version proved on day 2 | Clean source | None: the arcade ROM under MAME |
| Machine | Model B + SWRAM | Master 128 | Master 128 |
| Layers 0 to 6 | ~3 weeks | 2 days | 6 days (Layers 0-8, stage 1) |
| To release candidate | 30 days | 5 days (art and one music decision open) | 38 days; v1.0 at 47 |
| Commits | 406 | 66 | 483 |
| Docs | ~15,000 lines | ~7,000 lines | ~30,000 lines |
| Decisions of record | ~60 in layer docs | 74 in one table | 161 in one table |

The gap between the first two is the process, carried over, and the machine: the first port's
month bought the second port's week. The third ran at the second's pace while the layer plan
applied, and its other five weeks went to what sections 2.2, 3, 4 and 12 now say to do earlier -
the whole game priced against RAM, the original captured whole and driven, the oracle suite made
believable, real hardware, and a feature freeze. The purpose of this kit is to make the next
port's Layer 0 an afternoon, and its last month shorter.

---

## 12. How the ports ran with Claude Code

All three ports were built with Claude Code doing the typing and the owner directing, reviewing,
playing and deciding, and this kit assumes the next one will be too. What made that work, in
order of importance:

1. **The rules file is `CLAUDE.md`** and it is loaded every session. The four rules in section 1
   go at the top, in those words. "Do not write hardware code from recalled facts" is the single
   instruction that matters most.
2. **The emulator is connected as an MCP server** (`jsbeeb-mcp`, `.mcp.json` in the repo), so the
   assistant can boot the disc, run frames, read memory, set breakpoints and capture sound without
   asking. Every measured fact in this kit was taken that way. **Require 3.4.0 or later**: it is
   the first release where `cycles_run` reports what it ran, where a run after a breakpoint stop
   does not overrun, where `read_memory` can be pointed at a bank instead of inferred from `&F4`,
   and where `release_all_keys` and `keyboard_state` exist. `docs/hardware-facts.md` says which
   notes apply only below it. **Pin the exact version** (`jsbeeb-mcp@4.3.0` in the template's
   `.mcp.json`, since 2026-10-21; 4.0.0 from 2026-10-11): bare `jsbeeb-mcp` moves on its own, and
   4.0.0 brought jsbeeb 2.x, which changed the key names and the type harnesses pass to `keyDown`.
   The template's headless harnesses load the jsbeeb **that pin** installed, so they measure on
   the MCP's emulator (`tools/jsbeeb_src.mjs`).
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
   return whichever bank is paged) across conversations, so they are not rediscovered. End a
   session with a note of the branch, whether it is merged and pushed, and which disc was
   published: 1942's owner lost track of which branches held what.
7. **Real hardware from the first layer that touches the disc, the CRTC's timing or BREAK**, not
   from the release. Only 1942's owner's Master found the 1770's head settle, the DFS's drive and
   step rate (`BUGS.md` #85), a 1772's different step rates, garbage on the panel's lines (#87) and
   BREAK leaving RAM uncleared (#92) - on day 22 and after. Any disc access inside play is gated on
   real hardware, because emulator disc timing is not trusted.
8. **Keep the rules file inside its budget** (section 3) and run a documentation pass when it, or
   `PLAN.md`, starts to narrate: skill `beeb-doc-pass`. 1942 needed nine.
9. **Branches**: one per brief; merged or deleted within a day of the owner's yes. A git worktree
   wants `bin/` copied into it; a `tools/output` junction in one is removed with `rmdir`, never
   `rm -rf`, which follows it.
10. **Unattended jobs work, and fail in known ways.** 1942 built its front end, a RAM hunt and four
    enemy-behaviour decisions overnight. What went wrong: decisions taken provisionally were
    later reversed; a real-hardware gate was bypassed and the branch merged before the owner's
    Master saw it; the session limit cut a rewrite off half way (survivable only because the brief
    named the resume point); branches piled up; suites died of memory or a background time limit.
    The rules are skill `beeb-unattended-job`: own branch, the brief committed first with a resume
    point, provisional decisions marked `TAKEN` and listed in the morning report, hardware gates
    left shut, the suite detached with its output outside the home folder, no publishing, and a
    branch ledger in the report.

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
- [1942 `docs/arcade-facts.md`](https://github.com/kieranhj/1942-beeb/blob/master/docs/arcade-facts.md):
  an arcade original measured out of MAME, section by section, with the traps in the instrument.
- [1942 `docs/performance.md`](https://github.com/kieranhj/1942-beeb/blob/master/docs/performance.md):
  every cycle and byte figure, each labelled MEASURED, COUNTED or PROJECTED, and what was rejected
  with the number that rejected it.
- [1942 `docs/brief-boss-as-background.md`](https://github.com/kieranhj/1942-beeb/blob/master/docs/brief-boss-as-background.md)
  and [`docs/report-ram-2026-10-06.md`](https://github.com/kieranhj/1942-beeb/blob/master/docs/report-ram-2026-10-06.md):
  a brief from proposal to "what landed", and an overnight RAM hunt's morning report.
- All three `BUGS.md` files, end to end.
