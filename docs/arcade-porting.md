# Porting without source: arcade games and other emulated binaries

*The kit's other path. `PORTING.md` assumes the original's source or a disassembly you can trust;
this is what to do when all you have is a ROM set and an emulator. Distilled from the 1942 arcade
port (`1942-beeb`, 2026-09-07 to 10-23: 483 commits, 161 decisions, 95 bugs), which is the worked
example throughout. Citations are to that repository: `1942-beeb/docs/arcade-facts.md` §n,
`BUGS.md` #n, decision n. The tools are `py/beeb_port_kit/mame/`, `py/beeb_port_kit/ay2sn.py` and
`template/tools/mame/`; the procedures are the skills `beeb-arcade-capture` and
`beeb-rom-model-probe`.*

Most of this is machine-neutral. MAME is the instrument here, but the method - capture the
running original, model its routines in Python, score the model frame by frame, ship only what
scored - applies to any binary you can run in an emulator that exposes RAM: a cartridge, a disk
image with no source, a coin-op.

---

## 1. The rule this path adds

**The original is still the specification. The specification is now the running machine, not a
text.** Every rule the port ships is a Python model of a ROM routine, and a model counts only once
it has been scored against a capture of the real game: **0 wrong, with every excluded sample
named and counted.** A ROM read is a hypothesis; a fan guide is a lead; the emulator's RAM is the
fact.

1942 learned it by paying for every exception:

- The background map format was **guessed wrong from the ROM twice** before tilemap RAM was
  captured out of the running game and used as ground truth (CLAUDE.md §6). The first hypothesis
  matched the sea and nothing else (arcade-facts §6).
