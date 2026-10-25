# Static analysis: beebgame's dataflow tools on a Baron build (2026-10-06)

The kit has always checked code by running it: the buffer oracle, the cycle pair, the A/B
differential. This is the other half - reading the linked program and saying, for every
instruction, which registers and flags are live, which values are known and what range every
byte can hold. It finds bytes to save at no cycle cost, register ABIs, dead code and the odd bug,
and it is the tool to reach for when a port runs out of RAM, which every port so far has.

The analyses are **Eben Upton's**, written for his engine
[beebgame](https://github.com/ebenupton/beebgame) (`tools/dataflow`, its README is the manual)
and used on Commando to take about 400 bytes out behind a replay gate. The template **vendors
them unmodified at a pinned commit** (`template/tools/dataflow/`, MIT) and supplies the one
thing a Baron build lacks: the ld65 debug file they read.

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
| `tools/analyse.py` | template | the kit's: verify, convert, run |
| `tools/baron_dbg.py` | template (fork of `py/beeb_port_kit/baron_dbg.py`, tested in `py/tests/test_baron_dbg.py`) | the kit's: Baron build -> `game.dbg` |
| `tools/dataflow_config.py` | template | the project's: interrupt entries, source directory |
| `tools/dataflow/`: `model analysis forward findings dataflow dom ranges annotate patterns gamecfg`, `README.md`, `LICENSE` | template, vendored; `VENDORED.md` beside them | beebgame's, MIT, at `235e890` |

**Vendored, unmodified, and checked every run.** beebgame took an MIT licence on 2026-10-06
(`e07f8b2`), the same day this was built, so the template carries its `tools/dataflow` the way
it carries `tools/zx02src`: `analyse.py` holds the commit (`PIN`) and the SHA-256 of all twelve
files and refuses to run a copy that differs. `.gitattributes` marks the folder `-text`, so a
Windows checkout doesn't convert the files to CRLF and fail its own check. The first version of
this tool fetched them at run time instead, for want of a licence. That route stays for looking
at other commits: `--try <commit>` runs one from `build/dataflow-upstream/`, and `--vendor
<commit>` replaces the vendored copy. Both read a beebgame checkout (`$BEEBGAME`,
`../../beebgame`, `../beebgame`) with `git show`, or else GitHub's archive of the commit.

**Moving the pin** is a decision, not a refresh. Read what changed upstream. `--try` the new
commit on the template and on one real port, and compare with the current results. Then
`--vendor` it, paste the `PIN` and `SHA256` it prints into `analyse.py`, and redo
`template/tools/dataflow/VENDORED.md`'s checks. The first move was on 2026-10-06, from `e07f8b2` to
`235e890`, which took the kit's two fixes upstream; the template's and three ports' results were
identical across it.

## The converter: what it does and cannot know

`baron_dbg.py`'s header has the whole account. In short:

- **Code versus data** comes from the listing: every emitted statement, macros expanded, with
  its address and bytes, in its `SECTION`. Section bytes come from the raw disc, so data the
  listing elides with `...` is exact; a section not saved to the disc falls back to the
  listing's bytes and says so. A `SECTION` inside another (a block copied down at start-up,
  rephased) takes its bytes from the disc file of the section that carries it; until
  2026-10-25 the inner `ENDSECTION` ended the outer section too and lost the rest of it (found
  by Stryker's Run). A disc of packed files is read through `read_disc` (`dfs.game_files`).
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
- **Nothing upstream is patched.** Until the pin moved to `235e890`, two functions were
  patched in memory here, and both fixes are now beebgame's own (merged 2026-10-06):
  - [#4](https://github.com/ebenupton/beebgame/pull/4): `model.Source.short` joined paths with
    `os.sep` while every caller compared against `/`, so on Windows nothing counted as the
    game's and nothing was reported.
  - [#5](https://github.com/ebenupton/beebgame/pull/5): a range run that ran out of its step
    budget stopped partway but still called itself converged, cached the result as a sound
    start and annotated with no warning. Now upstream marks it NOT sound and skips the cache.
    `--budget N` (or `$DATAFLOW_BUDGET`) sets upstream's `RANGES_BUDGET`, 3,000,000 a run by
    default.

## BeebASM projects

The two shipped ports are beebasm, and `py/beeb_port_kit/beebasm_dataflow.py` covers them: a
single file that converts the `-v` listing and runs the analyses from this kit's vendored copy.
Fork it into the project's `tools/` with a `tools/dataflow_config.py` that names `LISTING`,
`SOURCES` and `ISR_ROOTS`, and run `python tools/beebasm_dataflow.py [report|annotate|patterns]`
from the project root. It finds the kit through `$BEEB_PORT_KIT`, else `../beeb-port-kit`.
Paradroid and Edge Grinder carry it, each with a `docs/dataflow-report.md` of what it found.

A beebasm listing gives less than a Baron build:

- **No source lines.** It prints resolved operands (`LDA &0A00`), not source text, so findings
  point into a listing-shaped `build/dataflow-in/src/listing.s` with the nearest label. Search
  the sources by that label.
- **No references.** "Address taken" comes from scanning the sources: a label named anywhere
  other than as a `JSR`/`JMP`/branch target counts as taken. That over-counts, which costs
  findings but never correctness.
- **No sections.** They're inferred from `Saving file` lines and address jumps. Check the
  summary line against the listing's own memory map.
- **Long data may be cut short.** Edge Grinder's beebasm prints an `INCBIN` as three bytes and
  `...`. Paradroid's prints every byte. A cut line is taken to run to the next listed address,
  zero-filled, which the report never reads.

Measured on 2026-10-06:

| | Instructions | Findings | Bytes | Range analysis |
| --- | ---: | ---: | ---: | --- |
| Paradroid (`944578c`) | 22,556 | 371 | 274 | not run (larger than puzzle-beeble, which ran out of steps) |
| Edge Grinder (`0000aec`) | 4,051 | 83 | 106 | converged in 56 s |

`py/tests/test_beebasm_dataflow.py` covers both listing shapes, the `Saving file` split and the
address-taken scan. When those projects are on the machine, it also checks that the vendored
model reads their converted listings with no bad spans. Writing those tests found two bugs in
the first version, both fixed before anything was committed: a label sharing a line with a
statement hid that statement's references, and a bare address line (a zero-page variable)
attached its label to the next code address.

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
| Checked by hand | all 6: correct, one a constant coincidence | 3 of the riskier ones: one allocator artefact (above), and one dead load: `shooter.6502:303` loads `tk_frame+1` and overwrites it at once. It is a leftover from a commit that moved the high-byte test to line 288, so 2 bytes and 3 cycles a frame, not a bug. I called it a bug at first, without following the paths into it, and puzzle-beeble's session corrected me: the lesson is in the skill's step 4 |

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

## An interrupt that exits into the MOS: `isr_model.py` (2026-10-25)

Upstream takes the interrupt (`ISR_ROOTS`) to read and write ALL memory if anything it reaches
has an exit the analysis cannot follow - a `JMP` to the MOS, a `JMP (vector)`, a self-modified
operand - or a store through a pointer. Then no byte is a known value anywhere, and the ranges,
known values and the findings built on them go. `lib/irq.6502` ends in `RTI`, so the template
never meets it; a handler that chains to the MOS to keep its tick, or a music handler that calls
OSWORD through `JMP (WORDV)`, does. Every one of Stryker's Run's did, and its analysis knew no
memory byte until it wrote `tools/isr_model.py` (2026-10-16).

`template/tools/isr_model.py` is that file. `tools/analyse.py` installs it in the analysis's
own process (`tools/dataflow/` untouched: its SHA-256 check still passes) when
`dataflow_config.py` sets `ISR_MODEL = True`; it is off in the template. Then each site in
`ISR_MOS_EXITS` (`'file:line'` as `report.md`'s notes print it) is the MOS, returning having
touched only `MOS_WORKSPACE` (ranges you declare: an ASSUMPTION from the memory map, the
config's comment has Stryker's Run's); `ISR_POINTER_STORES` bounds a store through a pointer;
`ISR_PRESERVES` names what a handler saves and restores. Any exit not named still means all
memory, with a note naming it; a site named but not reached stops the run (exit 1), so a site
gone stale when code moved is an error. `report.md`'s Model notes say which were modelled.

`--config` goes BEFORE the job: `python tools/analyse.py --config F report`. After it,
argparse puts `--config F` among the pass-through extras, so the default config is passed too,
first; upstream takes the last, and the hook does likewise since 2026-10-25 (Stryker's Run's
took the first, and with `report --config F` ran without the model while upstream read F).

**Measured, 2026-10-25:**

- The template, `ISR_MODEL` off (the default): `report`'s output and every file in
  `build/dataflow/` identical to before the hook (6 findings, 11 bytes; the interrupt reads 9
  and writes 6 universe bytes). On (`--config` a copy with `ISR_MODEL = True`): the same
  findings and the same 9/6 bytes, and the model's note.
- A copy whose `irq_handler` ends `JMP irq_chain` to a `JMP &FFFF` patched with the old IRQ1V
  (a chain to the MOS): off, the interrupt reads and writes all 33 universe bytes and 6 findings
  (10 bytes) - `reg_xfer` gone, since nothing is known across it. On, with the `JMP &FFFF`
  named and Stryker's Run's `MOS_WORKSPACE`: reads 12, writes 10, and 7 findings (12 bytes),
  the `reg_xfer` back. On with nothing named: the note "unknown exit at src/lib/irq.6502:141
  (jmp $FFFF)" and all memory, as upstream. A named site the interrupt does not reach: "isr_model:
  the config names sites the interrupt does not reach", exit 1.

## Using it to take a Master port down to a Model B: `nmosify.py` (2026-10-25)

From Stryker's Run (its decision 73, `docs/briefs/model-b-lite.md` step 1). A Master port's
65SC12 instructions are rewritten as `lib/nmos.6502`'s macros, one per instruction at a site,
each named for the NMOS form its state allows; the annotation (`python tools/analyse.py
annotate`) is the state. `template/tools/nmosify.py`:

```
python tools/nmosify.py [--v-dead] report        # every site, its form; MANUAL for the rest
python tools/nmosify.py [--v-dead] apply         # the sources rewritten
python tools/nmosify.py [--v-dead] check         # on the build WITHOUT NMOS: every form still allowed
python tools/nmosify.py [--v-dead] check --nmos  # on the build WITH NMOS: what the forms newly read
```

The rules are `nmos.6502`'s: a register known 0 for an `STZ` (free), else a dead one loaded with
0; a flag known for a `BRA` (free), else `JMP`; `INC A`/`DEC A` by `ADC`/`SBC #1` where C is
known and C, V dead, else `CLC`/`SEC` first, else through a dead X or Y; `PHX`..`PLY` through a
dead A. `TSB`, `TRB`, `BIT #`, `BIT zp,X`, `(zp)` and anything after a `:` are MANUAL: an `IF
NMOS ... ELSE ... ENDIF` by hand, which the report then counts as `IF NMOS`. A form the analysis
cannot prove (`STZ_PHA`, `BVC_BIT6`) is checked by reading its callers and its line marked
`(hand`.

**Both checks, always.** `check` proves each form's register or flag free in the 65SC12 code;
it cannot see what an NMOS form newly READS, because there the instruction reads nothing.
`check --nmos` reads the NMOS build's annotation: a `BRA_xx`'s flag, an `STZ_A`'s zero
register, an `INC_A_ADC`'s C, as the other forms leave them. Stryker's Run found two clashes
that way, each from two forms safe alone; the kit's demonstration (below) makes one. Each
refuses an annotation of the wrong build (exit 2): an NMOS form of several instructions is
annotated one state per instruction only in the NMOS build.

**V.** The analysis keeps V live almost everywhere (few instructions write it), so the `INC A`
forms that need C and V dead are rarely allowed. `--v-dead` takes V as dead but where a
`BVC`/`BVS` reads it straight after a `BIT`, `ADC`, `SBC`, `CLV`, `PLP` or `RTI`, and checks
that claim over the whole annotation first (a V reader after a label, or after anything else,
refuses it). Stryker's Run assumed it in `check` alone, by hand; here both halves take it.

**Measured, 2026-10-25:**

- The template has no 65SC12 instruction: `report` 0 sites, `check` 0, exit 0.
- A copy of the template with seven written into `fill_play` (two `STZ`, `PHX`/`PLX`, two `INC
  A`, a `BRA`), its section `cmos = (NMOS = 0)`: `report --v-dead` chose `STZ_LDA` x2, `PHX_A`,
  `PLX_A`, `INC_A_CLC` x2, `BRA_CS` (10 bytes at most); `apply`; rebuilt without `NMOS`, the
  disc byte-identical to before; `check` 7 hold; built with `NMOS` (assembles under `cmos =
  FALSE`); `check --nmos`: **1 DOES NOT** - the `BRA_CS` after the `INC_A_CLC`, whose `CLC`
  leaves C unknown at the branch. The clash, by construction, and only the second half sees it.
- Stryker's Run's own annotation (read-only, a build without `NMOS`, 2026-10-25 01:52):
  `check --v-dead` 292 hold, 16 by hand, 10 not in that build, 0 no longer hold; `report` 41
  sites, all in `IF NMOS` blocks. Without `--v-dead`, 2 `INC_A_CLC` fail on V (Stryker's Run
  dropped V in `check` only). Its own copy of the tool, which zips the annotation against the
  current sources by line, reported 47 failures on the same annotation: the sources had moved
  since it was made. The kit's reads the annotation alone (the source text is in it), and
  `apply` refuses a line that no longer matches.
