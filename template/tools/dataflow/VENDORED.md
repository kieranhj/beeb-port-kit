# beebgame's tools/dataflow, vendored

Eben Upton's static analyses of a linked 6502 program, from https://github.com/ebenupton/beebgame
at **commit `e07f8b25af4493a37f21604883949c3658eb5e53`** (2026-10-06), **unmodified**. MIT
(`LICENSE`, byte-identical to upstream's, which that commit added). The ten `.py` files and
`README.md` are byte-identical to `77bbdb6`, the commit they were first run at here; `e07f8b2`
is the pin because it is the one that licenses them.

`../analyse.py` holds the commit and every file's SHA-256 and **refuses to run a copy that
differs**, so never edit these: a change belongs upstream or in `analyse.py`'s in-memory
patches. `.gitattributes` marks this folder `-text`, because a CRLF checkout would fail its own
check. The kit's `docs/dataflow.md` says what the tools do on a Baron build, what the two
patches are, and how to read the results.

**Validated here before it was installed, 2026-10-06:**

| Check | Result |
|---|---|
| All 12 files, from the local checkout (`git show`) and from GitHub's archive of the commit | the same SHA-256 by both routes, equal to `analyse.py`'s |
| The template, `python tools/analyse.py all` | 573 of 573 statements placed; `report` 6 findings, 11 bytes, **identical** to the fetched `77bbdb6` run; range analysis converged (557 of 557 reached); `patterns` the same `const_load` |
| puzzle-beeble's build (converted into scratch, nothing written to that project) | 9,380 instructions, 122 findings, 129 bytes: **identical** to the fetched run |
| `py/` test suite, including the upstream model reading the template's converted build | 86 pass, 2 skip (Paradroid absent) |
| A copy with one file edited and one converted to CRLF | refused, naming both files; nothing ran |

**Upgrade** with `python tools/analyse.py report --try <commit>` first: it runs that commit
from `build/dataflow-upstream/` and leaves this copy alone. Compare with the results above on
the template and on one real port. Then run `python tools/analyse.py --vendor <commit>`, paste
the `PIN` and `SHA256` it prints into `analyse.py`, and rerun this table. Upstream issues
[#1](https://github.com/ebenupton/beebgame/issues/1) (Windows paths) and
[#2](https://github.com/ebenupton/beebgame/issues/2) (step budget reported as converged) are
the reasons to move. When one is fixed, drop the matching patch in `analyse.py`'s
`_run_upstream`.
