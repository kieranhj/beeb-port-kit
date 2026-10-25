# beeb-port-kit

**A starter kit for porting a game to the BBC Micro with a coding agent - from a C64, an arcade
board, or anything you can run under an emulator** - distilled from three ports that shipped:
[Paradroid](https://github.com/kieranhj/paradroid-beeb) (C64, Model B, 2026-08),
[Edge Grinder](https://github.com/kieranhj/edge-beeb) (C64, Master 128, 2026-09) and
[1942](https://github.com/kieranhj/1942-beeb) (Capcom arcade, Master 128, 2026-09-07 to 10-23).
All three were written by Claude Code with a human directing, reviewing, playing and deciding.
The first took a month. The second, reusing the first's method, took a week. The third had no
source at all - only the arcade ROM, running in MAME - and took seven weeks, the first three at
the second's pace. This kit is what each still had to rediscover, packaged so the next does not.
A fourth project used the kit for another kind of job:
[Stryker's Run](https://github.com/kieranhj/strykers-run) (BBC Master 128 and Model B, 2026-10-16 to
10-25), a BBC original rebuilt byte for byte from its disassembly, then made faster, flicker free and
playable on a Model B; what it added is in `PORTING.md` section 2.1c and through the docs and tools.

**Be clear about what this is.** Everything under `docs/`, `skills/` and `PORTING.md` is written
to be loaded into an agent's context: dense, exhaustive, and cited, because that is what makes an
agent measure instead of guess. The hardware facts are what any experienced BBC programmer
already knows from the Advanced User Guide; the gotchas are the ways an agent trips up in a
build-test loop, which is not how a person works. None of it is meant to be read by a human, and
the library code is the only part a hand port would take. The summary below is the human version.

## The approach, in a page

Three games - two from the C64, one from an arcade board - were ported to the BBC Micro in 6502
assembly by an AI coding agent, with a person choosing the game, directing the work, playing the
builds and taking every design decision. The first port took a month, the second a week, and the
difference was method rather than machine. The third added what a game with no source, and a
much bigger one, demands of that method. This is the method.

**Treat the original as the specification.** Get its source or a trusted disassembly, prove which
version it is, and transcribe: routines, tables and constants copied verbatim wherever the
hardware allows. With no source, capture the original running under an emulator, drive it to
every state the recordings never reach, and model each routine until it scores zero wrong against
the capture. When the BBC forces a change, port the decision the original made, not just the
visible effect. Every deviation is a numbered decision, agreed with the person before it is
built and written down after. Nothing is added quietly, and nothing the original lacks is added
at all without a decision.

**Build one layer at a time, visible in the emulator before the next starts.** Toolchain, data
pipeline, display, scroll, sprites, player, game logic, game flow, sound, loader, art, balance,
release. No abstraction layer up front. Each layer ends with a short write-up of what was
measured and what was tried and rejected, so the same argument is never had twice.

**Measure, never recall.** The agent has an emulator it can drive: set registers, run frames,
read memory back, set breakpoints, capture the sound chip. Every hardware number in the code
came from doing that, and the write-ups say what it was measured on and when. The one time a
register's behaviour was inferred instead, the mistake reached real hardware.

**Verify against the buffer, not the screenshot.** Screenshots said "fine" when it was not, more
than once. The check that works is an independent rendering of what the screen memory should
hold, diffed byte for byte against what the game drew, at the awkward scroll positions. The same
habit everywhere: never check a thing against itself, and say which oracle a number came from.

**Assume RAM is tight for the whole port.** The source machines have more memory than a BBC.
Target a Model B with as little sideways RAM as the game can fit in, so more people can run it,
and accept that some games need a Master. Price the whole game's data against the machine in the
first week, before the first level's layout is fixed. Keep a memory map current - generated from
the build, not written by hand - and expect to trade quality for space. Multi-part loading is
feasible on the BBC's fast floppy but confine it to seams: loader, titles, game, levels.

**The architecture that transferred between the two games**: the play area as a circular strip
under the hardware wrap, scrolled by the CRTC; a static panel above it by a CRTC rupture, with
the palette switched per cycle; the game owning the interrupt vector outright, keyboard read
straight from the VIA; sprites in slots with a save area that mirrors screen geometry, the mask
taken from the data byte, pre-shifted copies in sideways RAM; every file compressed on disc
with one resident depacker (both ports used ZX0; a new port uses ZX02 - half the code and twice
the speed for +0.11% on size, measured); a release build flag and a build stamp - a disc file, `INFO`, that the boot shows and `*TYPE`
reads back - naming every debug flag.

**After the layers, work comes as briefs**: one per job too big for a layer - the other levels, a
boss, the front end, a RAM hunt - each costed before it is built and closed with what it really
cost. Decisions carry a status; what has landed has its own log; the rules file has a size budget,
because it is loaded every session.

**What the person does**: chooses the game and the machine, answers the decisions, plays every
build on a second emulator and on real hardware - from the first layer that touches the disc, the
CRTC's timing or BREAK, not just before release - reports what looks wrong, and owns taste calls
like a speed or a colour, which are played from test discs side by side rather than calculated.

**What the kit gives the agent**: the full method, the facts it would otherwise re-measure, the
mistakes it would otherwise repeat, a checklist (skill) for each measurement and procedure it
makes over and over - [`skills/README.md`](skills/README.md) lists them - the code the ports
shared, the tools for capturing and modelling an arcade original, and a starter project that
boots to a panel above a scrolling area with all eight colours on screen.

## What is here

```
PORTING.md              the playbook: rules, artefacts, the layer plan, briefs and decisions, the
                        patterns that transfer
docs/arcade-porting.md  when there is no source: capturing an arcade original in MAME, driving it,
                        modelling its ROM routines to 0 wrong, rotation, DIP switches, the sound CPU
docs/hardware-facts.md  measured facts about the CRTC, VIAs, MOS, DFS, the 1770, the assemblers and
                        the emulators
docs/gotchas.md         the bug classes that recurred, with the instance and the rule
docs/verification.md    the measuring and checking procedures, by hand or through the MCP
docs/build-portability.md   the rules for a build that makes the same disc on any machine
docs/dataflow.md        static analysis of the linked program - liveness, ranges, bytes to
                        save - by beebgame's dataflow tools, on a Baron or beebasm build
docs/related-beebgame.md  what this kit takes from Eben Upton's beebgame engine, what it sent
                        back, and what it left on purpose
docs/target-portability.md  which machines a port runs on: each configuration, what it costs,
                        what can test it, and the defaults the template already carries
skills/                 the procedures as Claude Code skills; copy into .claude/skills/ - from
                        the smoke test and the buffer oracle to the arcade capture, the ROM
                        model probe, the oracle harness, a RAM hunt, an unattended job, a doc
                        pass, the WIP publish, the release and the micro-optimisation grind
lib/                    6502 includes the ports shared: depacker, IRQ owner, constants, keyboard
                        read, loader, and qdisc*.6502 - a Master's own WD1770 driver, for a game
                        that loads after the filing system is gone; nmos.6502 (65SC12 code that
                        also builds for a Model B) and sfx50.6502 (sound effects at 50 Hz for a
                        game that owns IRQ1V). Baron syntax (the assembler
                        the kit defaults to now); docs/toolchain-baron.md has the BeebASM delta
py/                     the Python halves the ports shared: ZX02 and ZX0, DFS image builder, mode
                        packers, C64 readers, the art sheet pipeline, the decisions-table lint
                        (check_decisions.py), ay2sn.py (AY-3-8910 register streams to the
                        SN76489, offline), sfx50.py (the MOS's sound effects fitted as 50 Hz
                        ramps), and mame/ - running MAME as an instrument, per-frame
                        capture records, ROM sets and gfx layouts, rotation, a headless Z80
                        sub-CPU, and the 0-wrong scoring shape of a ROM model probe
template/               a starter project that boots to a panel above a play area with a
                        rupture, its own interrupt handler, direct keyboard and a compressed
                        disc; docs/ with the decisions table (with a Status column), done.md
                        and a brief template; tools/ with the headless oracle harness
                        (harness.mjs), the suite runner (run_suite.py) and the command
                        printer that reads every address off the build (verify_cmds.py), the
                        A/B pair harness and the relocation proof (pairlock, lockstep,
                        tracediff), probes (irqprofile, memwatch, pcprof), video with sound,
                        nmosify and the grind's tools;
                        tools/mame/ with the Lua capture harnesses; template/examples/vscroll
                        is the other frame shape - the play area FIRST, scrolled one scanline
                        at a time under the cursor keys, with its own oracle and its
                        measurements
```

Everything in `lib/` and `py/` is meant to be **forked into your project and hacked**, not
depended on. Each file's header says where it came from and what was measured about it. Keep
the header when you fork it.

## Start here

1. Point your agent at [`PORTING.md`](PORTING.md). It is long because it is the whole method,
   and the agent is the one who has to read all of it.
2. Copy `template/` to a new repository and build it. It should boot in jsbeeb.
3. Copy `skills/` into the project's `.claude/skills/`.
4. Have the agent write the proposal, using section 2.3's table, and take your first decisions.
5. Layer 0.

## Provenance

Every line of new code in the three ports was written by Claude Code, directed and reviewed by
Kieran Connell; 1942's disc driver derives from scarybeasts' quicdisc, relicensed for it, and its
title player is his p15k3 (which the kit links to rather than carries). The measurements say what they were taken on and when; nothing here is believed
without one. MIT, see [`LICENSE`](LICENSE).
