# Baron, and BeebASM as the legacy (2026-09-07)

The kit assembles with [Baron](https://github.com/waitingforvsync/baron), Rich Talbot-Watkins's
ground-up rewrite of BeebASM (MIT, active - the sections design changed on 2026-09-06). `lib/`
and `template/` are both Baron. BeebASM is the legacy: the two shipping ports are BeebASM
projects, and this file records exactly what differs so either direction is a short walk.

Pin the version, **and keep the pinned exe in this project**. The builds find `baron` through
`$BARON`, then `bin/`, then the PATH, never through a path written into the build
(`docs/build-portability.md`). On this machine the kit's own copy is `template\bin\baron.exe`
(gitignored), named in the template's gitignored `local.ps1`. Binaries are on the project's
releases page; the language is still moving, so a build that worked is worth keeping the exe for.

**Do not upgrade a shared tools folder to do it.** `..\..\Bin\` holds `beebasm.exe`, `zx02.exe`
and a `baron.exe` that *every* BBC project on the machine resolves - 1942 among them - so
replacing the exe there moves projects that never asked to move. That folder stays on the
release binary (0.3.0, 2026-09-07); the kit runs the newer build out of its own `bin\`.

**`--version` does not identify a build.** The kit's `template\bin\baron.exe` is `main` at
`7213c8b` (2026-09-14), built here from source, and it reports `baron 0.3.0.0` - the same string
as the 0.3.0 release binary of 2026-09-07 still in `..\..\Bin\`, which does not have
`--symbols`, `--pad`, the `INCLUDE` fix or the relaxed symbol naming. Two different assemblers,
one version string, both on this machine. So a version string cannot tell you which you are
running: ask `baron --help | grep symbols` for the September/post-September split, assemble a
label named `.next` for the 14th's, or check the file date. Watch the releases page for a tagged
build that bumps it.

## Why

Measured on this kit, 2026-09-07, not taken from the READMEs:

| | Result |
|---|---|
| All of `lib/` converted, then the template rebuilt on it | every byte of `Game` and `PANEL` unchanged again - the conversion is provably cosmetic |
| The template built with Baron vs BeebASM | `Game` (1,087 bytes DEV, 1,138 MASTER) and `PANEL` **byte-identical**; `!BOOT` differs only in the timestamp; final `game.ssd` differs in those bytes alone |
| Both discs booted in jsbeeb (`B-DFS1.2` and `Master`) | `&4A00` reads back identical to `src/data/panel.bin`, `zxdst` left at `&5400` - same as the BeebASM build |
| All of `lib/` assembled under Baron (a ported `test_lib`) | 1,509-byte image **byte-identical**, at a cost of 6 changed lines across 8 files |
| A forward-referenced zero-page symbol | assembled as **zero page** - BeebASM's pass-1 sizing trap does not exist |

So the bytes are the same bytes. What changes is the toolchain around them.

## What Baron fixes, of the gotchas this kit documents

- **The beebasm pass-1 sizing trap.** An undefined symbol was assembled as absolute in pass 1 and
  errored on the size change in pass 2, so zero-page slots had to be declared before the first
  file that used one. Baron assembles until the program converges. Measured.
- **No `IFDEF`, and a symbol defined twice is an error**, which is why every invocation had to
  pass `-D RELEASE=0 -D MASTER=0`. Baron has `DEFINED()`. The build scripts still pass both, so
  that a build says what it is - now a choice rather than a workaround.
- **`SAVE` writes loose host files when `-do` is missing.** Baron writes nothing without `-p` or
  `-o`, and warns. `template/.gitignore` no longer needs `/Game`, `/PANEL`, `/!BOOT`.
- **beebasm writes progress to stderr**, which trips `$ErrorActionPreference = 'Stop'` in
  PowerShell even on success. Baron is silent on success; stderr carries diagnostics only.
  Measured: empty stderr, exit 0.
- **`CLEAR` releases the overwrite check.** A section's `guard` attribute is checked when the
  section closes and reports the overshoot in bytes, without stopping the assembly.
- **One error at a time.** Baron reports every error in one run, `file:line:col: error: message`.

## What landed upstream on 2026-09-13 and -14

Four things the kit asked for, all in the binary now installed. Built from source here
(`cmake -B build -G "Visual Studio 18 2026" -A x64`, submodule `richc` initialised first); a
second build with `-DBARON_TESTS=ON` runs Baron's own suite, 420 tests, 420 ok.

| Asked | Fixed | What it does |
|---|---|---|
| [#5](https://github.com/waitingforvsync/baron/issues/5) - no symbol dump | `45e5cb8` | `--symbols <file>` writes every resolved symbol as JSON, one object per source file: labels, computed constants **with their values**, and `ZA_AUTO` allocations. On the template that is 309 top-level symbols where the listing shows 48 |
| [#1](https://github.com/waitingforvsync/baron/issues/1) - a failed `INCLUDE` went unreported when something later depended on it | `b330d32` | An unreadable `INCLUDE` is now fatal, like `INCBIN`'s, so it reports on the spot. The trade: several wrong paths report one per run rather than all at once |
| [#4](https://github.com/waitingforvsync/baron/issues/4) - no full-size image | `e3359e7` | `--pad` (with `-o`) pads to 800 sectors, filler `&E5`. **The builds do not pass it**, and should not: an unpadded image boots everywhere the kit runs (`docs/verification.md`), and padding is a publishing convention, not a build step |
| [#6](https://github.com/waitingforvsync/baron/issues/6) - a label colliding with a keyword or a macro was refused, saying only "Expected a label name" | `7213c8b` | The restriction is **gone** rather than the message improved: a symbol may now be named after a keyword, because the two do not clash in an expression. See below - it changes what a port may name things |

What changed in the kit, the same day: both builds now pass `--symbols`, writing
`build/game.symbols.json` beside the listing, and that file is where addresses come from
(`docs/verification.md`). The image is **byte-identical** across the two binaries - same
`sha256`, checked before installing.

`45e5cb8` also reshaped the `-v` listing: a label now prints with its own address
(`  1900  .start`), where it used to sit on its own line, and the byte field widened from 16
columns to 26. Two consequences. First, the kit's `listing.py` no longer keys off fixed columns -
it matches the byte field as a pattern, and reads listings from either side of the change.
Second, **the old layout could give a wrong address**: a label at the end of a section took the
address of the next line that carried one, which is the *start of the next section* - the
template's `end` read as `&4A00` when it is `&1DBE`. Any address quoted from a listing written
before 2026-09-13 is worth re-checking if it is the last label of a section.

### Symbols may be named after keywords (`7213c8b`)

**This is the one that changes what a port may write.** A label whose name collided with a
keyword, or with a macro (names are matched case-insensitively), used to be refused - and the
message said only `Expected a label name`, which reads as a syntax error somewhere else. In a
1942 port that cost five build cycles on `clr`, `byte`, `div`, `next` and a `hud_row` against a
`HUD_ROW` macro, which is what [#6](https://github.com/waitingforvsync/baron/issues/6) reported.
Rather than name the collision, Rich removed the restriction: a keyword and a symbol do not
clash in an expression, so there is nothing to disambiguate except an assignment.

Measured here on 2026-09-14, the same four files under each binary:

| | 0.3.0, 2026-09-07 | `7213c8b` |
|---|---|---|
| `.next`, `.clr`, and `.foo` beside a `MACRO FOO` | `error: Expected a label name` | assembles, exit 0 |
| `next = 12` | `error: NEXT without a FOR` | `error: NEXT without a FOR` - **still refused**, and the message is still about the keyword, not the name |
| `@next = 12` | `error: Unexpected token` | assembles, exit 0 |

So: name a label whatever the original called it, and **prefix an assignment with `@` when the
name is a keyword** (C#'s convention). Nothing in `lib/` or the template needed either - no name
in the kit collides - but a port transcribing a 6502 source that uses `next`, `clr`, `div` or
`byte` as labels no longer has to rename anything, and the old workaround (renaming to
`next_row`, `do_clr`) can be undone if the names were only changed for this.

## What it costs, and what we did about it

| BeebASM | Here |
|---|---|
| `ORG` / `SAVE` / `GUARD` / `CLEAR` | `SECTION name, org=, guard=, filename=, exec=` ... `ENDSECTION`. The filename **is** the request to save. Two sections may share an address, so `PANEL`'s `CLEAR` is gone |
| `ASSERT cond` | A two-line `MACRO ASSERT` in `beeb.h.6502` (`IF NOT(c) : ERROR ... : ENDIF`), so all 16 assertions in `main.6502` read exactly as they did. Baron reports the `ERROR` and adds `Note: Expanded from here` at the call, so an assertion still names its own line |
| `TIME$` | Gone. `tools/build_stamp.py` (run by the `Makefile` and `build.ps1`) writes `build/build_time.6502` - one line, `BUILD_TIME = "..."` - which `main.6502` includes. Not a `-D`: **Windows PowerShell cannot hand a quoted string containing spaces to a native exe** (three forms tried, all mangled). The time is the source's (`SOURCE_DATE_EPOCH`, else the last commit), so a rebuild is byte-identical on any machine |
| `INCLUDE` resolves from the working directory | Baron resolves it **relative to the including file**: `src/main.6502` says `INCLUDE "lib/irq.6502"`, not `"src/lib/irq.6502"`. Watch for this when forking a file into a different directory. A wrong path once surfaced as a confusing parse error downstream rather than "could not read"; that was [#1](https://github.com/waitingforvsync/baron/issues/1), fixed on 2026-09-13, and a bad path now says so at the `INCLUDE` |
| `CPU 0` | NMOS is the default; `cmos = TRUE` on a section enables the 65C02 |
| `P%` | `*` (both spellings work) |
| `PRINT ~x` prints one value | `~` swallows the whole expression after it, so `~CODE_TOP - end` is `~(CODE_TOP - end)`. Parenthesise |
| `TRUE` is -1 | `TRUE` is 1 (`--beebasm-true` restores it). Nothing in the kit relied on it |
| `.asm` | `.6502`, which the [VS Code extension](https://marketplace.visualstudio.com/items?itemName=RichTalbot-Watkins.baron-vsc) keys on |

## The zero-page allocator

In use in the template since 2026-09-07. `ZA_POOL &00..&8F`, then `ZA_AUTO1`/`ZA_AUTO2`
declarations; Baron traces each value's life and packs the ones that never overlap onto the same
byte. What it bought, measured:

| | Before | After |
|---|---|---|
| Zero page for 17 variables | 26 bytes, hand-laid | **16 bytes**, `&00-&0F` |
| Code | 1,087 bytes | 1,081 - the boot-time zero-page wipe loop is gone, because every variable now has a provable first write |
| Behaviour (both models) | 100 fields / 100 frames, 50 passes, scroll 0 -> 200 under X, panel identical | **the same, exactly** |

`scroll` lives on `&00` - the byte `zxsrc` used while the panel was unpacking and `fill_ptr`
used while the strip was being filled. That is the depacker header's "borrowed from state that
is not live while it runs", checked by the tool instead of asserted by a comment.

Two markers carry the facts the instruction stream does not: `ZA_ENTRY` on `main` (`*RUN` enters
there; nothing in the program calls it) and `ZA_INTERRUPT` on `irq.6502`'s handler. **Both are
load-bearing.** Removing the `ZA_INTERRUPT` gets a warning - `ZA_AUTO used in code unreachable
from any entry` - and then a build that puts `frame_ready` and `crtc_park` on one byte and hangs
at boot. Measured, deliberately, so the failure mode is on record.

The rules that bite: an address does not exist until the assembly converges, so a `ZA_AUTO` name
cannot decide the program's shape (`IF v`, `SKIP v`, `FOR n = v..8`, `org = v` are all refused,
clearly); `(var),Y` needs a `ZA_AUTO2`; an indexed store into the pool proves nothing to the
analysis, which is why the blanket wipe went. Anything shared with the outside world - BASIC
pokes, a fixed API - keeps a hand-picked address.

Still unused, and worth a look when a real port needs them: `ZA_DISCARD` for arrays rebuilt
through `STA arr,X`, `ZA_CANCALL`/`ZA_CANJUMP` for dispatch tables, `BITABS`/`BITZP` for the
skip trick.


Also unused so far: lists and broadcasting (a sine table in one `EQUB`), user `FUNCTION`s,
`BASIC` ... `ENDBASIC` for a tokenised BASIC loader, and macro overloading.

## Going back to BeebASM

A port that wants BeebASM reverses the table above. The whole delta measured on `lib/` was six
lines - the `ASSERT` shim in `beeb.h`, the `TIME$` line in `boot_stamp` - plus the `SECTION`
wrappers in whatever includes them, and the file extensions. Everything else, macros and all,
assembles unchanged under both. The BeebASM `lib/` and template are in this repository's
history: commit `5355d03`, the commit before the Baron port (it was the tip of a
`zx02-depacker` branch, deleted 2026-09-11 once it was an ancestor of `master`).
