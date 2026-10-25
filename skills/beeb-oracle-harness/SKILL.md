---
name: beeb-oracle-harness
description: Write a headless jsbeeb oracle for a BBC Micro port on the template's tools/harness.mjs - addresses from the symbol dump, the bank named on every read and write, hooks gated on the paging, a driven run, a coverage gate, a model that does not borrow from the port, and an exit code that is the verdict. Use when a layer, a fix or a measured behaviour needs a check that runs on every build, when turning an MCP-by-hand check into a script, or when an existing harness passes and nobody has seen it fail.
---

# A headless oracle harness

A check that runs on every build, unattended, and is believed. 1942 for the BBC Master ended with
148 of these, and most of what it learned is how one LIES: an oracle answering a well-formed
object of zeros with exit 0 (its `BUGS.md` #9), a harness echoing the stage it asked for (#39), a
run that never pressed a key (#31), an oracle that shared the port's table and scored zero on a
wrong port (#16). The long form is `docs/verification.md` "Headless harnesses" and procedures
16-19; the skeleton is `template/tools/harness.mjs`, and `template/examples/vscroll/tools/record_vscroll.mjs`
is a worked one.

**Exit 0:** sampled something, every named path taken, every sample agreed
**Exit 1:** something disagreed - OR nothing was sampled, OR a path was never taken
**Exit 2:** could not judge: usage, a missing symbol, a stale build, a disc that never booted
**Output:** one JSON line, last, with `jsbeeb` (the version) in it; explanations on stderr

## Steps

1. **Name the oracle before writing code.** What is the port compared AGAINST, and was that
   produced by the code under test or anything derived from it? If yes, find one that was not:
   the original's capture, a model written from the specification, a round trip
   (`docs/verification.md` procedure 15). Decide whether this is a DATA oracle (the buffer holds
   the exported bytes) or a BEHAVIOUR oracle (the object does what the original's does) - a plane
   circling for ever is drawn perfectly, so you may need both.

2. **Start from the skeleton**, in `tools/` beside `verify_dynamic.mjs`:

   ```js
   import { open } from "./harness.mjs";
   const h = await open({ name: "verify_thing", disc: process.argv[2] });  // dump beside the disc
   const LOOP = h.need("main_loop"), FIELD = h.zp("field_count");
   const N = h.asmConst("THING_MAX");        // dump value, checked against the source's literal
   await h.boot({ field: FIELD });           // exit 2 if the field counter never moves
   const cov = h.coverage();
   ```

   **No address is an argument with a default, and none is written in a doc.** `need()` exits 2
   on a missing or ambiguous name; `zp()` refuses one above `&FF`; `asmConst()` exits 2 if the
   dump and the source disagree (a stale build). 1942's `measure_budget` defaulted one address,
   the code moved it a byte, and it answered "51 objects fit" against the true 13.

3. **Name the bank on every read AND write** of `&3000-&7FFF` and `&8000-&BFFF`:
   `h.rd(a, n, "main")`, `h.wr(a, bytes, 5)`, `"shadow"`, `{bank, shadow}`, or `"paged"` to say in
   so many words "whatever is in". They throw otherwise. An unbanked cheat write in 1942 landed in
   the other screen buffer on a boot an odd number of fields longer, and the cheat run and the
   no-cheat run came back identical.

4. **Hook, do not time.** `h.onExec(addr, fn, {romsel: 5})` on the loop or the instruction after
   the draw - never "sample every N fields", which catches a half-drawn buffer on a busy tick. The
   gate is `(ROMSEL AND &8F) = 5`: on a Master an address below `&9000` in a bank is ALSO ANDY's
   (pass `andy: true` for ANDY code). Hooks stay dark until `boot()` returns, because the DFS runs
   code at overlay addresses while loading. For a raster-phase claim, `h.onWrite(lo, hi, fn)`
   gives each write its PC, cycles, paging and CRTC counters (`hc`, `vc`, `sc`, `adj`).

5. **Drive the run, and size it.** Hold fire; force deaths, power-ups and the screen edges by
   poking what the original's code would set, where it would set it; hold invincibility on long
   runs; sample from tick zero, not after a settle; run more than level 1. **Never verify through
   a debug shortcut** (a skip key that redraws the screen repairs the corruption the real path
   made - 1942 #35), and **read state back, never echo the argument** - hold a skip key until the
   game's own byte moves and fail unless it lands where asked (#39). Ask what length covers the
   case: 2,600 ticks missed 1942's #31 and 6,000 found it.

6. **Gate on coverage.** List the paths from the code under test (each branch that changes what
   is drawn or decided), `cov.need(name, n, why)` each, `cov.hit(name)` in the hooks. Count the
   CASE, not the call.

7. **For logic, record and replay.** Record the port's inputs and outputs per step to a trace;
   a Python `check_*.py` runs the reference model over it, **re-seeded from the port's state at
   every step**, written from the specification and not transcribed from the 6502. The recorder
   spawns the checker and exits with its code: one command, one verdict.

8. **Finish with the samples counted:**

   ```js
   h.finish({ wrong, judged, firstWrong }, wrong === 0, { samples: judged, cover: cov });
   ```

   `samples: 0` fails; a gap fails. Budget each tick and use `h.runTo(addr, budget)`, which on
   giving up records `where()` - PC symbolised, ROMSEL, ACCCON, stack, `(&FD)` - in the JSON.

9. **Prove it fails.** Run it on the unfixed build, or on a deliberately broken input, and see
   exit 1 with the defect named. Keep a negative control in the suite where it is cheap (an env
   switch that pokes one byte; `verify_cmds.py` marks the line `expect: 1`). An oracle never seen
   failing has not been shown able to.

**For "the change left the game alone"** - an optimisation, a renderer against its
draw-everything twin, a relocation - the oracle is the other build, and the template has the
pair already: `tools/pairlock.mjs CONFIG CONTROL.ssd TEST.ssd` gives both builds the same keys
per game-loop PASS (so a faster build plays the same game) and compares the config's state
ranges, and with `--screen` the shown screen, at the start of every pass; `--poke P:ADDR=B` is
its negative control. `tools/lockstep.mjs` and `tracediff.mjs` are the relocation proof
(`build.ps1 -Shift 256` against `-Shift 256 -ShiftEnd`). A config is a few lines
(`template/examples/pairlock/`); do not write another pair harness.

10. **Add its line to `tools/verify_cmds.py`** with the reason the run exists beside it, and run
    the suite (`beeb-run-suite`). Record the figure with the jsbeeb version, the date and what the
    run covered: "0 wrong of 1,951, 325 takes, both wraps, jsbeeb 2.10.2, 2026-10-25".
