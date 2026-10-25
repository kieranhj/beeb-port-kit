---
name: beeb-micro-grind
description: An aggressive, repeatable micro-optimisation grind over a BBC Micro port's hand-written 6502 - beebgame's static analyses annotate every instruction (flags, registers, memory operand ranges, liveness), the code is cut into 32-instruction windows weighted by measured cycles, an army of optimiser agents proposes faster or smaller code for each window, skeptic agents try to refute every proposal, and the survivors are applied one batch at a time through the project's proof gate, kept only if every check passes and the game is no slower. Iterates until a round finds nothing. Expensive (hundreds of agents a round). Use when asked to grind, micro-optimise the whole codebase, or squeeze cycles out of everything.
---

# The micro-optimisation grind

**The method is Eben Upton's**, from [beebgame](https://github.com/ebenupton/beebgame): its `tools/dataflow/README.md`, "Using the
annotations to shrink code: a suggested farm" (vendored here as `template/tools/dataflow/README.md`).
Cut the sources into windows of annotated lines, give each batch a reviewer and then a skeptic,
apply what the skeptic did not refute a small batch at a time behind the game's own equivalence
test, bisect failures, and audit what was accepted; beebgame's Commando: two passes, 171 proposals,
about 400 bytes. Stryker's Run turned it on cycles rather than bytes - windows weighted by measured
cycles a pass, a gate that keeps a change only if the game is no slower - and wrote the
bookkeeping this skill drives (`grind.py`).

From Stryker's Run (2026-10-17 to 10-23), where KC's brief was: "an aggressive micro-optimisation
grind over the whole codebase; get static analysis tools from github.com/ebenupton/beebgame; run
to annotate lines with flags, regs, memory operand ranges; spawn army of agents to evaluate every
32-instruction consecutive sequence of annotated instructions for better implementations; record
candidates; apply serially with skeptic; iterate indefinitely."

**What it gave there.** Three rounds, 580 candidates proposed, 256 kept by the gate. A pass's
work (cycles, the frame lock's wait excluded) went 43,036 -> 39,112 in round 1 alone and
34,422 -> 31,869 in round 3; 43,036 -> 31,869 from start to end of the three rounds, with a RAM
rearrangement and other layer work landing between them. Late frames 21 -> 7 of 1,998 from
round 1. Of the rest: 174 went stale (an earlier kept change had moved their text), 67 refuted by
their skeptics, 53 out of room, 10 slower, 10 no gain, 8 failed a check.

**It is expensive.** A round is one optimiser agent per hot window (one per two cold ones) and two
or three skeptics per candidate: at Stryker's Run's size (232 windows, 78 holding 90% of the
measured cycles) a round over the hot code was 300-600 agents. Say so before starting one, and run
the hottest windows first: most of the cycles are in a few windows, and later rounds reach the
rest.

**Do not start one before the port has a gate worth trusting** (step 0 below). The grind's
skeptics reason; only the gate proves, and it proves only the paths its checks run.

## Pieces

All in the project (the template carries them; `CLAUDE.md` says where if they moved):

- `tools/analyse.py annotate`: beebgame's analyses, vendored and pinned (the beeb-dataflow skill).
  Every instruction gets the state before it: A, X, Y, the flags, the memory operand's value or
  range (`?` unknown, `0..9`, `{...}`, `≡$C3` equal to that byte), and `in:/out:` liveness.
- `tools/pcprof.mjs`: every instruction's cycles by address, bank and phase (`run`, `wait`,
  `irq`) over a stretch of play: the windows' weights (`--out PC.json`) and the gate's measurement
  (`perPass.work`).
- `tools/grind.py`: the windows, the ledger, the gate and the serial run (its docstring).
- `tools/grind_config.py`: the project's facts - protected code, generated sources, the builds,
  the checks, the measurement, the noise. **Every entry says why.** The template's is a worked,
  commented example with Stryker's Run's values beside its own.
- `evaluate.workflow.js` (beside this file): the optimisers and the skeptics. `refute.workflow.js`:
  the skeptics alone, for a round that died between the two (`grind.py todo` says what is owed).
- `docs/grind/ledger.jsonl` (every candidate ever, its votes, its fate), `docs/grind/seen.txt`
  (windows already evaluated, by content hash), `docs/grind/README.md` (`grind.py report`).

## 0. Before the first round

