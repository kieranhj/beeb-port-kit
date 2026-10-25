---
name: beeb-run-suite
description: Run every headless oracle of a BBC Micro port after a build - tools/verify_cmds.py prints the lines from the symbol dump, tools/run_suite.py runs them N at a time into a scratch directory and judges each by its exit code. Use after any build that is going to be committed, merged or published, when the user asks to run the suite or the oracles, or when one oracle passing is about to be called "verified".
---

# Run the suite

Every oracle, not the newest one. 1942's `verify_dynamic` and `verify_scroll` were dead for some
time and nobody noticed, because only the sprite oracle was being run - and the dead one answered
zeros with exit 0 (its `BUGS.md` #9). The suite is `tools/verify_cmds.py` (the lines, from the
symbol dump) and `tools/run_suite.py` (the runner). `docs/verification.md` "Headless harnesses"
has the contract.

**Verdict:** each line's EXIT CODE against its `expect` (0, or 1 for a negative control)
**Never:** grep the outputs for "pass" - field names match it
**OUT_DIR:** absolute, outside the repo, and not the home folder - the session scratchpad or a temp directory

## Steps

1. **Build every variant the lines need, then do not build again until the suite finishes.**
   Every line reads the build's disc and its symbol dump; a rebuild under a running suite scores
   half of it on one build and half on another. In the template that is `.\build.ps1` and
   `.\build.ps1 -Master` (or `make` and `make master`), and `examples\vscroll\build.ps1`
   (PowerShell only). If the
   project has a build meant for the suite (1942's `-PlayBoot` boots straight into play), use it.

2. **Print the lines** and read them, once, for what is missing:

   ```bash
   python tools/verify_cmds.py
   ```

   Each has a comment saying why the run exists. A build that is not there is reported on stderr
   ("no build/game-master.ssd ... build it"), not skipped silently: build it, or say in the
   report that those lines did not run.

3. **Run them**, N at a time (4 by default; 1942 ran 10 on a desktop - each is a whole emulator,
   so mind the memory):

   ```bash
   python tools/run_suite.py <scratchpad>/suite-<date> 4
   ```

   The environment each line wants is passed as a dict, so it runs the same from PowerShell, cmd
   or a POSIX shell. Long suites: run it detached and wait for it to exit, rather than inside a
   tool call with a time limit.

4. **Read `summary.txt`**: a verdict, exit code, expected code and time for every line. For each
   FAIL, open its `NNN.out` - the command is its first line, the reason the run exists its
   second, and the oracle's own JSON is last.

5. **If (nearly) every line failed, suspect the TOOLS before the port.** The summary says so. 1942
   lost a whole suite at once to a new Baron listing layout (`BUGS.md` #26) and to jsbeeb 2.x
   changing `keyDown` from a number to a string - both failed every oracle identically on a good
   build. Check the `[jsbeeb x.y.z]` line in `000.out` and the build's dump before touching code.

6. **Exit 2 is "could not judge"**, not "wrong": a missing symbol, a stale build, a disc that did
   not boot. Fix the harness or the build, then re-run that line on its own.

7. **A known false failure has a signature** - write it in the oracle's doc, and recognise it
   (1942's sprite oracle past a death: 175 ticks wrong on a correct picture). Anything else is a
   defect until shown otherwise.

8. **Record the result** in the commit body: "suite 7 of 7, jsbeeb 2.10.2, 2026-10-25", the lines
   that did not run and why, and any FAIL left with its reason. Compare a cycle figure only with
   one from the same jsbeeb.
