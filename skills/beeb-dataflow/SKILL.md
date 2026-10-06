---
name: beeb-dataflow
description: Run static analysis over the BBC Micro port's linked 6502 - liveness, known values, value ranges, register ABIs and the bytes they can save - with beebgame's dataflow tools on the Baron build, and turn the findings into changes safely. Use when the port is short of RAM or code space, when asked what a routine's register contract is, what a byte can hold at a point, whether code is dead, or to hunt for smaller code.
---

# Static analysis with beebgame's dataflow tools

Reads what the build left and never runs the game. The kit's `docs/dataflow.md` is the long
form: where the analyses come from, how a Baron build becomes the debug file they read, and the
two traps specific to Baron.

**A beebasm project** uses `tools/beebasm_dataflow.py` instead (the kit's `py/beeb_port_kit/` fork, with a `tools/dataflow_config.py` naming `LISTING`, `SOURCES`, `ISR_ROOTS`). Findings then point at the nearest label rather than a `file:line` (`docs/dataflow.md`, "BeebASM projects"). Steps 4-6 apply unchanged.

**Needs (Baron):** `tools/analyse.py`, `tools/baron_dbg.py`, `tools/dataflow_config.py`, `tools/listing.py`,
`tools/dfs.py` and the vendored `tools/dataflow/` (all in the template); Python 3
**Reads:** `build/game.lst`, `build/game.symbols.json`, `build/game-raw.ssd` - the project's names
for them are in `CLAUDE.md` "Build"; pass `--listing`, `--symbols`, `--disc` if they differ

## Steps

1. **Build, then check the config.** `tools/dataflow_config.py` must name every interrupt entry
   the game installs in `ISR_ROOTS` (`grep -n "IRQ1V" src` - each handler stored there, and any
   front-end handler). An interrupt left out is analysed as ordinary code, and every claim about
   bytes it writes is then wrong.

2. **Run the report.**

   ```powershell
   python tools/analyse.py report
   ```

   Read the converter's line first: `baron_dbg: N statements, N placed, 0 not placed`. A
   non-zero "not placed" means some findings point at `stmts.s` rather than the sources. Say so
   when quoting them. `build/dataflow/report.md` holds the findings and `abi.md` each routine's
   registers in and out.

3. **For ranges, run annotate.** `python tools/analyse.py annotate` takes about 2 minutes the
   first time on the template, longer on a full game, and seconds after that. Then read
   `build/annotated/src/<file>` with `;|` and the state before each instruction. The notation
   is in beebgame's README, "The annotations", in `tools/dataflow/README.md`.
   `summary.md` lists the assumptions the ranges rest on. Read it before believing a `never`.
   **If it printed `WARNING: the range analysis ran out of steps`**, or the files open with
   `NOT sound`, the ranges are unusable as they stand. Say so, and either rerun with
   `--budget` (each 3,000,000 steps took about 6 minutes on a 9,000-instruction game) or work
   from `report` alone.

4. **Check each finding against the source before proposing it.** Discard it if:
   - its evidence relies on a **slash-named zero-page byte**, such as `te_c/te_w`, being two of
     its names at once. That is Baron's allocator sharing a byte, not the program;
   - it relies on a **link-time constant** (`imm_load`, `const_operand`, `known_*` with a value
     that comes from a computed equate) whose value is a coincidence of the current build;
   - it sits in **timing code** (a delay loop or a raster-timed write sequence), where a "dead"
     instruction is still a delay.

   Treat a `dead_insn` or `reload` that makes the surrounding code look wrong (a load overwritten
   at once, a test of the wrong byte) as a **possible bug**, and report it as one, not as a
   saving.

5. **Change a few at a time, behind the gate.** Run the port's oracle, the A/B differential
   (`docs/verification.md` 14) and the sound check, plus `beeb-identical-build` for anything
   meant to be mechanical. Bisect failures. Re-run the report after each batch.

6. **Audit what was accepted** against the source as it was before the batch, hunting for paths
   the gate never runs (a level, a menu, a game-over route). This step is not optional:
   Commando's audit caught two accepted rewrites that broke a mission no replay reached.

## Report

Quote the converter's placed count, the finding counts by category, which findings were checked
by hand and what each was (saving, artefact, coincidence or bug), and the gate's result for
anything changed. Never quote a byte total as savings: it is an upper bound over overlapping
findings.