1. **The gate.** `grind_config.py` CHECKS must be the port's suite, comparing the test against the
   control - state and the shown screen in lockstep over thousands of passes on two or three
   seeds, keys **by pass** so builds of different speed play the same game (a pair harness), an
   independent oracle build, and a check for **every path play rarely takes**: the front end,
   define keys, game over, the end of the game, a death, a vehicle. Stryker's Run's round 1 kept
   a change (G0038) that broke observer mode's keys; nothing in the gate ran that path, and it was
   found days later (its BUGS #11). The template's CHECKS (verify_dynamic on both models) are a
   placeholder that compares nothing against the control: replace them.
2. **Protect** what is timed or read as data: raster-timed writes (cycles from an interrupt to a
   palette or CRTC write), anything timed from vsync, code bytes another part of the build reads
   as data (`PROTECT_BYTES`), self-modified operands that must stay where their writers put them.
3. **The measurement** (`MEASURE`): deterministic work a pass on the same game for control and
   test. Run `grind.py gate` on an unchanged tree once: both measurements must come back within
   NOISE (Stryker's Run: 0.1 cycles a pass from the builds' stamps; the template: 0.0).
4. **A negative control**: apply a deliberately slower change and see the gate say so (the
   template's two NOPs at `main_loop` measured -3.5 cycles a pass on both games).

## A round

1. **On a branch** (`git checkout -b grind-<date>`): the serial run commits each batch it keeps.
   Build everything first; a clean tree.
2. **Profile and annotate the build the proofs use**, so addresses, cycles and annotations all
   describe the same image:
   ```
   node tools/pcprof.mjs BENCH.ssd --pass main_loop --passes 1500 --wait wait_label:4 --out build/grind/pc-a.json
   node tools/pcprof.mjs BENCH.ssd --pass main_loop --passes 600 --wait wait_label:4 --keys RIGHT --out build/grind/pc-b.json
   python tools/analyse.py --listing BENCH.lst --symbols BENCH.symbols.json --disc BENCH-raw.ssd annotate
   ```
   (two games: one scripted, one with the commonest key held). `annotate` must end `N instructions
   annotated` and its summary must not say `NOT sound`; if the interrupt's model complains, fix
   `tools/dataflow_config.py` first.
3. **Cut the windows:** `python tools/grind.py windows --profile build/grind/pc-a.json
   build/grind/pc-b.json` (`--offset 16` on alternate rounds, so a sequence cut in two by one
   round is whole in the next; `--all` to ignore seen.txt). It prints how many windows hold 50, 90
   and 99% of the measured cycles. A window whose lines are all protected is dropped; one that
   overlaps protected lines shows them marked `PROTECTED`.
4. **Evaluate:** run the workflow with the windows to do, hottest first (a round can take a slice):
   `Workflow({scriptPath: ".claude/skills/beeb-micro-grind/evaluate.workflow.js", args: {round: N,
   windows: <entries of build/grind/windows.json>, cpu: "<the CPU and machine>", listing:
   "build/<stem>.lst"}})`. Each optimiser writes `build/grind/rN/opt-<window>.json`, each skeptic
   `skeptic-<window>-<i>-<lens>.json`. If it dies: `python tools/grind.py todo build/grind/rN
   [--windows build/grind/windows.json]` and `refute.workflow.js` with that output.
5. **Record:** `python tools/grind.py add build/grind/rN` - every candidate into the ledger,
   approved (at least two skeptics heard, fewer than half refuting), refuted or unreviewed; the
   windows into seen.txt. Commit the ledger.
6. **Apply serially:** `python tools/grind.py run` (in the background: Stryker's Run's gate was
   about half an hour). Best claim first, one candidate per region of a file in a batch of four:
   apply, gate, keep and commit if every check passes, no measurement is slower and something is
   gained (cycles beyond NOISE, or bytes claimed - the ASSERTs and checks having held); else revert
   and bisect down to the candidate that fails. A candidate whose old text is gone is `stale` and
   its window comes back next round. A single candidate's failure is classified: `stale` (a kept
   change took its label or callee: Baron's `Duplicate symbol` / `Undefined symbol`), `no room`
   (its region's ASSERT, by the config's NO_ROOM pattern; `run --retry 'no room'` once the region
   has grown), `failed` (a check), `no gain` (within NOISE), `slower`.
   **After a gate or a run, `build/` holds the last build the gate made**, which may be of a
   candidate since reverted: rebuild before anything else reads it (the kit's
   `test_baron_dbg` found 2 lines unplaced against the template's reverted source).
7. **Report** (`grind.py report`, then commit): candidates by status, what was kept and what it
   saved, batch by batch.
8. **Iterate:** re-profile and re-annotate the new build, cut the windows again (changed code has
   new hashes, so it is evaluated afresh; unchanged code is not), and go round. Stop when a round
   keeps nothing, twice running, or when told to.

## What an optimiser does

Reads its window file, then the source around it: at least 60 lines either side, every label in
or next to the window, and every reference to them anywhere in the sources (grep). Proposes up to
four replacements for lines inside the window, best first, each as the exact source lines it
replaces (`old`, verbatim, comments and all) and their replacement (`new`). Aggressive: the
annotations exist so that facts the code re-establishes can be used instead. What to look for:

- a flag already known (a `CLC` where `C=0` is shown, a `CMP #0` after a load), a register already
  holding the value, a load whose value is already in A, X or Y, a store nothing reads (`out:`);
- strength reduction, a table instead of arithmetic, arithmetic instead of a branch, a branch
  arranged so the hot path falls through, the hot path with the fewest taken branches;
- on a 65C12 (Master) only: STZ, BRA, PHX/PLX/PHY/PLY, TSB/TRB, INC A/DEC A, `(zp)` without Y,
  BIT #, BIT zp,X. On an NMOS 6502 none of these exist - the project's `CLAUDE.md` Target says
  which CPU, and a build for both must keep to the NMOS set or use the kit's NMOS macros;
- self-modified immediates or operands in place of zero-page loads, loops unrolled or split where
  the bytes are there, work hoisted out of a loop, indexes counted down to zero;
- page crossings on indexed reads in hot loops.

What Stryker's Run's gate rejected most, which the workflow's prompt repeats:

1. **The wrong common case**: a branch rearranged for the path intuition says is common. Check the
   window's measured cycles a line, not intuition.
2. **A byte or two saved in hot code that slides a hot branch or table read across a page**: 20-60
   cycles a pass lost. Say which crossings a size change moves; no byte-only savings in hot code
   without counting that.
3. **Entries past a label**: `JSR name + 1`, `BMI loop + 15`. Round 1's G0038 removed
   `keydown_int`'s first instruction and broke a `JSR keydown_int + 1` nobody had grepped for
   (its BUGS #11). Grep `name *+` across the sources before changing the first bytes of any routine.
4. Two alternatives defining the same new label: name a new label for the candidate.

Claims: cycles saved an execution on the hot path (both paths if they differ), executions a pass
(the line's measured cycles ÷ its cycles an execution), their product, and bytes saved (positive
= smaller). The argument for equivalence covers every entry, every exit and everything live after
each. Nothing is better than a wrong candidate: return none if none is right.

## What a skeptic does

One lens each - **semantics** (every path in and out, every live register, flag and byte, the
interrupt, the stack), **the machine** (the CPU's real opcodes and cycle counts, page crossings,
branch ranges, self-modifying operands, code read as data, the assembler), **the project** (its
rules, protected code, generated sources, paging, the free space, paths the proofs never reach).
Two skeptics (semantics and machine) for small claims, all three from THREE_SKEPTICS_FROM cycles a
pass (5). Each reads the source itself, tries to refute, and refutes when unsure. A skeptic's
recount of cycles and bytes is kept with its vote.

## The rules

The project's `CLAUDE.md` rules hold (the original is the specification; measure, do not
recall). For a grind in particular:

- **Same behaviour on every path**, not only the ones the proofs run. The skeptics' reasoning is
  the only check on the paths the gate does not run; add a check when a path matters.
- **Protected code is never changed** (`grind_config.py` PROTECT, PROTECT_BYTES; marked in the
  window). Raster timing first: a cycle saved before a timed write moves the write.
- **Generated sources are not hand-edited** (GENERATED): an improvement there is a change to the
  generator, proposed and gated like any other but outside the window workflow.
- **No data moves, no new RAM.** Tables, workspace and zero page stay where they are. A byte the
  annotations show dead may be reused as a temporary only if nothing else - the interrupt included
  - can read it in between, and the skeptics agree.
- **Self-modifying code**: the operand some code writes must still be where it writes it.
- **Paging.** Code in a sideways bank runs with that bank paged (and ANDY in or out on a Master);
  with ACCCON's X bit set `&3000-&7FFF` is shadow RAM. New code must read and write the same RAM
  the old did in each state.
- **Each kept batch is a commit** with its ids, the checks it passed and the cycles it saved; the
  ledger is committed with it. Never add up claimed savings as a result: only the gate's
  measurements count.

## Room

A candidate that grows its region past its free space must fail to assemble: every region the
code lives in needs an ASSERT on its end (the template's `CODE` line and the build's own ASSERTs),
and NO_ROOM in the config is the text those ASSERTs print. Before a round, list each source's
region and its free bytes from the listing (the `SKIP`s and ASSERTs), with the date, in the
project's docs: the optimisers and the project skeptic read it. Stryker's Run's table had nine
regions, from 1,044 bytes free in main RAM to 0 in its zero-page block.

## Reporting

After a round: windows evaluated, candidates by status (approved, refuted, unreviewed; then
accepted, failed, slower, stale, no room, no gain), what was kept with its measured saving per
batch, and what the skeptics refuted most often (the next round's optimiser prompt can say so).
