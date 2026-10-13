# zx02, vendored

Daniel Serpell's ZX02 compressor, from https://github.com/dmsc/zx02 at **tag `v3`,
commit `7ffa0e782c9f5718a8d77ba021c6babc78c7fe19`** (released 2026-09-25), **unmodified**.
MIT (`LICENSE`, byte-identical to upstream's), over Einar Saukas' BSD-3 ZX0 (`LICENSE.zx0`).
`src/dzx02.c` is upstream's decompressor; the build does not use it. Upstream's `6502/`
decoders, `tests/` and build files are not vendored, so `README.md`'s links into `6502/` do
not resolve here.

**v3 is the release [#11](https://github.com/dmsc/zx02/issues/11) asked for**: the author
tagged it on 2026-09-25 "with all the fixes" and closed the issue. It is `main` as the kit
had it (`af53aeb`, 2025-11-23) plus one commit, `7ffa0e7` "Cleanup malloc memory", which
`memset`s the output buffer - a second guard on the uninitialised write below, which
`f4427e7` had already stopped. The two bugs v2 (2022-07-22) has, both fixed in v3:

- it wrote the slack between its size ESTIMATE and what it emitted, i.e. uninitialised
  `malloc` memory - on Windows, pieces of the environment block - so the same input gave a
  different file in a different shell (fixed by `f4427e7`, guarded by `7ffa0e7`; the kit's
  report, [#11](https://github.com/dmsc/zx02/issues/11));
- its optimiser used `1024` bits as the cost of an invalid Elias code, which stops being
  prohibitive on a long input, so it could emit **a stream that is not the data**: 19,200
  bytes of a repeated pattern compressed to 99 bytes that decoded, without error, to 4,096
  WRONG bytes (upstream [#8](https://github.com/dmsc/zx02/issues/8), fixed by `5d2f2e3`).

The kit briefly carried both as local patches, then took `main` whole, then `v3`; the tree
is plain upstream and diffs cleanly against the tag. (The `README.md` vendored with `af53aeb`
was an older one than that commit's - documentation only, every source file matched. Taking
`v3` whole replaced it.)

**Validated here before it was installed, 2026-10-13** - `v3` built with
`gcc -O` (MSYS2 gcc 15.2.0) against the `af53aeb` build it replaces and against the official
`zx02-progs-v3-win64.zip` `zx02.exe` (`sha256 50732fa0...`), over 48 real data files from
this kit and edge-beeb plus a 19,200-byte repetitive input:

| Check | Result |
|---|---|
| Stream bytes, 49 inputs, `v3` against `af53aeb` | **all 49 identical** |
| The same, `v3` against the official v3 exe | **all 49 identical** - the release exe is clean, unlike v2's |
| Round-trip through `tools/zx02.py` | 49 of 49 back to the input, byte for byte |
| Bytes after the END marker | **none**, on any of the 49 |
| Same input, 4 environments (bare, short var, 512-byte var, `SYSTEMROOT` and `PATH` only) | identical every time, ours and the release's |
| The repetitive input | 237 bytes, round-trips, and **equals `zx02.py`'s own output** |
| `game.ssd` DEV and RELEASE, `game-master.ssd`, `vscroll.ssd`, at a pinned `SOURCE_DATE_EPOCH` | **byte-identical** to the `af53aeb` build's, all four (`0c523a1f...` DEV, `885be4b6...` MASTER) |
| Booted in jsbeeb 2.3.2, both models | `verify_dynamic.mjs` 100 / 50 / 0 / 200 on each |
| `py/` test suite | 97 OK, 2 skipped |
| `gcc -O -std=c99 -pedantic -Wall` | warning-free |

**The previous install, `af53aeb`, validated 2026-09-23** - against the v2-era build, over
31 real data files from this kit and edge-beeb plus the repetitive case:

| Check | Result |
|---|---|
| Stream bytes, 32 inputs | **all 32 identical** - the estimate change moves nothing we compress |
| Round-trip through `tools/zx02.py` | 32 of 32 back to the input, byte for byte |
| Bytes after the END marker | **none**, on any of the 32 |
| Same input, 4 environments (bare, short var, 512-byte var, `env -i`) | identical every time |
| The repetitive case v2 got wrong | 310 bytes, round-trips, and **equals `zx02.py`'s own output** |
| `game.ssd`, `make` at a pinned `SOURCE_DATE_EPOCH` | `sha256 adb8baba...` - **unchanged** |
| `build.ps1` DEV / MASTER / RELEASE, `make`, vscroll | all build |
| Booted in jsbeeb (`B-DFS1.2`) | panel and strip on screen, and **`&4A00` reads back byte-identical to `src/data/panel.bin`** - the 6502 depacker decodes `main`'s stream |
| `py/` test suite | 78 pass |
| `gcc -O -std=c99 -pedantic -Wall` | warning-free |

In both tables the boot is the row that matters: `lib/zx02depack.6502` is the kit's own
transcription of the format, and the boot is what proves the two still agree. (On 2026-10-13
the streams and discs were byte-identical to the build that had already passed the `&4A00`
read-back, so `verify_dynamic.mjs`'s boot was enough.)

**Upgrade** by replacing `src/` from a later commit or tag and re-running the table at
the top. A stream that changes changes the disc.

**Why it is here and not an external tool.** The disc's bytes depend on the compressor, and
`src/lib/zx02depack.6502` decodes exactly what this one emits. The build used to run whichever
compressor it found - `zx02.exe` if one was in `bin/` or the shared `BEEB/Bin/`, else the
Python port - and the two do not agree: over the kit's 29 small test files `tools/zx02.py`
matched on 28 and ended one byte shorter on Edge's `tiles.chr.bin` (measured 2026-09-11). Both
decode the same, but a build whose image depends on what happens to be installed cannot be
checked by hash from another machine. So the build now has one compressor, this one: `make`
builds it into `bin/zx02` and every rule that compresses depends on it; `build.ps1` builds it
with a C compiler if `bin\zx02.exe` is missing.

## How the two bugs were found (2026-09-23)

Kept because the evidence is not obvious from the upstream commits, and because the second
one corrects something this file used to assert.

**The uninitialised write.** `compress.c` sets `*output_size` from `optimal->bits` - an
estimate, so an allocation bound - and `zx02.c` then writes exactly that many bytes, while
the writer only filled `output_index`. Found by instrumenting the two counters: a
19,200-byte input predicted **224** and emitted **99**, so 125 bytes were heap. They were
plainly the environment block - tails read `6f 63 61 6c` ("ocal"), `4d 6f 64 75` ("Modu"),
`43 3a 5c 55` ("C:\U") - and one extra short environment variable was enough to move them.
Over 31 real files, **9 carried surplus bytes**, 1 to 8 each.

Found first by **puzzle-beeble** (its `BUGS.md` #2), which saw its `make` and `build.ps1`
images differ and reported it as the last two bytes following the environment.

**The invalid-code sentinel.** `optimize.c` used `1024` bits as the cost of an out-of-range
Elias code - "never choose this". On a long input that stops being prohibitive, so v2 could
emit a stream that is **not the data**: the same 19,200-byte input gave 99 bytes which
decoded, without error, to 4,096 wrong bytes. Upstream [#8](https://github.com/dmsc/zx02/issues/8),
someone else's, 2025.

**And it settles an old claim in this file the other way.** This document used to say that
`tools/zx02.py` "ended one byte shorter" than the reference on Edge's `tiles.chr.bin`, and
`dfs.py` called it a trailing pad. Neither: the exe was writing one byte of uninitialised
memory - `0x65` in one run, `0x3D` in the next. A fixed compressor agrees with `zx02.py` on
that file **byte for byte**. The Python port was right all along, and the kit had been
recording the bug as a quirk of its own correct implementation.

`make_disc.py` now refuses any stream with bytes after its END marker, whatever compressor
produced it - so a port that points `$ZX02` at a released `zx02.exe` fails the build rather
than shipping the disc. Note that checking by re-running under a changed environment does
**not** work: tried first, and it passed a compressor known to be broken, because the leaked
bytes often repeat.

**The old "measured identical to the released binary" note (2026-09-11)** - 54 `.bin` files,
same stream byte for byte as the v2 release's `zx02.exe` - is superseded and, given the
above, meant only that the two builds agreed on the SURPLUS as well, the same code reading
the same heap. The checks that matter are the table at the top and the one in
`make_disc.py`: no bytes after the END marker. It also builds warning-free
under `-std=c99 -pedantic -Wall`.

`tools/zx02.py` stays as the round-trip oracle: every stream is decompressed by it and compared
with the source before the disc is written. It is too slow to be the build's compressor anyway -
2 s on the template's 2.5K panel, 3 min 38 s on a 16K bank.

Upgrade by replacing `src/` from a later tag and re-running the comparison above; a stream
that changes changes the disc.
