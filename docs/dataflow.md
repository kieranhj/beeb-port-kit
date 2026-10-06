# Static analysis: beebgame's dataflow tools on a Baron build (2026-10-06)

The kit has always checked code by running it: the buffer oracle, the cycle pair, the A/B
differential. This is the other half - reading the linked program and saying, for every
instruction, which registers and flags are live, which values are known and what range every
byte can hold. It finds bytes to save at no cycle cost, register ABIs, dead code and the odd bug,
and it is the tool to reach for when a port runs out of RAM, which every port so far has.

The analyses are **Eben Upton's**, written for his engine
[beebgame](https://github.com/ebenupton/beebgame) (`tools/dataflow`, its README is the manual)
and used on Commando to take about 400 bytes out behind a replay gate. The kit runs them
**unmodified at a pinned commit** and supplies the one thing a Baron build lacks: the ld65 debug
file they read.

```
python tools/analyse.py report      # ~2 s: findings, register ABIs   -> build/dataflow/
python tools/analyse.py annotate    # the sources with the state before every instruction
                                    #                                  -> build/annotated/
python tools/analyse.py patterns    # mechanical finds over the ranges, printed
```

Build first. The tool reads `build/game.lst`, `build/game.symbols.json` and
`build/game-raw.ssd` - what every kit build already writes - and never reassembles.

## What runs, and where it comes from

| Piece | Where | Whose |
|---|---|---|
| `tools/analyse.py` | template | the kit's: fetch, verify, convert, run |
| `tools/baron_dbg.py` | template (fork of `py/beeb_port_kit/baron_dbg.py`, tested in `py/tests/test_baron_dbg.py`) | the kit's: Baron build -> `game.dbg` |
| `tools/dataflow_config.py` | template | the project's: interrupt entries, source directory |
| `model analysis forward findings dataflow dom ranges annotate patterns gamecfg` | `build/dataflow-upstream/<commit>/`, gitignored | beebgame's, fetched |

**Fetched, not vendored, because beebgame has no licence file yet** (2026-10-06). Copying it
into an MIT kit is not ours to do; running a public repository's code is. `analyse.py` holds the
commit (`PIN`) and the SHA-256 of all eleven files, takes them from a local checkout with `git
show <commit>:...` (`$BEEBGAME`, then `../../beebgame`, then `../beebgame`) or else GitHub's
archive of that commit, and refuses to run anything if one hash differs. Both routes were tested
on 2026-10-06. If beebgame gets a licence, vendoring it like `tools/zx02src/` becomes an option;
the pin and the hashes would carry over unchanged.

**Moving the pin** is a decision, not a refresh. Read what changed upstream, run `python
tools/analyse.py --pin <commit>` for the new hashes, run all three on the template and on one
real port, compare with the old results, and only then replace `PIN` and `SHA256`.

## The converter: what it does and cannot know

`baron_dbg.py`'s header has the whole account. In short:

- **Code versus data** comes from the listing: every emitted statement, macros expanded, with
  its address and bytes, in its `SECTION`. Section bytes come from the raw disc, so data the
  listing elides with `...` is exact; a section not saved to the disc falls back to the
  listing's bytes and says so.
- **The source line** is not in a Baron listing, so the converter re-finds it. It walks the
  sources from the main file, following `INCLUDE` and `MACRO` as the listing does, and matches
  each listed statement to the next one in its file. Inside an expansion, the call's line is
  the place. Each run prints `N placed, M not placed`. A statement it cannot place is still
  analysed, but it is reported against the generated `stmts.s` rather than the source, so a
  non-zero M means some findings point nowhere useful. Measured on 2026-10-06: the template had
  573 of 573 placed, and puzzle-beeble 11,124 of 11,124 across 39 files and 12 sections.
- **References** are not in a Baron build either, and the analysis needs them to know which code
  has its address taken (a dispatch table, `lda #LO(x)`). The converter takes them from the
  statement text, resolving each name through the `{ }` scopes. A wrong resolution errs
  towards "taken", which loses precision but never soundness.
- **Two upstream functions are patched in memory** as the tools run, and nothing else is
  changed. Both are worth reporting upstream:
  - `model.Source.short` joins paths with `os.sep`, and every caller compares against `/`, so
    on Windows nothing counts as the game's and nothing is reported.
  - When the range analysis runs out of its step budget (3,000,000 a round), it stops partway
    through but still calls itself converged. It caches the result as a sound starting point
    and writes annotations with no warning. `analyse.py` marks such a run unconverged, so
    annotate's own NOT-sound banner goes on every file. It also deletes the cache and prints
    a warning. `--budget N` raises the limit.

## Reading the results on a Baron port: two traps

**Zero page is shared, and the analysis sees the byte, not the name.** Baron's allocator gives
one byte to every variable whose lifetime doesn't overlap another's. The converter names such a
byte by all of its variables, for example `fill_ptr/scroll/zxsrc`. A finding whose evidence
relies on two of those names being equal describes **this allocation**, not the program. On
puzzle-beeble, `lda te_w : sta te_c` was reported as a removable `known_store` because `te_w`
and `te_c` happened to share a byte. Delete that store and the code works until the allocator
moves them apart. **Discard any finding whose argument relies on a slash-named byte holding two
of its names at once.**

**Link-time coincidences are findings too.** The template's `lda #HI(T1_I3)` is "already in A"
only because both bytes of 1,028 are 4. That holds until the constant changes. beebgame's
README says the same: "they hold for this build". Read every `imm_load`, `const_operand` and
`known_*` finding's evidence for a constant before taking it.

## What it found, measured 2026-10-06

| | Template | puzzle-beeble (working tree, `0e0b57f`+) |
|---|---|---|
| Instructions | 557 | 9,380 |
| `report` | 6 findings, 11 bytes, ~2 s | 122 findings, 129 bytes (upper bound), ~4 s |
| `annotate` (range analysis, no cache) | ~2 min, converged | 18.5 min, then **ran out of steps**: 8,295 of 9,380 instructions reached, so not sound (see above) |
| Checked by hand | all 6: correct, one a constant coincidence | 3 of the riskier ones: one allocator artefact (above), and **one real bug**: `shooter.6502:303` loads `tk_frame+1` and overwrites it at once with `tk_frame`, so the high byte is never tested |

So the findings are good leads and nothing more. The `report` analysis (liveness and
constants) is fast and complete on a full game. The range analysis, as pinned, doesn't yet
finish on one. Until it does, a port gets `report` and the register ABIs, and gets ranges only
for code small enough to converge. The totals overlap and are an upper bound, and
some of the findings hold only for this build.

## Using it to shrink code

The rules, the same as beebgame's README "a suggested farm", which is where they were learned:

1. **Every change goes through the port's own behavioural gate**: the buffer oracle, the A/B
   differential at equal state (verification procedure 14) and the sound check. A static
   argument is a reason to try a change, not a proof that it is right.
2. **Apply a few at a time** and bisect failures. Findings overlap: a dead store's load may only
   become dead once the store goes.
3. **Audit afterwards against a snapshot**, looking for paths the gate never runs. On Commando,
   the audit caught two accepted rewrites that broke a mission no replay reached.
4. **Re-run after every change.** Addresses move, ranges change and allocations shift.

Mechanical edits that are meant to change nothing else still get `beeb-identical-build`'s
listing-stream diff.
