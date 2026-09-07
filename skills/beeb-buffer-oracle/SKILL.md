---
name: beeb-buffer-oracle
description: Diff the BBC Micro port's play buffer byte for byte against an independent redraw of what it should contain, at the awkward scroll positions and both bank parities, using jsbeeb MCP breakpoints and memory dumps. Use when a scroll, tile writer or sprite change needs proving, when a commit wants its "0 of N" figure, or when a screenshot looks fine and that is not good enough.
---

# The buffer oracle

The strongest check either port has. An **oracle** is an independent rendering of what the play
buffer should contain; the check is a byte-for-byte diff against what the game actually drew.
Paradroid's is `RedrawAll` on a debug key and nearly every commit from Layer 3 on ends
"0 of 10,240". Edge Grinder never built its redraw oracle and its layer docs say so from Layer 3
to Layer 5. **Build yours in Layer 3, before the scroll is trusted.**

**Pass mark:** 0 bytes different
**Settle time:** ~1,500,000 cycles before freezing, so no scroll is in flight
**NOP:** `&EA` = 234; a `JSR` site is three of them

## Project parameters

Look these up before starting; record them in the project's `CLAUDE.md` once known.

| Parameter | Where to find it |
|---|---|
| The draw call sites - **every** one (`JSR spr_draw_all`, both `JSR SprDrawTr`, the scroll's column copy) | the main loop in `src/main.asm`; addresses from `build/<NAME>.lst` |
| The frame boundary symbol to break on (the redraw `JSR`, or the top of the main loop) | the listing |
| Buffer base and size (Paradroid `&5800`, 10,240; Edge `&4000`, 16,384) | `CLAUDE.md` "Memory" |
| Whether there are two banks (Master: main and shadow; ACCCON `&FE34` bit 2 selects which the CPU sees) | `CLAUDE.md` "Target" |
| The renderer: the debug redraw key, or an off-machine model (`tools/render_*.py` from the map and the scroll position) | `CLAUDE.md`, `tools/` |
| The positions to vary (odd/even scroll unit, non-zero scanline offset, diagonal, bank parity) | the layer doc |

## Steps

1. **Drive the view to an awkward position and let it settle.** Every scrolling bug so far
   hid in an odd `mapHX`, a non-zero scanline offset or a diagonal. Poke the position rather
   than hold keys, then `run_for_cycles session_id, cycles: 1500000`.

2. **Freeze with the player at rest.** Restores replay every pass while draws are off, so a
   freeze taken mid-deceleration stamps stale tiles into a scrolled buffer on every later pass.

3. **Disable every writer.** Poke *all* the draw sites to NOPs. NOPing only the first was enough
   in Paradroid until the tranche split; after it the second path kept drawing and the diff
   showed a player-shaped block of false corruption. Let a pass or two run so the restores take
   every sprite off the buffer. If the scene cannot be made quiet (a door animating, an enemy
   spawning), NOP the update call too.

   ```
   write_memory  session_id, address: <JSR site 1>, bytes: [234, 234, 234]
   write_memory  session_id, address: <JSR site 2>, bytes: [234, 234, 234]
   run_frames    session_id, count: 4
   ```

4. **Take both dumps inside ONE pass.** Break on the redraw `JSR` itself, dump (A); clear that
   breakpoint, break on the instruction after it, run, dump (B). The redraw can take over
   500,000 cycles, so if the run did not reach the second breakpoint run again rather than
   concluding it was missed. The trap in the obvious method - dump, press the key, run 800,000
   cycles, dump - is twenty passes, and anything that animates in between is a diff with nothing
   to do with the change under test: it reported 35 and 196 wrong bytes on two correct builds.

   ```
   key_down          session_id, key: "CTRL"      key_down session_id, key: "R"
   set_breakpoint    session_id, address: <JSR redraw>
   run_for_cycles    session_id, cycles: 200000
   save_memory       session_id, address: <base>, length: <size>, path: "<scratchpad>/a.bin"
   clear_breakpoint  session_id, id: <that id>
   set_breakpoint    session_id, address: <JSR redraw + 3>
   run_for_cycles    session_id, cycles: 600000
   save_memory       session_id, address: <base>, length: <size>, path: "<scratchpad>/b.bin"
   key_up            session_id, key: "R"         key_up session_id, key: "CTRL"
   ```

   With an **off-machine** oracle, B is the renderer's output for the scroll position read from
   the game's own variables at the moment of dump A.

5. **Diff, and report "N of <size>".** `cmp -l a.bin b.bin | wc -l`, or three lines of Python
   printing offsets. Anything sprite-shaped: resume draws, let the overlap heal, re-freeze
   somewhere quiet. Anything column-shaped is the scroll.

6. **The other bank, on a Master.** `save_memory` reads through the machine's own memory map, so
   flip ACCCON's X bit (`&FE34` bit 2) from the guest - poke it, or break where the game has the
   other bank up - before the dump and put it back after. Then repeat steps 1-5 at the other
   parity of everything: odd and even scroll unit, the other scanline offset, the other bank.

7. **Record the figure in the commit body and the layer doc** with the positions tested. "0 of
   16,384, both banks, scroll phase odd and even" is the shape.