- The player's death was written from the disassembly, and was wrong: the recording never died, so
  the state byte was constant through all 5,528 frames of it (`BUGS.md` #12).
- A "3 MHz Z80" in decision 1 was the AUDIO CPU; the main one is 4 MHz (§7). Read
  `mame -listxml`, never recall it.

---

## 2. Inventory the whole game against RAM first

The single biggest saving available, and the one 1942 took late. `inventory32.py` existed on day
3, but the 32-stage need was priced only on day 7, after stage 1's layout had been fixed - and
every later feature opened with a RAM ledger ("main RAM 3 bytes, anything new needs a lever
first"). Six RAM hunts followed.

**Before the first level is built**, out of the ROM: every level's map, palette schedule and
script; every enemy family each level selects; the sprite cells each needs at the port's phase
count; the sounds; what a level costs raw and packed - **per level, never in aggregate** - and the
streaming unit the original's own data suggests (1942's eight named sets were each one map group
plus one map-S stage, which became the disc file; decisions 29, 87). Count the catalogue too: the
**31-entry DFS catalogue bound before the sector count did** (decisions 87, 138, 161).
`1942-beeb/tools/inventory32.py` and `stage_sprites.py` are the examples; the second scores what
each stage wants against what the build has free.

---

## 3. The instrument: MAME, and its traps

`beeb_port_kit.mame.runner` wraps every run; `template/tools/mame/README.md` lists what it guards.
The traps it exists for, each measured on MAME 0.177:

| Trap | What happens | Guard |
|---|---|---|
| **Two instances of one machine** | the second blocks for ever; a stuck one poisons every run after (45 s timeout with one running, 14 s alone; arcade-facts §1) | `already_running()`; run a CLONE (`1942a`) beside an interactive session, after confirming by CRC that it shares the ROM |
| **Relative output path** | MAME's cwd is its own; the Lua dies "No such file or directory" | `out` made absolute, passed as `CAPTURE_DIR` |
| **Stale output** | a script died on a locked file, the error was lost in a pipe, and the old file was handed over as a fix (`BUGS.md` #3) | every expected file must be newer than the run |
| **A Lua error** | MAME runs on silently for ever (1942's `upclamp.lua` threw on `mach.memory` before opening its output) | `_compat.lua` opens output first, catches every error, writes `lua_error.txt` and exits; the runner reports it |
| **stdin** | with no console behind stdin, MAME hung before running the script | `stdin=DEVNULL` |
| **`-debug -debugger none`** | the debugscript never runs; silent hang (§8) | refused |
| **`go` in a debugscript** | never returns; a `quit` after it never runs | pair a watching script with `stop_at.lua` |
| **No `logfile` in 0.177** | watchpoint `printf` goes nowhere headless | `trace FILE,0` + `tracelog` actions |
| **Two Lua APIs** | 0.177 is `manager:machine()`, `mach:memory()`, `emu.register_frame_done`, no `install_write_tap`; current docs describe the other | `_compat.lua` tries both under `pcall`; read state from RAM each frame instead of tapping writes |
| **`cfg/<game>.cfg`** | MAME applies it to `-playback` too, and rewrites it on every exit; 1942's had been hand-set to Easy and five lives, so every capture for weeks was Easy (§34) | the runner prints every override; `dips.lua` reads the live cabinet |
| **Past the end of the `.inp`** | MAME runs on; "stage 2" in every early capture was stage 1 resumed after the input ran out (`BUGS.md` #13; 31,000 frames of non-play in one analysis) | know each recording's length; capture `--frames` to it |
| **`-playback` desync** | deterministic (byte-identical over 2,400 frames) until the DIP switches change between record and playback | record the cfg with the `.inp` |

**The headless debugger** reads the code: `-debug -debugscript cmds.txt` with `dasm`, `wpset`,
`bpset`, `trace`. It is proven fast (seconds for a disassembly). `template/tools/mame/debugscript.txt`
is the sample, with what 0.177 does and does not accept.

**Keep captures outside the repository.** 1942's whole-game capture was 92 MB and lived beside
the repo, read by a tool in it.

---

## 4. Capturing: dump every frame, and drive what no recording shows

**Per-frame binary records, one schema.** `register_frame_done` writes a fixed layout every frame;
one reader parses it. In 1942 the layout lived twice, a list in the Lua and a list in the Python
("a field list copied twice is a field list that will be wrong once", `enemy_cap.py`). Here it is
one spec string (`records.py`), written beside the data as `schema.txt`:

```
f:frame;g:bytes@e103,e102,e0d2,e0d3;spr:bytes@cc00-cc7f;obj:slots@e400,10,30,30
```

**Record a human playthrough first** (`-record`): it is the oracle for how the game is actually
played, and it is deterministic on replay. 1942 had two: `kieran.inp` (stage 1, 5,528 frames of
input) and `kc2.inp` (42,300 frames: deaths, extra lives, a loop, POWs, game over, a high score).

**Then drive the game where the recording never went**, because *a state byte that is constant in
the recording has not been measured* (`BUGS.md` #12, #38). The bomber's sub-states were declined
twice (decisions 34, 35) until a recording reached them (59). The levers, all templates:

- **Hold a pending-state byte** (`hold_byte.lua`). 1942's stage init copies `($E106)` to `($E103)`,
  so holding `($E106)` at N starts stage N+1 - **and the attract demo plays it**, with no coin, no
  input and no way to lose a life. Any stage became capturable in about ten minutes, nine days in
  (§28: "the instrument was one byte away the whole time"). Hold it only until the game has taken
  it: a harness that keeps writing hides the transition.
- **Patch the input read in ROM, not RAM** (`force_input.lua`): the game overwrites its input byte
  before reading it, so a RAM poke never lands. 1942: `$1BFB CD 35 2D` (`call`) -> `3E xx 00`
  (`ld a,xx`). Or set ioport fields on a schedule for coins and starts.
- **Invincibility by the game's own path** (`invincible.lua`): redirect the hit tests into the
  "already hit" branch, so kills still score. Never poke lives or the death state.
- **The ROM checksum.** 1942 XORs its ROM in play and halts minutes after any unbalanced patch
  (`$7112`, halt at `$7166`). Two patches that happened to cancel ran 400,000 frames; the
  autopilot's per-frame byte froze the game at frame 69,428. It was found with a `TRACE_FROM` PC/SP
  log. `C.patch` asserts the original bytes and logs the running XOR and sum delta - measured
  2026-10-25: 1942's two hit patches cancel to `00`/`00`, the checksum patch itself does not.
- **A whole-game autopilot** (`autopilot.lua`): from where the recording ends, rewrite the input
  every frame. 1942's: 242,100 frames, all 32 stages, four bosses fought and shot down, the ending
  (`fullgame.lua`, 2026-09-16). That one capture fed most of the port's later work.
- **Find registers by cause** (`find_reg.lua`): write every value to every candidate address and
  read the window back. 1942's bank select, `$C806`, and nothing else (§7; re-found 2026-10-25).
- **Inject commands into the main CPU's own request ring** (`subcpu_ram.lua`), so a sub-CPU's input
  travels the real path, timing included.

**Sampling has a phase.** A per-frame sample cannot see banking inside a DI routine: 1942's level
script lives in a bank paged in for two bytes with interrupts off, never live at a frame boundary
(§7). A capture sampled every 4th frame compared with a screenshot from another frame collapses
from 97% to 25% (§5). Compare only on sampled frames.

---

## 5. The probe: model a routine, score it, 0 wrong

`beeb_port_kit.mame.probe.Score` is the shape of every 1942 probe (`probe_efire.py`,
`probe_pdeath`, `probe_large`, `probe_bomber`, `probe_turner`, `probe_sound`):

1. **Read backwards from data you already understand** (brief-wave-disassembly §4). 112K of Z80
   is too much to read cold. A write watchpoint on a known spawn's sprite slot names the sprite
   writer; a watch on the table it copies from names the object creator; what the creator reads is
   the schedule. Every link confirmed against captured RAM (§12).
2. **Transliterate the routine** into Python, tables read from the ROM image (`romset.Banked`),
   never retyped. **Print table pointers; never read them by eye**: a dispatch table read with one
   digit transposed sent the reader to a bare `ret`, documented as "no steering at all" (§18).
3. **Score it frame by frame**, per rule and **per type, never in aggregate** - 113 of stage 1's
   119 objects were one plane type, so an aggregate measured almost nothing (§12).
4. **The pass mark is 0 wrong.** *"A residual you cannot explain is a defect you have not found
   yet."* Three jumps in 32,971 samples were a real coordinate defect (`BUGS.md` #8); 3,333 frames
   rationalised away were another (#10).
5. **Exclude by a named cause, never by a tolerance**, and count each one ("a freeze flag was
   set", "a sprite record was freed inside the frame"). 1942's player-mover exclusions were all
   *derived* from the game's own rules, not frame ranges (§19).
6. **Check the instrument's phase before the rule.** Sprite RAM is `LDIR`'d from a shadow copy, so
   a capture of it is one mover step late: 0 of 83 became 83 of 83 (§16). A RAM-to-RAM read is
   not late, and assuming it was cost six residuals in 2,146 (§18). Four "mover" residuals were all
   the capture's frame boundary (§19).
7. **A torn sample must be followed by a match.** MAME samples at frame end, mid-IRQ on a
   sub-CPU; a model error propagates and a torn snapshot does not (`probe_sound`: 2,859 match, 146
   torn, 0 wrong). `observe(..., torn_ok=True)`.
8. **"Unread" is a value.** `bank_stream` had `if p["e0af"] is not None`, which silently meant
   "leave the bank at 2" - wrong on 8 of 32 stages, and the path was deterministic all along (§28).
   A model refuses a path it does not follow: raise `probe.Unread`.
9. **A filter defines its answer.** A slot filter could only ever find 4 of the boss's 16 records
   (`BUGS.md` #46). Read live state from the run being scored, never another run's last frame (§28).
10. **One copy of each decode.** `rom_map.py` was the only map decode; `probe_map.py` scored it and
    `export_gfx.py` shipped it, so the scored and the shipped could not drift. Score on content that
    *discriminates* - the sea confirms everything and discriminates nothing.
11. **Close the loop on the port**: the same model replayed over the port's own emulator trace,
    re-seeded every frame so errors stay local. MAME -> model -> port, one model for both sides
    (1942's `verify_turner.mjs` spawns `check_turner.py`).

**A ROM read with no counterpart in a capture is a lead.** When a table search finds nothing above
chance, look for a counter or an RNG: 1942's spawn schedule was never found as a table because
there was none - an interval of `5 + (rnd & 6)` from a free-running counter (§12).

**Secondary sources are leads, scored.** Fan guides' structural claims scored 8/8, 4/4, 8/8 and 8/8
against the ROM and corrected the operator's manual twice (`inventory32.py` part H, §29).

---

## 6. Rotation and named spaces (decision 13, `BUGS.md` #1)

A vertical cabinet's hardware scans a landscape raster; the player sees it rotated. The driver,
tilemap RAM, sprite records and **every cell in the graphics ROMs** are in the hardware's
orientation. So:

- **Name every space** - *raw* (what the hardware scans) and *play* (what the player sees, and
  what the BBC uses) - and never write a dimension without its space. "224 play-pixels wide".
- **Measure the rotation**: rebuild a frame from captured RAM, render it under all four rotations,
  diff each against a same-frame screenshot (`orient.lua` + `orient.score_rotations`). 1942: ROT270
  96.3%, the others 46-48%. **Use an asymmetric scene**: symmetric content passes a broken
  rotation, and `score_rotations` refuses a near-tie. `-listxml`'s `rotate` is the prediction.
- **Cell contents AND flip bits are raw.** A raw X-flip is a play Y-flip under ROT90/270
  (`orient.flips_to_play`). The first 1942 level placed every tile right and drew every one 90
  degrees out, and "it looks like terrain" passed it; the aircraft were nearly symmetric too.
  `verify_orientation.py` (97.74% against a real frame when right, 25-50% when not) is the check.
- **Size fields follow raw axes.** 1942's sprite size field extends along raw Y, which is play X:
  the boss is 256 play-pixels *wide*, not tall.

---

## 7. Hardware-format traps

- **Transcribe the `gfx_layout` AND the sprite drawer from the driver source.** Planes are listed
  most significant first; getting it backwards permutes colours without changing shapes, and the
  sea's pens were fixed points of the reversal, so sea frames passed (`BUGS.md` #2). **Verify on
  the busiest frame.** `romset.GfxLayout` takes the layout as data.
- **A sprite code can be assembled from several bytes.** 1942's was 8 of 10 bits, the other two
  from the attribute byte; the port drew two small planes where the bomber belongs and **every
  oracle scored zero**, because they all checked against the same wrong table. A screenshot caught
  it (`BUGS.md` #16) - the one thing a screenshot is good for.
- **Coordinates have ninth bits and wrap.** 1942's attribute bit 4 *subtracts* 256 from raw X
  (`BUGS.md` #7); play Y is signed 9-bit, unwrapped at the middle of a gap the data itself shows
  (#8). The continuity test (no frame-to-frame jump) found all three coordinate defects; the
  buffer oracle found none.
- **Banked ROM** reads `$FF` above a short bank (§7). Find the select register by cause.
- **Palettes**: resistor weights and lookup PROMs come from the driver's palette init
  (`romset.prom_palette`, `lookup`). Reduce to the BBC's pens by ROLE, not nearest colour.
- **DIP switches are a measurement** (decisions 36, 68): read the live cabinet, scan the ROM for
  every read of the DIP ports, decide which setting the port hard-codes, and mark every dependent
  constant `DIPSWITCH:` in the source.

---

## 8. Sound from the ROM alone (decisions 46-54)

The kit's other sound route is Arkos from a tracker file. This one needs only the ROM.

1. **Run the sound CPU headless** (`mame.z80sub.SubCPU`, on the `z80` package): MMIO callbacks for
   the latch and the chip ports, a **held** IRQ at the measured rate with lateness accounting. 1942:
   4 IRQs a video frame, measured from an IRQ counter in the handler (`subcpu_ram.lua`).
   Re-measured 2026-10-25 on the kit's module: command `$11` takes its IRQ up to 3,067 T late,
   `$17` loses one assertion whole - without the accounting the model drifts.
2. **Score it RAM for RAM against MAME** with injected commands: 2,859 match, 146 torn, 0 wrong.
   The kit's module reproduces 1942's rips register for register (`test_mame_z80sub.py`).
3. **Convert offline, per field** (`beeb_port_kit/ay2sn.py`): clocks as parameters, the game's
   own channel priority (decision 46: the sound ROM's output chain decides who is heard, not the
   converter), periodic-noise bass below the SN floor (47), the three loudest voices, sticky.
4. **Judge only the conversion by ear** (50): everything upstream is exact. `render_ay`/`render_sn`
   give both chips' WAVs side by side.
5. **The exporter refuses to write** unless its model of the 6502 player reproduces the conversion,
   field for field. **Decode the chip bytes; never count them**: a count of writes passed three
   corrupted tunes (`BUGS.md` #66).

`ay2sn.py` is as useful to a CPC or Spectrum port: an AY at another clock.

---

## 9. The porting rules an arcade forces

- **A frame-rate policy that makes the arithmetic integral** (decision 10): 59.6 Hz treated as
  50, logic at 25 Hz, every per-frame delta doubled - so the scroll is exactly 1 pixel a tick.
  **A per-object routine called twice a tick is one arcade frame per call**; a new mover written
  per tick moves double.
- **Port the rule on your own counter; keep the data exact** (decisions 23, 25, 61). Free-running
  counters drive the original's spawn timing and jitter; reproducing them cycle-exactly is not
  porting. Take the rule, drive it from the port's own counter, drop pure jitter, record each as a
  decision.
- **Recorded data may stand in for a rule only as declared scaffolding** (decision 22's replay of
  the arcade's sprite RAM, retired by 134 once the rules existed).
- **The arcade's sprite hardware has no blit cost; the BBC's does.** That forces a per-family
  phase and direction budget, a spawner throttle keyed on the last tick's record count -
  deterministic, so oracles stay reproducible (decision 119) - and **a sprite bigger than the
  budget drawn as background**, composited into the scrolling ring and moved by the scroll,
  backwards included (decisions 114, 156: the boss fight's tick went from 180,824 to 28,733 cycles,
  after three days on a dedicated blitter that was thrown away). Ask what hardware the port already
  drives before writing an engine.
- **Stream in the original's own grouping**, and **evict at a seam only on a proof computed from
  the data** ("boss stages never spawn classes 2 and 3", checked at export, which refuses
  otherwise; decisions 104, 106, 107). Two files that share an address are told apart only by
  reading the bytes back; gate every call into swappable code, because being wrong there
  *executes* the wrong code.
- **The arcade front end** - coin, start, ranking, attract cycle (decisions 121-127, 136, 157, 159).

---

## 10. Order of work

1. `mame -listxml <game>` -> `romset.parse_listxml`: CPUs and clocks, sound chips, the display's
   rotation, the DIP switches, every ROM with its CRC. `RomSet` checks the zip against it.
2. `runner --cfg` and `dips.lua`: what the cabinet you will capture is set to.
3. Record a human `.inp` that plays as far as you can.
4. `capture_ram.lua` over it; `orient.lua` + `score_rotations` on an asymmetric frame.
5. **The inventory** (§2), out of the ROM, scored where captures reach.
6. `hold_byte`, `force_input`, `invincible`, `autopilot`: a capture of the whole game, outside
   the repo.
7. Per routine: the probe (§5), 0 wrong, before any 6502 is written for it.
8. Then the kit's layers, with each probe's model replayed over the port's trace.
