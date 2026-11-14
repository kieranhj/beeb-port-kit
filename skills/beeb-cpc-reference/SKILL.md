---
name: beeb-cpc-reference
description: Bring up the specification for an Amstrad CPC (or other Z80) original with no source - the DSK and AMSDOS file out, the original's own depacker run on a Z80 core to a 64K image, coverage-guided disassembly, the field-locked or free-running question, a picture machine at CPC timing and a logical reference machine that writes per-field 64K records, then Python models of each effect scored N of N against them. Use when starting a port of a CPC demo or game, when a model and the reference disagree, or when deciding how the port should be paced against the original.
---

# A CPC original as records

The pass mark is **N of N records identical** (all 64K but the stack, or the player's whole state
every tick) - never a percentage. The long form is `docs/cpc-demo-porting.md` sections 1-5; the
tools are `template/tools/cpc/` (README there), forked into the project and adapted to its
addresses. Isometrikum (field-locked) and Square Roots (free-running) are the two worked examples.

**Tools:** kosarev's `z80` (`pip install z80`), SkoolKit 10.1, numpy; run **without `python -I`**
(it hides user site-packages, where `z80` lives).
**Input:** the original's disc image or archive, kept out of git.
**Output:** `extracted/mem.bin` (the 64K at the entry), `work/ref/` (records), a model per effect
that scores N of N, and the reference's decision written down.

## Steps

1. **Get the file out.** `cpc/dsk_extract.py DSK OUT` (standard or EXTENDED DSK; the AMSDOS header
   kept as `.hdr`: load, exec, length). Unpack with the original's **own** stub:
   `cpc/depack.py FILE OUT LOAD EXEC ENTRY` runs it on `z80` and saves the 64K when the PC reaches
   the entry. Find the entry by running the stub and watching where it jumps; record the unpacked
   range. Make the build re-extract every time (`tools/extract_original.py`) and assert the facts
   the port will rely on.

2. **Find the code by coverage, never a linear listing.** `cpc/cpccov_raw.py MEM work/cov N`, then
   `cpc/covdis.py MEM work/cov/cov.txt START END`. Players dispatch into the middle of
   instructions; kosarev stops between a DD/FD prefix and its opcode (covdis drops it). Name, in
   order: the interrupt chain (handlers rewriting `&0039` for the next), the wait loop, every
   `OUT &7Fxx` (pens or RAM banks?), every `LD A,R` / `LD A,I`, every AY register written.

3. **Look at it.** `cpc/cpcrun.py MEM work/run FIELDS EVERY`, contact sheets, the AY log. Measure the
   field length in lines (Square Roots' is 304, not 312) and how much of a field the main loop
   uses. Treat what the pictures suggest as hypotheses for step 2 to confirm (a "palette fade"
   was tile sets).

4. **Decide the machine's timing, and write the decision down.** Is the main loop **field-locked**
   (one pass per field, waits each time) or **free-running** (draws as fast as it can)? Field-locked:
   raw T is harmless; the reference is `cpcref_fieldlocked.py`'s shape (Z80 4x fast, VSYNC read as
   an edge, interrupts queued to the wait loop, a fixed 312-line clock). Free-running: speed is the
   specification; run at CPC timing (`cpctime.py`, PROVISIONAL until a real CPC or WinAPE/ACE
   confirms it), cut the main loop into **units** at commuting boundaries, hold the work
   interrupt out of the non-commuting regions, and record at the first unit after each work
   (`cpcref_units.py`). Run once with the holding back off (`NODEFER=1`) and report what it changes.

5. **Check the reference itself.** It reaches the demo's end (a free-running original at the wrong
   speed overwrites its own vector); no interrupt is lost (a late acknowledge must not clear the
   Gate Array's counter); no record includes the next field's work (nothing taken at the
   field-done call itself). Every record of a 64K XOR-zlib `passes.bin` decodes.

6. **Model each effect over the original's own 64K image**, so self-modified operands stay at their
   Z80 addresses (`fx_music.py`, `fx_world.py`). Score every record; a mismatch names its first
   address and record. An operand is at instruction + 1. Compare at a canonical point (a unit, the
   field-done call), not where the main loop is half way through something.

7. **Where the capture has an artefact the port will not copy** (a long `LDIR` holding interrupts
   back then a burst of ticks; work interleaved with a boot clear), build an **ideal reference**:
   the proven model run on the idealised schedule (Isometrikum's `ideal_ref.py`, Square Roots'
   `boot_model.py`), agreeing with the capture up to the artefact. A re-dithered colour set gets
   its own reference the same way, self-checked to give 0 differences on the original's data.

8. **Hand the 6502 the same records.** Each 6502 routine is checked against the model's state at
   the same hook, on both models and every colour set, by a harness that exits 0/1/2
   (`beeb-oracle-harness`). Write the counts into the layer doc: "7,595 of 7,595".

## Traps

- `STA` sets no flags; the Z80's arithmetic did. Name operands `cpc_XXXX` at their own address.
- `LD A,R` is timing: replace it with a seeded LFSR mirrored in the reference, compare by density.
- A race between the music and the main loop is settled once, in the reference, and copied.
- A record and a pass may be one apart; the harness says which.
- The CPC timing table is from memory, not measured: anything that depends on it is PROVISIONAL.
