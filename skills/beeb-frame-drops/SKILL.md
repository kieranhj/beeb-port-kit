---
name: beeb-frame-drops
description: Measure whether the BBC Micro port is holding its frame rate by counting loop passes against fields over exactly 100 fields in the jsbeeb MCP, in each scenario that loads the game. Use when the user asks whether the game is dropping frames, whether a change slowed it down, or when a scroll "looks" smooth or juddery in an emulator.
---

# Frame-lock and drop check by counting

Whether the game is holding its rate, *measured*. "It looks smooth" is not evidence: the emulator
runs at the host's ~60 Hz, not the Beeb's 50, so a 5:6 judder is baked in before the code gets a
say. Paradroid sent a session chasing a regression that counting showed was a 31 % improvement.

**Sample:** exactly **100 fields** = **3,993,600** cycles (39,936 a field, interlace off)
**Expected:** field counter +100; pass counter +100 / `FRAME_LOCK` (50 for a 25 Hz game)
**Fewer passes than that:** dropped frames. More fields than 100: the IRQ is not healthy

## Steps

1. **Find the two counters in the project.** The loop-pass counter and the field counter
   (Paradroid `gameTick` / `fieldCount`; Edge Grinder `frame_count` / `field_count`), and
   `FRAME_LOCK`, from `CLAUDE.md` or `src/main.asm`. Take their addresses from `build/<NAME>.lst`,
   never from an old note - main-RAM addresses move every build. If either lives above `&8000`,
   `read_memory` returns whichever bank is paged *at that instant*, and a sprite engine pages
   banks mid-frame; break at the top of the main loop first, or pick a main-RAM copy.

2. **Boot into the scenario under test** (`beeb-smoke-test`, then play or poke to the state).
   Do not measure straight after heavy single-stepping: a 62-in-100 transient seen once after
   a debugger session and never again is recorded in Paradroid's audit as "flagged, not
   concluded". Measurements with the debugger in the loop can perturb the thing measured.

3. **Read, run 100 fields, read.**

   ```
   read_memory     session_id, address: <pass counter>,  length: 1
   read_memory     session_id, address: <field counter>, length: 1
   run_for_cycles  session_id, cycles: 3993600
   read_memory     session_id, address: <pass counter>,  length: 1
   read_memory     session_id, address: <field counter>, length: 1
   ```

   The counters are single bytes and wrap; subtract modulo 256. Use `run_for_cycles` here, not
   `run_frames`: the question is what the game did in a fixed span of real time.

4. **Read the result.** Fields +100 says the interrupt is healthy under load. Passes
   +100 / `FRAME_LOCK` says no flip was missed. Paradroid's table was 50/100 stationary,
   50/100 scrolling, 50/100 on a nine-droid deck; Edge Grinder's Layer 2 confirmed "10 game
   frames in 20 fields" the same way.

5. **Repeat in every scenario that loads the game**: stationary, scrolling, a busy screen,
   firing, the death sequence. Record a row per scenario. One scenario passing says nothing
   about the others.

6. **Prefer the in-guest instrument if the project has one.** Edge Grinder's `tim_over` in
   `src/timing.asm` is the definitive per-frame answer: field count minus the field of the last
   flip at handover, `FRAME_LOCK` or more meaning the flip was missed. It costs nothing. If you
   build a frame meter on a VIA timer, three traps caught Edge Grinder's before a single number
   was good: the two timer bytes are read one after the other and can roll between them (throw
   away a sample that goes backwards); a frame longer than 65.5 ms wraps the counter outright,
   which deaths and mode changes do (one measured 234 fields); and a phase *maximum* includes
   any interrupt that landed inside it, six a frame, so read maxima as upper bounds and take
   typical cost from single frames.

7. **Record the table in the layer doc** with the build (DEV or RELEASE, flags), the date, and
   the scenario. "50/100 scrolling, DEV, 2026-09-04" is the shape; put the headline in the
   commit body.
