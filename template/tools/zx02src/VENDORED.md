# zx02, vendored

Daniel Serpell's ZX02 compressor, from https://github.com/dmsc/zx02 at tag `v2`
(commit `b665e0aa1efaffd9679fbb6ab93ffcdfe8676223`), **unmodified**. MIT (`LICENSE`), over
Einar Saukas' BSD-3 ZX0 (`LICENSE.zx0`). `src/dzx02.c` is upstream's decompressor; the build
does not use it.

**Why it is here and not an external tool.** The disc's bytes depend on the compressor, and
`src/lib/zx02depack.6502` decodes exactly what this one emits. The build used to run whichever
compressor it found - `zx02.exe` if one was in `bin/` or the shared `BEEB/Bin/`, else the
Python port - and the two do not agree: over the kit's 29 small test files `tools/zx02.py`
matched on 28 and ended one byte shorter on Edge's `tiles.chr.bin` (measured 2026-09-11). Both
decode the same, but a build whose image depends on what happens to be installed cannot be
checked by hash from another machine. So the build now has one compressor, this one: `make`
builds it into `bin/zx02` and every rule that compresses depends on it; `build.ps1` builds it
with a C compiler if `bin\zx02.exe` is missing.

**Measured identical to the released binary.** Built with `cc -O` (MSYS2 gcc 15.2.0) and run
over 54 `.bin` files from the template, `lib/` and edge-beeb, it wrote the same stream byte for
byte as the v2 release's `zx02.exe` on every one (2026-09-11). It also builds warning-free
under `-std=c99 -pedantic -Wall`.

`tools/zx02.py` stays as the round-trip oracle: every stream is decompressed by it and compared
with the source before the disc is written. It is too slow to be the build's compressor anyway -
2 s on the template's 2.5K panel, 3 min 38 s on a 16K bank.

Upgrade by replacing `src/` from a later tag and re-running the comparison above; a stream
that changes changes the disc.
