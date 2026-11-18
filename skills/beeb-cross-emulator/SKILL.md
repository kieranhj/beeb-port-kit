---
name: beeb-cross-emulator
description: Checklist for getting a second opinion on a BBC Micro port's display-bank switches, mid-frame CRTC changes and displayed-memory tricks from b2 or beebjit, jsbeeb's main branch beside the pinned one, and real hardware, because no one emulator sees everything - with a table of what each models. Use when a rupture, a shadow-bank flip, a CRTC register change or a display below &3000 is about to be called done, or when something works in jsbeeb and a tester says it does not.
---

# Cross-emulator check for display-bank and CRTC tricks

jsbeeb is the instrument for almost everything, and there are things it cannot see. Each of
these was found by a second emulator or by hardware, after jsbeeb had said it was fine:

- **What the video fetches below `&3000` with the shadow bit set.** jsbeeb displayed Edge
  Grinder's panel at `&2000` under both shadow states; b-em showed garbage on alternate frames.
  The rule became *nothing displayed may live below `&3000`* (Edge decision 17). **A real Master
  has since answered it**: with ACCCON D = 1 the 6845 reads HAZEL for CRTC addresses below
  `&3000` (`&1800` shows `&C800`; phX's hardware-test disc, test I, 2026-11-15), as jsbeeb and b2
  model it. b-em was the wrong one; the rule stands.
- **A misplaced field.** Paradroid's handover into the rupture produced one short field and a
  vertical roll; jsbeeb reported 39,93x-cycle fields throughout. b2 showed it. A frame-length
  instrument measures length, not phase.
- **The mid-frame bank flip** was measured in jsbeeb only, and Edge Grinder's rules say so. phX's
  test A has since switched ACCCON D mid-line on two real Masters: it acts at the character
  written, odd or even C0, cleanly - as jsbeeb shows.
- **The vertical total adjust displaying when `R6 = rows + 1`** - the fact a scanline vertical
  scroll's bottom sliver comes free from - is a jsbeeb 1.25.0 result on a Master (1942) and on a
  Model B (the kit's own `template/examples/vscroll`), both 2026-09-08. Rich Talbot-Watkins's demo
  disc relies on it and runs in jsbeeb too; nothing has checked it on b2, beebjit or hardware. A
  port that spends the row it saves should check first.
- **Perceived smoothness** - no emulator can judge it (`beeb-frame-drops`).

**Second emulator:** b2 or beebjit (b-em is no longer used); `b2 -0 <ssd> -b` or `beebjit -0 <ssd> -autoboot` (`-master` for a Master, `-swram 4` per bank)
**b2 debug build:** HTTP API on port **48075**; `peek` reads memory, `paste` types BASIC, **there is no screenshot endpoint**
**Real hardware:** last for a game; from the first raster or disc layer for a demo; dated in the layer doc

## What each emulator models (phX, 2026-11; the facts are in `docs/hardware-facts.md`)

| | Master MA13 address flip | palette / R8 writes early | 1770 timings | ACCCON D below `&3000` | monitor (black clamp, sync) |
|---|---|---|---|---|---|
| **real Master** | MA6 every other character, MA7 too on alternate lines | `&FE21` about a MODE 2 pixel early; R8 part of a character early | READ ADDRESS's INTRQ at once after byte 6 | reads HAZEL | Sony clamps black in the back porch and loses sync on a frame ending on a 2-character line; the CUB bends |
| **jsbeeb pin** (the MCP's, 2.10.2) | none | at the character written | READ ADDRESS's INTRQ 48 us or more late; tracks skewed ~3 sectors | HAZEL | none |
| **jsbeeb main** (2.22.x, `JSBEEB_SRC`) | modelled (#1859) | `4 - p` texels early (#1868) | timed from a real Master (#1860) | HAZEL | none |
| **beebjit** | MA6 only | `&FE20` a little early (test B) | its own drive timing (phX's load margins differ) | - | none |
| **b2** | none | - | - | HAZEL | none |
| **b-em** (not used) | - | - | - | wrong | none |

`-` = not checked. **No emulator models a monitor**: a lit back porch, a frame ending on a short
line, an HSync position that sits the picture off the tube are found on the owner's monitors only.
Run the headless suite on **both jsbeeb versions** (`beeb-oracle-harness`): a check that passes on
one and fails on the other is a fact about the emulator, and goes in `BUGS.md` with its reason.

## What must be seen, and where

1. **Anything that switches the display bank, changes CRTC shape mid-frame, or displays memory
   the MOS would not, gets b2 or beebjit before it is called done.** Launch it on the padded
   image the build wrote, with the model the build targets (the project's `build.ps1 -Run` should
   do exactly this; check which emulator and model it passes):

   ```powershell
   .\build.ps1 -Run
   # or directly
   b2 -0 build\game.ssd -b
   beebjit -0 build\game.ssd -autoboot
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

4. **Real hardware, and record it.** Paradroid's first run on a real Master is dated in
   its `layer-13-compatibility.md` with the list of machines still untested. For anything on a
   knife edge (mid-line palette, RVI, MA13, the 1770), build a **hardware-test disc** early - a
   menu of numbered tests, a phone checklist, results per machine and monitor (`PORTING.md`
   section 12) - rather than waiting for the release. A NuLA build wants
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
