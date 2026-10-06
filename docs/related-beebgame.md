# beebgame, and what this kit shares with it (2026-10-06)

[beebgame](https://github.com/ebenupton/beebgame) is Eben Upton's scrolling-platformer engine for
the BBC Model B with 64K of sideways RAM and the Master 128. It's ca65/ld65, MIT, and its games
are Cleo and Commando. This kit and beebgame solve neighbouring problems: the kit **ports existing
games** with an agent, and beebgame is an **engine new games are written on**. Their assemblers
differ (Baron and beebasm here, ca65 there), so they share pieces, facts and fixes, not a
codebase. Neither depends on the other, apart from the one pinned copy below.

This file records the link. It was read against beebgame `main` at
`1a71c25`. Refresh it when either side changes something the other uses, not on a schedule.

## Taken from beebgame

| What | beebgame | Here | How it's kept |
| --- | --- | --- | --- |
| The static analyses: liveness, constants, value ranges, register ABIs, findings | `tools/dataflow/` | `template/tools/dataflow/`, run by `tools/analyse.py` (Baron) and `py/beeb_port_kit/beebasm_dataflow.py` (beebasm) | **Vendored unmodified at a pinned commit** (`235e890`), every file hash-checked before it runs. `VENDORED.md` has the pin history and the checks; `docs/dataflow.md` the account |
| The reviewer-then-skeptic review of annotated code ("a suggested farm") | `tools/dataflow/README.md` | `skills/beeb-dataflow/`; used on Edge Grinder's BANK0 and BANK1 | The method, rewritten for the kit's gates |
| Watford and Solidisk write-select board emulation on a jsbeeb Model B | `test/lib/boards.mjs` | `template/tools/boards.mjs`, checked by `tools/boards_check.mjs` | A fork, unchanged under a provenance header |
| The page-crossing branch list | `tools/pagecheck.py` (ld65 debug file) | `listing.py pages` (Baron listing), `crossings()` | Redone for Baron's listing; the idea, not the code |

## Sent to beebgame

| What | Where | State |
| --- | --- | --- |
| `Source.short()` joins with `/` on every host (Windows reported nothing) | [#1](https://github.com/ebenupton/beebgame/issues/1), [PR #4](https://github.com/ebenupton/beebgame/pull/4) | merged 2026-10-06 |
| A range run cut off by its step budget is not converged; `RANGES_BUDGET` | [#2](https://github.com/ebenupton/beebgame/issues/2), [PR #5](https://github.com/ebenupton/beebgame/pull/5) | merged 2026-10-06 |
| `findJsbeeb()` chooses jsbeeb by version and says which; `shiftKey()` for 2.x | [#3](https://github.com/ebenupton/beebgame/issues/3), [PR #6](https://github.com/ebenupton/beebgame/pull/6) | open |

## Left on purpose

- **The engine itself, `levelfile.py`, `sprpack.py`, `midi2snd.py`, the disc driver.** They're
  built for one architecture and its file formats. A port that wanted them would be a beebgame
  game, not a port.
- **`mkdfs.py`.** The kit's `dfs.py` already does this job, tested, and makes byte-identical
  discs.
- **`codecmp.py`.** The kit's `listing.py stream` compares emitted bytes, which is stronger than
  comparing source text.
- **The frame-exact harness (`frame_top`, scene fingerprints).** It's a good contract, but it's
  written around beebgame's engine. Its idea belongs in `verification.md` procedure 14 (A/B
  timing only at equal state). Not done yet.
- **Supporting Solidisk boards rather than refusing them.** beebgame patches every bank number
  and write-bank store at boot (`loader.s`, `DESIGN.md` §4). The kit's probe still refuses
  Solidisk; `boards.mjs` now lets a port measure what supporting it would take.

## Keeping in step

- **The dataflow pin moves as a decision.** `python tools/analyse.py report --try <commit>`, then
  `--vendor`, then redo `VENDORED.md`'s table. As of `1a71c25`, beebgame has moved on from the
  pin. Its "dataflow grind" commit changed `ranges.py` (+106 lines) and `gamecfg.py`, so it's the
  next candidate.
- **beebgame's README points back here.** That note, a "Related" section, is a separate small PR.
- **Facts found on one side are recorded on both.** Example: jsbeeb makes `&FE20-&FE3F` a 2 MHz
  access (`hardware-facts.md` §2).
