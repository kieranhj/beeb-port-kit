---
name: beeb-rom-model-probe
description: Turn a routine in an original's ROM into a Python model and score it frame by frame against a MAME capture until it is 0 wrong with every exclusion named - reading backwards from known data with watchpoints, transliterating with tables read from the ROM, checking the instrument's lag and phase, refusing unread paths, and making the probe the exporter's only decode and the port's oracle. Use when porting any behaviour of a game with no source (movement, spawning, firing, scoring, sound), when a probe has a small residual someone wants to call noise, or when a port and the original disagree.
---

# A ROM routine as a scored model

The pass mark is **0 wrong, with every excluded sample named and counted.** *A residual you cannot
explain is a defect you have not found yet* - three jumps in 32,971 samples were a real defect in
1942 (`BUGS.md` #8), and 3,333 frames rationalised away were another (#10). The long form is
`docs/arcade-porting.md` §5.

**Tools:** `beeb_port_kit.mame.probe.Score`, `romset.Banked`, `z80sub.disassemble` / `SubCPU`, `records`
**Input:** a capture (`beeb-arcade-capture`) that covers the routine's paths
**Output:** a probe script that exits 0 or 1, and a model the exporter and the port's oracle import

## Steps

1. **Start from data you understand, and read backwards.** Never cold. A write watchpoint on a
   known object's sprite slot names the sprite writer; a watch on the table it copies from names
   the creator; what the creator reads is the schedule (`template/tools/mame/debugscript.txt`;
   1942-beeb `brief-wave-disassembly.md` §4). Confirm each link against captured RAM.

2. **Transliterate the routine.** Tables are read from the ROM image (`romset.Banked(...).read`),
   never retyped. **Print every table and pointer you use** (`z80sub.disassemble`): 1942 read a
   dispatch table with one digit transposed and documented a bare `ret` as the behaviour (§18).
   Where the ROM reads a free-running counter or RNG, model it from the capture's own value of it.

3. **Make the model refuse what it does not follow.** A path you have not read raises
   `probe.Unread`; it never returns a default. 1942's `None` meant "leave the bank at 2" and was
   wrong on 8 of 32 stages (§28).

4. **Score it per rule and per type** with `Score.compare(rule, predicted, observed, key=frame)`.
   Never in aggregate: 113 of 119 objects were one type (§12). Add `cover(path)` for each branch
   and `require()` the ones the capture must exercise - a check that ran over nothing is not a pass,
   and `Score` fails a rule with zero samples.

5. **Before blaming the rule, check the instrument.**
   - Lag: sprite RAM copied from a shadow is one step late (0 of 83 -> 83 of 83, §16); a RAM-to-RAM
     read is not (six residuals, §18). Try both offsets on the first residual.
   - Frame boundary: a flag tested at the start of a frame and captured at its end misleads on its
     transition frames (§19).
   - Sub-CPU sampling: MAME samples mid-IRQ now and then. Use `observe(..., torn_ok=True)`: a torn
     sample must be followed by a match, or it is wrong.
   - The filter: does the selection of samples predetermine the answer (`BUGS.md` #46)? Is every
     live value read from THIS run (§28)?

6. **Exclude only by a named cause**, `Score.exclude("a freeze flag was set")`, derived from the
   game's own state where possible, never by a frame range or a widened threshold. Check every
   exclusion is true (e.g. "no shot in the capture comes from an object with this bit set").

7. **Run it to 0 wrong** - `sys.exit(score.finish())`. If the capture cannot reach a path, say so
   in the probe and go back to `beeb-arcade-capture` step 6 rather than marking it done.

8. **Make the probe the exporter's only decode.** The exporter imports the model; one copy of each
   decode means the scored thing and the shipped thing cannot drift (1942's `rom_map.py`).

9. **Close the loop on the port.** Record the port's per-frame state in the BBC emulator, replay
   the SAME model over it re-seeded each frame, and fail on any difference (1942's
   `verify_turner.mjs` -> `check_turner.py`). One model, both sides.

10. **Write the result where the next session reads it**: the routine's addresses, the rule, the
    score with its exclusions, and the capture it was scored on, in the project's arcade-facts file.
    A rule taken on the port's own counter instead of the original's (decision 23's shape) is a
    numbered decision, not a quiet substitution.
