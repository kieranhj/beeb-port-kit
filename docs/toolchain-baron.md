# Baron, and BeebASM as the legacy (2026-09-07)

The kit assembles with [Baron](https://github.com/waitingforvsync/baron), Rich Talbot-Watkins's
ground-up rewrite of BeebASM (MIT, active - the sections design changed on 2026-09-06). `lib/`
and `template/` are both Baron. BeebASM is the legacy: the two shipping ports are BeebASM
projects, and this file records exactly what differs so either direction is a short walk.

Pin the version. `baron.exe` 0.3.0 lives in `..\..\Bin\` beside `beebasm.exe` (a local
`template/bin\baron.exe` wins); binaries are on the project's releases page. The language is
still moving, so a build that worked is worth keeping the exe for.

## Why

Measured on this kit, 2026-09-07, not taken from the READMEs:

| | Result |
|---|---|
| All of `lib/` converted, then the template rebuilt on it | every byte of `Game` and `PANEL` unchanged again - the conversion is provably cosmetic |
| The template built with Baron vs BeebASM | `Game` (1,087 bytes DEV, 1,138 MASTER) and `PANEL` **byte-identical**; `!BOOT` differs only in the timestamp; final `GAME.SSD` differs in those bytes alone |
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
| `TIME$` | Gone. `build.ps1` / `tools/build.sh` write `build/build_time.6502` - one line, `BUILD_TIME = "..."` - which `main.6502` includes. Not a `-D`: **Windows PowerShell cannot hand a quoted string containing spaces to a native exe** (three forms tried, all mangled). Keeping the file gives a byte-identical rebuild |
| `INCLUDE` resolves from the working directory | Baron resolves it **relative to the including file**: `src/main.6502` says `INCLUDE "lib/irq.6502"`, not `"src/lib/irq.6502"`. Watch for this when forking a file into a different directory - a wrong path surfaced once as a confusing parse error downstream rather than "could not read" |
| `CPU 0` | NMOS is the default; `cmos = TRUE` on a section enables the 65C02 |
| `P%` | `*` (both spellings work) |
| `PRINT ~x` prints one value | `~` swallows the whole expression after it, so `~CODE_TOP - end` is `~(CODE_TOP - end)`. Parenthesise |
| `TRUE` is -1 | `TRUE` is 1 (`--beebasm-true` restores it). Nothing in the kit relied on it |
| `.asm` | `.6502`, which the [VS Code extension](https://marketplace.visualstudio.com/items?itemName=RichTalbot-Watkins.baron-vsc) keys on |

Not yet used here, and the reason to keep watching it: **the zero-page allocator** (`ZA_POOL`,
`ZA_AUTO`) packs named variables by liveness and proves the packing safe across `JSR`. Our
depacker headers claim the borrowed zero page is "not live while it runs" - an assertion nothing
checks. That is the natural next step, and it will change emitted addresses, so it needs its own
measurement rather than riding along with this one.

Also unused so far: lists and broadcasting (a sine table in one `EQUB`), user `FUNCTION`s,
`BASIC` ... `ENDBASIC` for a tokenised BASIC loader, and macro overloading.

## Going back to BeebASM

A port that wants BeebASM reverses the table above. The whole delta measured on `lib/` was six
lines - the `ASSERT` shim in `beeb.h`, the `TIME$` line in `boot_stamp` - plus the `SECTION`
wrappers in whatever includes them, and the file extensions. Everything else, macros and all,
assembles unchanged under both. The BeebASM `lib/` and template are in this repository's
history: branch `zx02-depacker`, the commit before the Baron port.
