# Decisions of record

The table every deviation from the original, and every choice the hardware forced, gets a row in.
Per-layer detail lives in that layer's `docs/layer-*.md`, and a large job's in its
`docs/brief-*.md`; this is the index. **This table is the only copy.** Nothing here is
re-litigated without a new row saying why.

**A row is short**: the question, the answer, one line of reason and a link to the brief or layer
doc that holds the evidence. A row that grows into an essay - with its status jammed into the Date
cell - is the failure this layout exists to prevent (1942-beeb's decision 15 ran to 10K).

**Status**, the lifecycle, and the first thing a reader looks at:

| Status | Means |
|---|---|
| `OPEN` | raised, waiting on the owner; nothing is built on it |
| `PROPOSED` | an answer is written down and costed, waiting on the owner's yes |
| `TAKEN` | the agent took it while the owner was away (an unattended job), provisionally; listed in that job's report for review |
| `AGREED` | the owner said yes, or **merged it: merging a branch agrees the decisions it carries** |
| `SUPERSEDED by N` | replaced by row N; the row stays, so what was ruled out stays ruled out |
| `REJECTED` | considered and refused; it also gets a line in the table at the bottom |

Taste calls (a colour, a speed, an outline) are settled by playing, not by argument: build test
discs side by side, each alternative one switch away (an environment variable or `-D` whose default
is the shipped value), and record whose eye chose. `python -m beeb_port_kit.check_decisions
docs/decisions.md` (the kit's `py/`) checks the table still renders and every status is one of
these; run it after editing.

| # | Date | Status | Decision | Where |
|---|---|---|---|---|
| 1 | 2026-09-07 | AGREED | **Target is the BBC Model B with sideways RAM**, with a `MASTER` build symbol for the Master 128 path. The template uses no bank and no shadow RAM, so both boot the same code; a port that needs a Master (two 16K screens for a 1-pixel scroll, as Edge Grinder did) records that as its own row and drops the B | `docs/layer-0-toolchain.md` |
| 2 | 2026-09-07 | AGREED | **Paradroid's geometry, Edge Grinder's frame shape.** Panel 4 rows at `&4A00`, strip 16 rows at `&5800` under the 10K wrap, R1 = 80, because Paradroid's timing was measured for it; two CRTC cycles rather than Paradroid's three, because nothing scrolls vertically so no R5 adjust needs a tail cycle to hide in. VSync at absolute row 31 (Paradroid's `FRAME_DROP_ROWS` = 3, KC's eye), inside cycle B, so R7 is a constant | `src/rupture.6502`, `docs/layer-0-toolchain.md` |
| 3 | 2026-09-07 | AGREED | **The rupture is switched on unaligned**, under an R8 blank: `setup_display` writes cycle B's shape and `install_irq` follows. Costs a malformed field or two at boot that b2 would show and jsbeeb does not. Paradroid's `RuptAlign` is the fix, parked for Layer 9 | `PLAN.md` |
| 4 | 2026-09-07 | AGREED | **The panel and the strip have a palette each, four physical colours and the OTHER four, so all eight MODE 1 colours are on screen at once** (KC's request). Paradroid's decision, for Paradroid's reason - the panel's colours must not be at the mercy of the play area's - with its two placements: the panel's sixteen ULA writes at the end of `rupt_vsync`, after the T1 restart; the strip's at the A -> B boundary. Panel = black, red, yellow, white; strip = blue, magenta, cyan, green. **This frame has no gap at the boundary** (Paradroid's panel cycle had 20 blank lines): sixteen writes are 96 cycles and MODE 1's horizontal blanking is 48, so the switch straddles a line boundary and is placed so its displayed-time part is harmless. **The straddle line is the panel's last scanline, kept ALL logical 0 by `export_panel.py`**: the twelve writes for logicals 1-3 land in its displayed part, where no pixel looks them up, and the four for logical 0 land in its blanking. It reads black end to end. The other placement - the strip's first line as the straddle - was rejected because blue is the strip's colour 0 and that line would have read black-then-blue; the sacrifice is a panel scanline the port controls, not one of the game's. Needs a third T1 fire: fire 2 is the switch, fire 3 the old fire 2 (R4 for B, which cannot be written in the same fire because it is still cycle A). `T1_TUNE2` is the measured phase | `src/rupture.6502`, `tools/export_panel.py`, `docs/layer-0-toolchain.md` |
| 5 | 2026-09-07 | AGREED | **The VSync hook restarts T1 before it does anything else.** Found by measurement while placing decision 4's switch: the frame-lock take runs on every second field only, and with the restart after it every fire alternated by the take's ~24 cycles between take and non-take fields - the same build gave two phases in two boots. Paradroid's rule was "the palette after the restart, so it cannot move the fires"; the general form is that NOTHING conditional goes before the restart | `src/rupture.6502`, `BUGS.md` #1 |

## Rejected, do not re-litigate

What was considered and refused, with the number that refused it, so the next session does not
cost it again. A rejection reversed by a new measurement becomes a numbered row above.

| What | Why it was rejected | When |
|---|---|---|
| Paradroid's three-cycle frame with the panel on top | Nothing here scrolls vertically, so there is no R5 adjust for a third cycle to hide; two cycles do it (decision 2) | 2026-09-07 |
