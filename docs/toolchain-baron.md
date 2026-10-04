# Baron, and BeebASM as the legacy (2026-09-23)

The kit assembles with [Baron](https://github.com/waitingforvsync/baron), Rich Talbot-Watkins's
ground-up rewrite of BeebASM (MIT, active - the sections design changed on 2026-09-06, the
zero-page markers on 2026-09-23). `lib/` and `template/` are both Baron. BeebASM is the legacy:
the two shipping ports are BeebASM projects, and this file records exactly what differs so either
direction is a short walk.

Pin the version, **and keep the pinned exe in this project**. The builds find `baron` through
`$BARON`, then `bin/`, then the PATH, never through a path written into the build
(`docs/build-portability.md`). On this machine the kit's own copy is `template\bin\baron.exe`
(gitignored), named in the template's gitignored `local.ps1`. Binaries are on the project's
releases page; the language is still moving, so a build that worked is worth keeping the exe for.

**Do not upgrade a shared tools folder to do it.** `..\..\Bin\` holds `beebasm.exe`, `zx02.exe`
and a `baron.exe` that *every* BBC project on the machine resolves - 1942 among them - so
replacing the exe there moves projects that never asked to move. That folder stays on the
0.3.0 release binary of 2026-09-07; the kit runs the newer build out of its own `bin\`.

## The pinned version: 0.4.2 (2026-10-03)

**The kit builds on Baron 0.4.1 and later, and on nothing older.** The pin is the 0.4.2 release
binary (`baron.exe` from the [releases page](https://github.com/waitingforvsync/baron/releases/tag/v0.4.2),
`sha256 2c428495 87132a11 aeee5f52 ca965437 4a4ee499 d1ad53be e9bb8fd9 e8a816c6`).

**0.4.1 made `ASSERT` a statement, and that is what moved the pin.** `beeb.h.6502` had defined
`MACRO ASSERT` because Baron had no `ASSERT`; 0.4.1
([`d046a9a`](https://github.com/waitingforvsync/baron/commit/d046a9a), released 2026-09-30)
added one, and from then on that macro is `error: Reserved macro name` - so on any current Baron
the template, `lib/test/` and `examples/vscroll` all failed to build, while the 0.4.0 pin hid it.
Three projects building on the kit met it independently, and the
kit said nothing about which versions it supports. The macro is gone and the call
sites are unchanged: the statement takes both of its shapes (`ASSERT c`, `ASSERT c, msg`). There
is no source that builds on both sides - Baron has no version symbol, and a `MACRO ASSERT` is
refused even inside `IF FALSE` - so 0.4.0 and older are no longer supported.

What changed, measured on 2026-10-04 with Linux builds of the tags (`v0.4.1`, `v0.4.2`, and
`main@accc35c`), each against the old macro under 0.4.0:

| | Result |
|---|---|
| The template, `make`, `make release` and `make master`: `game.ssd`, `game-master.ssd` and both raw images | **byte-identical**, on all three |
| `lib/test/test_lib.6502`, `-D RELEASE=0` and `=1` | `TEST`, `BOOT` and `INFO` **byte-identical**; exit 0 and silent at `--warn 2` |
| `lib/test/run_test`, `andy_test`, `probe_test` | images **byte-identical**, exit 0 |
| `examples/vscroll` | image **byte-identical** |
| `game.lst` / `vscroll.lst` | each `ASSERT` line is gone - a macro call was listed, a statement is not. Nothing else moved |
| `game.symbols.json` / `vscroll.symbols.json` | entries like `"@0:2465.c": true` are gone: the macro's parameter `c`, one per expansion (14 in the DEV template's dump). Nothing else moved |
| A failing `ASSERT` | still fails the build, exit 1 (`make`: 2, raw image removed), reported at the `ASSERT`'s own line - `src/main.6502:60:1: error: Assertion failed` with `PANEL_BYTES = 2560` changed to 2561, or the message when there is one. The macro said `assertion failed` at its `ERROR` line in `beeb.h`, with `Note: Expanded from here` at the call |

`build.ps1` was not run (no PowerShell here), so `make` against `build.ps1` is not re-measured.

### The previous pin, 0.4.0 (2026-09-23)

`template\bin\baron.exe` was the **0.4.0 release binary**, downloaded from the releases page on
2026-09-23 (`sha256 2c1183bb c293370e 586dcd10 bb8a6ec4 8f75c603 ba0e2fe3 0a5fe009 98a15a7c`).
It replaced a `main@7213c8b` build made here from source on 2026-09-14; everything that build
had is in 0.4.0, tagged.

**A version string identifies a build again - from this release forward.** The 0.3.0 era did not:
`main@7213c8b` and the 0.3.0 release binary both reported `baron 0.3.0.0` while differing in
`--symbols`, `--pad`, the `INCLUDE` fix and the relaxed symbol naming. 0.4.0 reports
`baron 0.4.0.0`, so `--version` now separates it from everything before it. What it still cannot
do is tell the two *0.3.0s* apart, and one of those is the `..\..\Bin\` copy every other
project on this machine uses: for that one, `baron --help | grep symbols` is the test.

**Upgrading changed no bytes.** Measured here on 2026-09-23, the same sources under
`main@7213c8b` and under 0.4.0:

| | Result |
|---|---|
| The template, DEV and MASTER, `game.ssd`, `game-master.ssd` and both raw images | **byte-identical**, all four |
| `build/game.symbols.json` and `build/game.lst` | **byte-identical** - the dump and the listing did not move either |
| `lib/test/test_lib.6502`, `-D RELEASE=0` and `=1` | `TEST`, `BOOT` and `INFO` **byte-identical** on both |
| `examples/vscroll` | image and symbol dump **byte-identical** |
| `make` against `build.ps1`, `SOURCE_DATE_EPOCH` pinned to the last commit | the same `sha256 adb8baba...`, which is the pre-upgrade image's |
| The whole template at `--warn 2` | **silent** - no warning at either level, so the new audits cost nothing to turn on |

So this is a drop-in. The one thing to know before upgrading a port: **the unchecked-indexed-access
warning is now on by default** (it used to be opt-in), so a port that indexes a `ZA_AUTO` variable
will start seeing `warning: Unchecked indexed access into ZA_AUTO variable` where 0.3.0 said
nothing. It is a warning, never the exit code - see `ZA_INDEXEDBY` below for how to answer it.

### What the kit changed for 0.4.0

**`--warn 2` on every build** - `template/build.ps1`, `template/Makefile` and
`examples/vscroll/build.ps1`. Level 2 adds the opt-in audits to the ordinary warnings, and the one
that matters is a store into the `ZA_POOL` at a literal address: the stray pointer the allocator
otherwise cannot see, which is [#2](https://github.com/waitingforvsync/baron/issues/2) and the
one failure the allocator exists to prevent. The template is silent at level 2 and a port should
keep it that way. Warnings go to **stderr**, never change the exit code, and - unlike beebasm's
progress chatter - do not trip PowerShell's `$ErrorActionPreference = 'Stop'` (checked here on
PowerShell 7.6.6, warnings emitted, script survived, exit 0).

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

Four things the kit asked for. They landed before any release carried them, so they were built
from source here (`cmake -B build -G "Visual Studio 18 2026" -A x64`, submodule `richc`
initialised first; a second build with `-DBARON_TESTS=ON` runs Baron's own suite, 420 tests,
420 ok) - and they are all in the 0.4.0 binary now installed, tagged.

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

## What landed in 0.4.0 (2026-09-23)

Two more of the issues this kit raised are closed, and the annotations that answer them. The
whole release, against `7213c8b`, changed none of this kit's bytes (the table at the top).

| Asked | Fixed | What it does |
|---|---|---|
| [#2](https://github.com/waitingforvsync/baron/issues/2) - nothing warned when a store aimed a literal address into the `ZA_POOL`, which is the one failure the allocator exists to prevent | `caa954c` | Two answers at once. `--warn 2` turns on the audit that was asked for - `warning: Store into the ZA_POOL at a fixed address: '&00'` - and **`ZA_WIPE`** is the way to say a sweep was deliberate. The kit now passes `--warn 2` on every build |
| [#7](https://github.com/waitingforvsync/baron/issues/7) - a string carrying a NUL byte cut the `-v` listing short | in 0.4.0 | The listing runs to the end; an unprintable byte renders as `.` in listings and diagnostics, and the assembled bytes are untouched. Not something the kit hit, but it reads listings mechanically (`listing.py`), and a truncated one is a silently short opcode stream |

Still open, and both worth knowing:

- **[#3](https://github.com/waitingforvsync/baron/issues/3) - no response file.** This is why the
  build time is a generated `build/build_time.6502` rather than a `-D`. Rich's answer: the defect
  is **Windows PowerShell 5.1's** argument encoder, fixed in PowerShell 7.3+. Re-measured here on
  2026-09-23 under PowerShell 7.6.6, and he is right - the form that came out as loose words in
  5.1 now delivers the quoted string intact:

  ```powershell
  $t = '07 Sep 2026 15:47:31'
  & $baron -D "BUILD_TIME=`"$t`"" p.6502      # PS 7: prints 07 Sep 2026 15:47:31
  ```

  **The kit keeps the generated file anyway**: it is what makes a rebuild byte-identical, it is
  the same code path under `make` and under `build.ps1`, and it still works where a port is built
  from PowerShell 5.1. Under 5.1, his workaround is an environment variable and the stop-parsing
  token (`--%`), or cmd.exe.
- **[#8](https://github.com/waitingforvsync/baron/issues/8) - character encoding and string
  escapes.** Source files and strings are byte sequences, and `""` is the only
  escape. A port that defines its own glyphs above `&7F` and writes them inside string literals
  runs into this; the suggestion in the thread is `"hello" + CHR(&9A) + "world"`. Nothing in the
  kit hits it - the template's text is ASCII - but a port with a custom character set will.

Also in the release, unasked for and worth a line each:

- **A `ZA_AUTO` read only through `var,Y` was invisible to the allocator** - the access widens to
  absolute, which has no zero-page encoding, and the analysis missed it. A table read that way
  could be classified unused, or have its bytes reused while still live. A silent wrong answer,
  now fixed: any port that indexes zero page with `Y` wants 0.4.0 rather than any 0.3.0.
- `-vv` dumps every emitted byte rather than the first eight, and whole list values.
- `-log<n> <file>` redirects `PRINT` channel *n* (`PRINT #1, ...`), not diagnostics: errors and
  warnings stay on stderr whatever `-log` says. Measured, because the name suggests otherwise.
- Numbers up to 32 bits print exactly in listings and `PRINT` (`&FFFF1900` used to come out as
  `4.29484e+09`).
- The reserved-name relaxation of `7213c8b` is now the documented rule and reaches further: `FOR`
  variables, macro and `FUNCTION` parameters, `ZA_AUTO` names and `-D` defines may all be spelled
  like a keyword. Re-measured under 0.4.0: `FOR next = 0..2` runs, `-D clr=5` defines, `@next = 12`
  assigns, bare `next = 12` is still `error: NEXT without a FOR`, and only `TRUE`, `FALSE` and `PI`
  are refused outright (`error: Cannot reassign a constant`).

## What it costs, and what we did about it

| BeebASM | Here |
|---|---|
| `ORG` / `SAVE` / `GUARD` / `CLEAR` | `SECTION name, org=, guard=, filename=, exec=` ... `ENDSECTION`. The filename **is** the request to save. Two sections may share an address, so `PANEL`'s `CLEAR` is gone |
| `ASSERT cond` | The same, Baron's own statement since 0.4.1, with an optional message (`ASSERT cond, "text", value`). Until then it was a two-line `MACRO ASSERT` in `beeb.h.6502`, which 0.4.1 refuses as `Reserved macro name` - see the pin above |
| `TIME$` | Gone. `tools/build_stamp.py` (run by the `Makefile` and `build.ps1`) writes `build/build_time.6502` - one line, `BUILD_TIME = "..."` - which `main.6502` includes. Not a `-D`: **Windows PowerShell 5.1 cannot hand a quoted string containing spaces to a native exe** (three forms tried, all mangled; PowerShell 7.3+ can, re-measured on 7.6.6 - [#3](https://github.com/waitingforvsync/baron/issues/3) above). The file stays regardless: it is what makes the rebuild byte-identical. The time is the source's (`SOURCE_DATE_EPOCH`, else the last commit), so a rebuild is byte-identical on any machine |
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

### The two markers 0.4.0 added, and when a port needs them

Both answer the same objection - "the allocator cannot see what my index register holds, or what
my wipe loop just did" - by letting the source say it, so that Baron can check it rather than
trust it. The template needs neither (it has no wipe loop and indexes nothing in the pool), which
is why it is silent at `--warn 2`. A port transcribed from an original will very likely need both.

**`ZA_WIPE`** - the answer to a conventional boot-time zero-page sweep, which is exactly the
pattern [#2](https://github.com/waitingforvsync/baron/issues/2) was about. Written *directly
after* the loop, it promises that every pool byte has just been freshly written:

```
    LDX #0 : TXA
.wipe
    STA &00,X : INX : CPX #&90 : BCC wipe
    ZA_WIPE                     ; the loop above swept the pool - and says so
```

That does three things: it makes the wipe a legitimate first write (so a `ZA_ENTRY` routine may
rely on a variable being zero), it ends every earlier value's live range, and it quiets the
`--warn 2` fixed-address warning for the sweep's own stores - and only those; a stray pool store
elsewhere still warns. It is **trusted**, and it is the bigger promise of the two: nothing
survives it, so a value you wanted to keep across the wipe is already gone. Put it after the loop,
never before - above it, it would vouch for bytes not yet written.

The kit's template deleted its wipe loop instead, which is the better answer where it is
available (six bytes of code, and every variable has a provable first write). `ZA_WIPE` is for
the port where the wipe is load-bearing or not worth unpicking yet.

**`ZA_INDEXEDBY`** - the answer to `LDA table,X`. That access is now warned about **at the default
warning level**, where 0.3.0 said nothing, so this is the one a port will meet first. Declare what
the register can hold and the access is checked instead of trusted:

```
ZA_AUTO 8, frames
    LDA frames,X : ZA_INDEXEDBY 0..7    ; checked against the variable's 8 bytes
```

The operand flattens like `EQUB` data - a range, a list, a comma run, a symbol bound to one - and
Baron refuses a declaration whose largest index reaches past the end of the variable, `(var,X)`
included (the pair's second byte must fit too). **It goes after the access, not before**:
measured here, `ZA_INDEXEDBY 0..1` written on the line above gets
`error: ZA_INDEXEDBY must follow an indexed ZA_AUTO access`.

One thing it does not do is discard: `STA arr,X : ZA_INDEXEDBY 0..7` bounds where the store can
land but still writes one unknowable byte, so an array rebuilt through indexed stores wants
`ZA_DISCARD` as well. The two answer different questions - where can an access land, and when is
a value dead.

Still unused, and worth a look when a real port needs them: `ZA_DISCARD` for arrays rebuilt
through `STA arr,X`, `ZA_CANCALL`/`ZA_CANJUMP` for dispatch tables, `BITABS`/`BITZP` for the
skip trick. 0.4.0 also made `ZA_DISCARD` and `ZA_WIPE` placement path-accurate: **a marker
belongs to the path it is written on, with a label as the pivot** - above the label it stays on
the arm that falls in, below it it covers every path arriving there. Write whichever you mean.


Also unused so far: lists and broadcasting (a sine table in one `EQUB`), user `FUNCTION`s,
`BASIC` ... `ENDBASIC` for a tokenised BASIC loader, and macro overloading.

## Going back to BeebASM

A port that wants BeebASM reverses the table above. The whole delta measured on `lib/` was six
lines - the `ASSERT` shim in `beeb.h`, the `TIME$` line in `boot_stamp` - plus the `SECTION`
wrappers in whatever includes them, and the file extensions. Everything else, macros and all,
assembles unchanged under both. The BeebASM `lib/` and template are in this repository's
history: commit `5355d03`, the commit before the Baron port (it was the tip of a
`zx02-depacker` branch, deleted 2026-09-11 once it was an ancestor of `master`).
