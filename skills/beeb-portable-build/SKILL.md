---
name: beeb-portable-build
description: Check that a BBC Micro port's build works on someone else's machine and produces the same disc there - a fresh copy built with make -j4, a no-op rebuild, one-file and flag changes, a failing tool that must leave no target behind, the Makefile and build.ps1 images compared byte for byte, and the SHA256 to publish. Use before asking anyone to test a build on another platform, after changing a Makefile or build script, or when a tester reports a failure or a hash you cannot match.
---

# Portable build check

The failures this finds are the ones a tester on another machine hits first: they cost a
round trip each in paradroid-beeb issue #3. The rules behind every step are in the kit's
`docs/build-portability.md`.

**Needs:** a POSIX make (GNU make; on Windows MSYS2's `/c/msys64/usr/bin/make.exe`), a C
compiler if the build compiles its compressor, the project's assembler
**Image and hash:** `build/<name>.ssd`; `make_disc.py` prints its `sha256` on every build
**Fixed time for comparisons:** `SOURCE_DATE_EPOCH=1757600000` in the environment

## Steps

1. **Read the Makefile's first line.** It must be `.POSIX:`. Without it GNU make does not run
   recipes under `sh -e` the way a BSD make does, and every check below can pass on this
   machine and fail on OpenBSD. Then grep the recipes for `; rc=$$?` - under `-e` it must be
   `|| rc=$$?`.

2. **Build a fresh copy with `-j4`.** A clone or a copy without `build/` and `bin/`: after a
   clone every file has much the same mtime, and that is what exposes a missing prerequisite
   (Paradroid's generator ran before its compressor existed).

   ```bash
   git clone <repo> /tmp/fresh && cd /tmp/fresh     # or: tar the tree without build/ bin/
   SOURCE_DATE_EPOCH=1757600000 make -j4
   ```

   On Windows, run it inside MSYS2 with the Windows PATH kept:
   `env MSYSTEM=UCRT64 MSYS2_PATH_TYPE=inherit CHERE_INVOKING=1 /c/msys64/usr/bin/bash.exe -lc 'make -j4 PYTHON=python BARON=...'`.
   Also `touch` a generator's input to force the order that fails.

3. **Run `make` again.** It must do nothing (`'build/<name>.ssd' is up to date`). If it
   reassembles, a stamp or config file is being rewritten on every run.

4. **Touch one source, then flip a flag and flip it back.** One source reassembles once.
   `make release` then `make` rebuilds each time, and the second debug build's hash matches
   the first. If it doesn't, a flag is reaching the output without reaching a file make can
   see.

5. **Make a tool fail.** `make BARON=false` (or the project's assembler variable) must exit
   non-zero and leave no raw image behind: `ls build/<name>-raw.ssd` finds nothing.

6. **Compare the two build scripts.** Build with the other script (`build.ps1`) using the same
   `SOURCE_DATE_EPOCH`, then:

   ```bash
   python tools/dfs.py compare build/<name>.ssd /tmp/fresh/build/<name>.ssd
   ```

   The pass is `identical images`. "Every file matches but the images differ" means a layout
   or catalogue difference. A difference in `!BOOT` alone means the two scripts stamp
   different times.

7. **Boot it.** `beeb-smoke-test` on the image from step 2, on every model the project builds.

8. **Publish the hash with the request.** Give the commit, the `SOURCE_DATE_EPOCH` (or say
   the stamp is the commit time) and the `sha256` line. The tester's first line back is then
   either a match or a real difference.

9. **Record what was not tested.** Which makes and platforms ran it (GNU make x.y, bmake,
   macOS) goes in the commit body. "Only tested with GNU make" is a finding, not a formality.
