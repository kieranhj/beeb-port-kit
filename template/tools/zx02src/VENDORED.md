# zx02, vendored

Daniel Serpell's ZX02 compressor, from https://github.com/dmsc/zx02 at tag `v2`
(commit `b665e0aa1efaffd9679fbb6ab93ffcdfe8676223`), with **one local patch** (below). MIT (`LICENSE`), over
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

## The one local patch (2026-09-23)

`src/compress.c`, one line: `*output_size = output_index;` before the return.

**What was wrong.** `compress()` sets `*output_size` from `optimal->bits`, which is an
ESTIMATE and therefore an allocation BOUND - but `zx02.c` then writes exactly
`*output_size` bytes to the file, while the writer only filled `output_index` of them.
Where the estimate over-predicts, the slack is uninitialised `malloc` memory and it goes
straight into the `.zx02`. On Windows it is commonly a readable piece of the process
environment block, so **the same input gives a different file in a different shell**: a
19,200-byte input came out with 125 of its 224 bytes following the environment, and the
tails were ASCII (`6f 63 61 6c` = "ocal", `4d 6f 64 75` = "Modu"). Over 31 real data
files from this kit and edge-beeb, **9 carried surplus bytes** (1 to 8 each). That breaks
`docs/build-portability.md` rule 16 outright, and it means a published disc image can
carry fragments of whoever's environment built it.

Found by **puzzle-beeble** (its `BUGS.md` #2, 2026-09-23); diagnosed to this line here the
same day by instrumenting `output_size` against `output_index`.

**Why patch rather than upgrade.** Upstream `main` fixes it the same way (`if (real_size
!= *output_size) ... *output_size = real_size;`), but there is **no tag after `v2`**, and
`main` also carries `f4427e7 "Use a better estimate of the compressed bit sizes"` and an
allocator rewrite - changes that would move the emitted stream, and a stream that changes
changes the disc. This patch changes **no emitted stream byte**: it only stops the garbage
tail. Verified over the same 31 files - the 22 that had no slack are byte-identical, and
the 9 that did are the same bytes with the surplus gone.

**It also settles an old question the other way.** This file used to say that `tools/zx02.py`
"ended one byte shorter" than the reference on Edge's `tiles.chr.bin`, and `dfs.py` called it
a trailing pad. Neither was right: the exe was writing one byte of uninitialised memory
(`0x65` in one run, `0x3D` in the next). With the patch the exe and `zx02.py` agree on that
file **byte for byte**, so the Python port was correct all along.

On the next upstream tag, drop this patch if it carries the fix, and re-run the comparison
below - the estimate change in `main` may move streams, which moves the disc.

**Measured identical to the released binary.** Built with `cc -O` (MSYS2 gcc 15.2.0) and run
over 54 `.bin` files from the template, `lib/` and edge-beeb, it wrote the same stream byte for
byte as the v2 release's `zx02.exe` on every one (2026-09-11) - which, given the above, means
only that the two agreed on the SURPLUS as well, the same build reading the same heap. The
check that matters now is the one in `make_disc.py`: no bytes after the END marker. It also builds warning-free
under `-std=c99 -pedantic -Wall`.

`tools/zx02.py` stays as the round-trip oracle: every stream is decompressed by it and compared
with the source before the disc is written. It is too slow to be the build's compressor anyway -
2 s on the template's 2.5K panel, 3 min 38 s on a 16K bank.

Upgrade by replacing `src/` from a later tag and re-running the comparison above; a stream
that changes changes the disc.
