# Baron, and BeebASM as the legacy (2026-09-07)

The kit assembles with [Baron](https://github.com/waitingforvsync/baron), Rich Talbot-Watkins's
ground-up rewrite of BeebASM (MIT, active - the sections design changed on 2026-09-06). `lib/`
and `template/` are both Baron. BeebASM is the legacy: the two shipping ports are BeebASM
projects, and this file records exactly what differs so either direction is a short walk.

Pin the version. The builds find `baron` through `$BARON`, then `bin/`, then the PATH, never
through a path written into the build (`docs/build-portability.md`). On this machine 0.3.0 is
in `..\..\Bin\` beside `beebasm.exe`, named in the template's gitignored `local.ps1`.
Binaries are on the project's releases page. The language is
still moving, so a build that worked is worth keeping the exe for.

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

## What it costs, and what we did about it

| BeebASM | Here |
|---|---|
| `ORG` / `SAVE` / `GUARD` / `CLEAR` | `SECTION name, org=, guard=, filename=, exec=` ... `ENDSECTION`. The filename **is** the request to save. Two sections may share an address, so `PANEL`'s `CLEAR` is gone |
| `ASSERT cond` | A two-line `MACRO ASSERT` in `beeb.h.6502` (`IF NOT(c) : ERROR ... : ENDIF`), so all 16 assertions in `main.6502` read exactly as they did. Baron reports the `ERROR` and adds `Note: Expanded from here` at the call, so an assertion still names its own line |
| `TIME$` | Gone. `tools/build_stamp.py` (run by the `Makefile` and `build.ps1`) writes `build/build_time.6502` - one line, `BUILD_TIME = "..."` - which `main.6502` includes. Not a `-D`: **Windows PowerShell cannot hand a quoted string containing spaces to a native exe** (three forms tried, all mangled). The time is the source's (`SOURCE_DATE_EPOCH`, else the last commit), so a rebuild is byte-identical on any machine |
| `INCLUDE` resolves from the working directory | Baron resolves it **relative to the including file**: `src/main.6502` says `INCLUDE "lib/irq.6502"`, not `"src/lib/irq.6502"`. Watch for this when forking a file into a different directory - a wrong path surfaced once as a confusing parse error downstream rather than "could not read" |
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
