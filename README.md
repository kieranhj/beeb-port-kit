# beeb-port-kit

**A starter kit for porting a C64 game to the BBC Micro with a coding agent**, distilled from
two ports that shipped: [Paradroid](https://github.com/kieranhj/paradroid-beeb) (Model B,
2026-08) and [Edge Grinder](https://github.com/kieranhj/edge-beeb) (Master 128, 2026-09). Both
were written by Claude Code with a human directing, reviewing, playing and deciding. The first
took a month. The second, reusing the first's method, took a week. This kit is what the second
still had to rediscover, packaged so the third does not.

**Be clear about what this is.** Everything under `docs/`, `skills/` and `PORTING.md` is written
to be loaded into an agent's context: dense, exhaustive, and cited, because that is what makes an
agent measure instead of guess. The hardware facts are what any experienced BBC programmer
already knows from the Advanced User Guide; the gotchas are the ways an agent trips up in a
build-test loop, which is not how a person works. None of it is meant to be read by a human, and
the library code is the only part a hand port would take. The summary below is the human version.

## The approach, in a page

Two C64 games were ported to the BBC Micro in 6502 assembly by an AI coding agent, with a person
choosing the game, directing the work, playing the builds and taking every design decision. The
first port took a month, the second a week, and the difference was method rather than machine.
This is the method.

**Treat the original as the specification.** Get its source or a trusted disassembly, prove which
version it is, and transcribe: routines, tables and constants copied verbatim wherever the
hardware allows. When the BBC forces a change, port the decision the original made, not just the
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
and accept that some games need a Master. Keep a memory map current and expect to trade
quality for space. Multi-part loading is feasible on the BBC's fast floppy but confine it to
seams: loader, titles, game.

**The architecture that transferred between the two games**: the play area as a circular strip
under the hardware wrap, scrolled by the CRTC; a static panel above it by a CRTC rupture, with
the palette switched per cycle; the game owning the interrupt vector outright, keyboard read
straight from the VIA; sprites in slots with a save area that mirrors screen geometry, the mask
taken from the data byte, pre-shifted copies in sideways RAM; every file ZX0-compressed on disc
with one resident depacker; a release build flag and a boot stamp naming every debug flag.

**What the person does**: chooses the game and the machine, answers the decisions, plays every
build on a second emulator and on hardware, reports what looks wrong, and owns taste calls like a
speed or a colour, which are played rather than calculated.

**What the kit gives the agent**: the full method, the facts it would otherwise re-measure, the
mistakes it would otherwise repeat, a dozen checklists for the measurements it makes over and
over, the code both ports shared, and a starter project that boots to a panel above a scrolling
area with all eight colours on screen.

## What is here

```
PORTING.md              the playbook: rules, artefacts, the layer plan, the patterns that transfer
docs/hardware-facts.md  measured facts about the CRTC, VIAs, MOS, DFS, BeebASM and the emulators
docs/gotchas.md         the bug classes that recurred, with the instance and the rule
docs/verification.md    the measuring and checking procedures, by hand or through the MCP
skills/                 the procedures as Claude Code skills; copy into .claude/skills/
lib/                    6502 includes that were identical in both ports: depacker, IRQ owner,
                        constants, keyboard read, loader
py/                     the Python halves that were identical: ZX0, DFS image builder, mode
                        packers, C64 readers, the art sheet pipeline
template/               a starter project that boots to a panel above a play area with a
                        rupture, its own interrupt handler, direct keyboard and a compressed disc
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

Every line of new code in the two ports was written by Claude Code, directed and reviewed by
Kieran Connell. The measurements say what they were taken on and when; nothing here is believed
without one. MIT, see [`LICENSE`](LICENSE).
