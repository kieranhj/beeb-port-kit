# Shrinkler, vendored

Aske Simon Christensen's Shrinkler, from https://github.com/askeksa/Shrinkler at **commit
`17cff110fcded387fe90e632805258d9c8359e94`** (2022-02-22, "Upped default compression preset to
-3"), **unmodified**: `cruncher/` (the compressor), `decrunchers_bin/*.dat` (the Amiga decrunch
headers the compressor `#include`s; unused for raw data, needed to compile), `LICENSE.txt` and
`README.txt`. Upstream's Amiga decrunchers' sources, toolchain and Makefile are not vendored.

Licence: `LICENSE.txt` (permissive; source distribution must carry it, as here).

The crunch (decision 15, `docs/crunch.md`) uses it as `-d -b -p -9`: raw data, no parity
context (the variant unShrinkler's `unshrinkler_PARITY=0` decodes), no progress output, the
strongest preset. `tools/shrinkler.py` is the oracle: its decoder is upstream's
`RangeDecoder.h`, `LZDecoder.h` and `Decoder.h` transcribed, and every stream is decoded and
compared with its input before the build uses it.

Built by `build.ps1` (c++, g++, clang++, else `zig c++`) and `make` (`$(CXX)`) into
`bin/shrinkler`. Validated 2026-11-08 with `zig c++ -O2` (zig 0.17.0) on Windows: the
original's `&1D00-&36DC` 6,621 -> 3,620, and master's four files 34,311 -> 10,623, each stream
decoded by `tools/shrinkler.py` to its input.
