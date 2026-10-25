---
name: beeb-ram-hunt
description: Find RAM for a BBC Micro port that has run out - regenerate the memory map from the build, ledger what is free against what the job wants per region, list every lever and cost each in bytes AND cycles before building any, then one commit per lever with the suite run after each, ending in a report with what was built, what was measured and not built, and what was rejected with the number that rejected it. Use when a feature does not fit, a region's free figure is near zero, the user asks to find or free RAM, or a brief's ledger goes negative.
---

# A RAM hunt

RAM is contended for the whole of a port, so the hunt recurs - 1942 ran six, 2026-09-14 to 10-10,
and every later feature opened with a ledger ("main RAM 3 bytes; anything new needs a lever
first"). A hunt done as a procedure finds more and breaks less: the 2026-10-06 one took main RAM
from 3 bytes to 179 and bank 4 from 20 to 1,501 with nothing on the screen changed and the suite
126 of 126. Done by grabbing the first pocket that looks free, it puts code on a table the port
already owns (1942 `BUGS.md` #24, #29).

**Memory map:** `docs/memory-map.md`, GENERATED from the listing (the project's `tools/memmap.py
--write` or equivalent); never hand-edit it
**Figures:** off THIS build - the listing's gauge lines and the symbol dump, never a doc
**Brief:** `docs/brief-<hunt>.md` from `docs/brief-TEMPLATE.md` if the hunt is more than one lever
**Branch:** its own, `ram-hunt-<date>`

## Steps

1. **Build, then regenerate the memory map**, and read it for sense: overlapping regions, a "free"
   figure that contradicts the rules file, entries for things that no longer exist. If the map is
   wrong, the GENERATOR is wrong - fix it first (1942's said HAZEL had 284 bytes spare when it had
   3).

2. **Write the ledger**: per region (main RAM, each sideways bank, shadow, ANDY, HAZEL, low RAM,
   zero page, the save-under store, the disc's sectors AND catalogue entries), what is free now
   and what the job wants. Say which figure binds. A region's ceiling for code read in play may be
   lower than the image's.

3. **List every lever before building any.** The kinds that paid in 1942, roughly in order of
   yield:
   - **data format** - a cheaper encoding of the biggest asset (1942's background cells as 32
     one-byte strip ids into per-column dictionaries instead of 64 bytes of pixels, decision 130);
   - **move data, not code** - a read-only table any bank can read, to low RAM;
   - **code into the bank it already runs with** - code that only runs with a sprite bank in can
     live in that bank;
   - **load it at a seam, or in the background** - what is dead for most of a level (1942's
     carrier deck, mid-stage) is an arena for something else;
   - **derive instead of store** - descriptor fields, all-constant arrays, generated counts;
   - **measured pockets** - MOS low RAM, HAZEL, ANDY, shown unwritten through a whole DRIVEN game
     with BREAK, by a write-hook harness. A map of what the MOS leaves is not a map of what is
     free: read what the port already put there;
   - **dataflow** - dead code, duplicate runs, register ABIs (`beeb-dataflow`); leads, not proofs.

4. **Cost each lever in bytes AND cycles, labelled MEASURED / COUNTED / PROJECTED.** A lever that
   frees bytes and costs the tick is a trade the owner takes, not one you take. A counted cycle
   figure is suspect (1942: -13 a blit counted, +7 measured): measure before and after as a pair,
   same day, same emulator version. Anything that changes the picture or the play is a decision.

5. **Build one lever per commit**, the measurement in the body (bytes freed per region, cycles a
   tick before and after), and the suite run after each one - not just the oracle nearest the
   change. **It is the whole-game run that catches a whole-game regression**: 1942's save store ran
   516 bytes into game state on stage 28 while the oracles nearest the change passed.

6. **Regenerate the memory map** and update the rules file's figures only where it says to read
   them off the build (the budget line in `CLAUDE.md`).

7. **Report** (`docs/report-ram-<date>.md` if the hunt ran unattended, else the brief's "what
   landed"): where it ended, as a before/after table per region; what was built and what proves it;
   **measured and not built** - the next RAM, in rough order of value; **rejected, with the number
   that rejected it**, which also go into `docs/decisions.md`'s rejected table; caveats and what
   is open. Merge only on the owner's word.
