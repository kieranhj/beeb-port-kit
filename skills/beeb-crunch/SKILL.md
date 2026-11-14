---
name: beeb-crunch
description: Shrink a working BBC Micro port to the smallest packed executable that still plays identically - a measuring stick first (Shrinkler vendored with a decoder oracle, a per-byte packed cost map from the symbols, an identical-image gate with the zero page pinned), then rounds that change how the bytes arrive, generate tables and code at boot and ship them as zeros, delete what is dead or harness-only, and re-lay data for the packer, each change measured packed and alone. Use when asked how small a build can get, to crunch, pack or shrink an executable, or before a size-limited release (a 4K demo's port, a compo).
---

# The crunch

The measure is **the packed length of the file people load**, and the gate is **the same
behaviour**: first an identical memory image, then the whole suite with its timing floors. The
long form is `docs/cpc-demo-porting.md` section 11 (Isometrikum: 10,623 -> 7,582 bytes in five
rounds). Getting the size down is a decision the owner takes (it trades load time, and later may
cut code the original has): number it, and number each later step that reverses an earlier rule.

**Tools:** `template/tools/shrinkler.py` + `shrinklersrc/` (build with any C++ compiler or
`zig c++ -O2 -w -Ishrinklersrc/decrunchers_bin`), `lib/unshrinkler.6502`, `size_report.py`,
`verify_image.mjs`, `grind_bytes.py`; the project's `make_disc.py`.
**Output:** a commit per round with the executables' lengths in the message, and a log table in
the project's crunch doc.

## Round 0: the measuring stick

1. **Choose the packer by what counts.** Shrinkler packs smallest and decodes at ~4,000 cycles a
   byte (34 s for Isometrikum's 7.6K); ZX02 at 54. Size alone: Shrinkler, `-d -b -p -9`.
2. **Trust no compressor without its oracle.** Every stream goes through `shrinkler.py`'s
   transcribed decoder and is compared with its input before the disc is written.
3. **The cost map**: `size_report.py` charges each bit to the byte it produced and totals by
   section, file and label. Rank the work by **packed** cost, never raw size.
4. **The gate**: golden memory images at two hooks (after boot, at the main loop), both models,
   every set (`verify_image.mjs`). **Pin the zero page** to the golden build's allocation while the
   gate is identity, or the allocator repacks when a variable goes and every operand moves.
5. **A no-op round**: rebuild unchanged, gate passes, length identical.

## The rounds, in the order that paid

1. **How the bytes arrive** (gate: identical image): one executable, a stub plus a stream per load
   address; a chooser that picks the set (stock, NuLA) on the disc rather than in the executable.
2. **Generate at boot** (gate: identical image): every table, unrolled block and cache the build
   computes becomes 6502 that computes it (often the original's own generator), and the range ships
   as **zeros** (`genr_NAME`..`genr_NAME_end`): the assembler still lays out every label, so the
   harnesses' symbols resolve, and zeros pack to nearly nothing. Isometrikum: -1,600 then -700.
3. **Delete** (gate: the suite): never-called routines, write-only variables, the zeroing of state
   that already ships as zero, counters and record fields only a harness reads (move them into the
   harness: it can snapshot at a hook), paths the coverage and the whole-run checks prove are never
   taken (a decision).
4. **Re-lay data for the packer's context**: tables by column instead of by record, pointers made
   absolute where that makes repeated data identical. Measure: some re-layouts lose.
5. **The byte grind**, once: `beeb-micro-grind` in bytes mode. Expect a fifth of candidates to grow
   the packed stream.

## The rules

- **Measure each change alone, packed**, before building anything on it. A round planned on raw
  bytes at 900-1,200 delivered 502.
- **Deletions pay; merges do not.** Repeated code packs nearly free and a loop's control does not:
  three merges measured +20, +19 and -3/+10. Do not spend a day on a merge without a packed
  prototype.
- **Things measured as no help** (record them, so they are not retried): the packer's stronger
  settings; merging streams (the copy code eats the gain); splitting a bytecode's opcodes from its
  arguments; formulas for tables that are nearly regular.
- **The timing floor stays.** A size change may not take a pass over its field: the gate checks the
  least slack against a floor (Isometrikum: 1,000 cycles) and every raster margin.
- **Commit each round** with both executables' lengths; the log row names what paid and what was
  tried and lost, with its number.
