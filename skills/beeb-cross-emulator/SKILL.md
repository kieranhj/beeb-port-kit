---
name: beeb-cross-emulator
description: Checklist for getting a second opinion on a BBC Micro port's display-bank switches, mid-frame CRTC changes and displayed-memory tricks from b2 or beebjit, and then real hardware, because jsbeeb cannot see everything. Use when a rupture, a shadow-bank flip, a CRTC register change or a display below &3000 is about to be called done, or when something works in jsbeeb and a tester says it does not.
---

# Cross-emulator check for display-bank and CRTC tricks

jsbeeb is the instrument for almost everything, and there are things it cannot see. Each of
these was found by a second emulator or by hardware, after jsbeeb had said it was fine:

- **What the video fetches below `&3000` with the shadow bit set.** jsbeeb displayed Edge
  Grinder's panel at `&2000` under both shadow states; b-em showed garbage on alternate frames.
  The rule became *nothing displayed may live below `&3000`* (Edge decision 17).
- **A misplaced field.** Paradroid's handover into the rupture produced one short field and a
  vertical roll; jsbeeb reported 39,93x-cycle fields throughout. b2 showed it. A frame-length
  instrument measures length, not phase.
- **The mid-frame bank flip** is measured in jsbeeb only, and Edge Grinder's rules say so.
- **Perceived smoothness** - no emulator can judge it (`beeb-frame-drops`).

**Second emulator:** b2 or beebjit (b-em is no longer used); `b2 -0 <ssd> -b` or `beebjit -0 <ssd> -autoboot` (`-master` for a Master, `-swram 4` per bank)
**b2 debug build:** HTTP API on port **48075**; `peek` reads memory, `paste` types BASIC, **there is no screenshot endpoint**
**Real hardware:** last, and dated in the layer doc

## What must be seen, and where

1. **Anything that switches the display bank, changes CRTC shape mid-frame, or displays memory
   the MOS would not, gets b2 or beebjit before it is called done.** Launch it on the padded
   image the build wrote, with the model the build targets (the project's `build.ps1 -Run` should
   do exactly this; check which emulator and model it passes):

   ```powershell
   .\build.ps1 -Run
   # or directly
   b2 -0 build\GAME.SSD -b
   beebjit -0 build\GAME.SSD -autoboot
   ```

   Look at: the panel and play area at rest, the transition into and out of every rupture shape
   (titles to game, game to titles, death, completion), and several seconds of each state.
   You are looking for garbage on alternate frames, a roll at a transition, a torn or flashed
   field. Watch, do not screenshot; the fault classes here are temporal.

2. **For a phase question - "did a field come out short or rolled?" - b2 is the instrument.**
   Its debug build's API (`doc/Debug-version.md` in its tree): `peek/WIN/BEGIN/END` returns
   memory as binary, with `?s=m` main, shadow, a paged ROM, ANDY or HAZEL selectable by suffix;
   `paste/WIN` types BASIC in. `poke` to an I/O address has **no effect** - it writes emulated
   memory, not the bus - so a register write goes through `paste` and the 6502 does it.

   ```
   curl --data-binary '?&FE22=&27
   ' http://localhost:48075/paste/b2
   curl -o buf.bin "http://localhost:48075/peek/b2/0x5800/+0x2800?s=m"
   ```

   Paradroid proved `peek` byte-identical to the file on disc on 2026-08-21. The display half
   needs eyes on the window; the buffer half is the half these ports trust, and `peek` gives it.

3. **Compare the buffer, not the picture, across emulators.** Dump the same region from jsbeeb
   (`save_memory`) and from b2 (`peek`) at the same game state and `cmp`. If the buffers agree
   and the pictures do not, the difference is in what the emulators *display* from the same
   bytes - which is exactly the class of fault this skill exists for, and is real.

4. **Real hardware last, and record it.** Paradroid's first run on a real Master is dated in
   its `layer-13-compatibility.md` with the list of machines still untested. A NuLA build wants
   NuLA hardware as well as jsbeeb (which does emulate the palette, measured 2026-09-05 - the
   belief that it did not let a register mistake reach hardware first).

5. **Write down which emulators have seen it**, in the layer doc, per trick: "mid-frame flip:
   jsbeeb 2026-09-04; b2 not yet; hardware not yet". A trick with one emulator's name against
   it is not done, and the doc should make that visible rather than the next tester.

## A related MCP quirk

`read_memory` at `&8000` and above returns whatever bank is paged **at that instant**, and a
sprite engine pages banks in and out mid-frame, so a sideways-RAM variable reads plausible
nonsense between frames. Break somewhere the resting bank is up (the top of the main loop), or
verify against a main-RAM copy or the panel instead.
