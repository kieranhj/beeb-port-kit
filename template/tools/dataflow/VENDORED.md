# beebgame's tools/dataflow, vendored

Eben Upton's static analyses of a linked 6502 program, from https://github.com/ebenupton/beebgame
at **commit `235e890c4b3d13c0eff36b5f32850ace4050643b`** (2026-10-06), **unmodified**. MIT
(`LICENSE`, byte-identical to upstream's). That commit is `main` after Eben merged the kit's two
fixes, [#4](https://github.com/ebenupton/beebgame/pull/4) (paths on Windows) and
[#5](https://github.com/ebenupton/beebgame/pull/5) (a range run cut off by its step budget is
not converged), so `../analyse.py` no longer patches anything as the tools run.

`../analyse.py` holds the commit and every file's SHA-256 and **refuses to run a copy that
differs**, so never edit these: a change belongs upstream. `.gitattributes` marks this folder
`-text`, because a CRLF checkout would fail its own check. The kit's `docs/dataflow.md` says
what the tools do on a Baron or beebasm build and how to read the results.

## History

| Pin | Date | Why |
| --- | --- | --- |
| `77bbdb6` | 2026-10-06 | First run, fetched at run time (no licence yet) |
| `e07f8b2` | 2026-10-06 | Eben's MIT licence; vendored. Analysis files byte-identical to `77bbdb6` |
| `235e890` | 2026-10-06 | #4 and #5 merged; both of `analyse.py`'s in-memory patches dropped. Changes since `e07f8b2`: `model.py` (#4, and `85da262` dropping the `hazel.bin` bank name, which neither converter writes), `ranges.py` (#5), `README.md` |

## Checks before installing `235e890`, 2026-10-06, with no patches

| Check | Result |
| --- | --- |
| All 12 files by both routes (GitHub's archive, and `git show` in a fresh clone) | the same SHA-256, equal to `analyse.py`'s |
| The template, `python tools/analyse.py all` | 573 of 573 placed; `report` 6 findings, 11 bytes; range analysis converged (557 of 557), cache written; `patterns` the same `const_load`. **Identical** to `e07f8b2` with the patches |
| The template, `RANGES_BUDGET` 20,000 | upstream's own banner on every file, its WARNING in `summary.md`, no cache. What the dropped patch did |
| puzzle-beeble's converted build | 9,380 instructions, 122 findings, 129 bytes: identical |
| Edge Grinder (`tools/beebasm_dataflow.py`) | 83 findings, 106 bytes; range analysis converged (4,051 of 4,051): identical |
| Paradroid (`tools/beebasm_dataflow.py`) | 371 findings, 274 bytes: identical |
| `py/` test suite | 93 run, 2 skip (Paradroid tool paths), all pass |

**Upgrade** with `python tools/analyse.py report --try <commit>` first: it runs that commit
from `build/dataflow-upstream/` and leaves this copy alone. Then run `python tools/analyse.py
--vendor <commit>`, paste the `PIN` and `SHA256` it prints into `analyse.py`, and rerun the
table above.
