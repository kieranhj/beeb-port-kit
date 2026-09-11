# Verification: the measuring and checking procedures

Fifteen procedures, numbered so a reader can pick one by number. Each gives the manual route
first - what to do by hand in [jsbeeb](https://bbc.xania.org), b2 or beebjit - and then, in a short
sub-block, the same thing as calls to the jsbeeb MCP server (`jsbeeb-mcp` on npm, used from
Claude Code). Nothing in the MCP block is needed to follow the manual one.

Every procedure here was used more than once across the two ports, and most of them were learned
the expensive way: a screenshot said "fine" while the buffer was a column out; a smooth-looking
scroll was dropping a field in three; a tune played happily for thousands of frames from the
wrong address before running off the end of its data. Paradroid's rule, carried into Edge
Grinder's rules file word for word, is **verify against the buffer, not the screenshot**, and the
procedures below are what that rule turned into in practice.

The other reason to have them written down: every measured fact in
[`hardware-facts.md`](hardware-facts.md) came from one of these. The CRTC write windows, the T1
scanline counts, the four display-wrap sizes, ANDY's 4K window, the key numbers, whether jsbeeb
emulates the NuLA palette - each is the output of a procedure here, and a fact that cannot say
which procedure produced it is a recollection, not a fact. Both ports' rules files say do not
write hardware code from recalled facts; this document is the alternative.

Sources are linked inline. Where a port did *not* do something this document describes, it says
so rather than filling the gap from imagination.

---

## Before you start: three conventions

**Addresses come from the listing, every time.** Builds keep the assembler's `-v` listing in
`build/`; main-RAM addresses shift on every build, and a breakpoint or a memory read against a
stale one measures nothing. **Under Baron this is not optional**: with zero-page allocation on,
a `ZA_AUTO` variable's address is chosen by the assembler and moves when the code changes, so
the listing is the only place it exists at all.

```bash
python -m beeb_port_kit.listing symbols build/game.lst score      # any substring
python -m beeb_port_kit.listing symbols build/game.lst            # everything
```

That prints `name = &addr` for every label and every `[auto]` allocation. It is `py/listing.py`
in this kit, and it exists because Baron has no symbol dump - BeebASM's `-d` had no successor
(asked for upstream: waitingforvsync/baron#5), and Baron's listing puts a label on its own line
with the address on the *next* line that carries one, so it wants a parser rather than a grep.
Two things the listing cannot give you either way: a computed constant's value (the listing
echoes `PLAY_R7 = 34 - FRAME_DROP_ROWS - PANEL_CYC_ROWS` unevaluated, so `PRINT` the ones you
care about, as the template does for its T1 constants), and anything at all from a build you did
not keep.

The BeebASM equivalent, for the two shipping ports:

```bash
./bin/beebasm.exe -i src/main.asm -do build/symbols.ssd -D RELEASE=0 -d | tr ',' '\n' | grep "'score'"
```

`-do` is there only to stop beebasm dropping loose `SAVE` files in the project root; Baron writes
nothing without `-p` or `-o`, so it needs no such guard.

**Snapshot the state you are going to measure from.** `save_state` keeps a whole machine
server-side under an ID and `restore_state` puts any session of the same model back to it -
memory, registers and `elapsed_cycles` exactly, so a measurement can be repeated from the same
instant rather than re-reached. Booting to a game state costs a disc load and a few hundred
frames; a restore costs one call, and the same state can seed several machines at once. Two
things to know: jsbeeb's frame counter keeps climbing across a restore (so count frames as
deltas, never absolutely), and **the keyboard is not in the snapshot** - a key held with
`key_down` is still held after a restore, and will go on scrolling the game while you wonder
why. `key_up` as part of restoring. Both measured 2026-09-07; `hardware-facts.md` has the
numbers. `destroy_machine` when a session is finished, and `delete_state` when a snapshot is:
states outlive their session and are freed only when deleted.

**Units.** The 6502 runs at 2 MHz; the MCP's `elapsed_cycles` and `run_for_cycles` count 2 MHz
cycles. Both VIAs' timers count at **1 MHz**, so a T1 or T2 reading is half the CPU cycles, and
a scanline is 64 us = 128 cycles. A 50 Hz field is 39,936 cycles with interlace off, which is
what a ruptured display runs; jsbeeb's `run_for_cycles` help text warns that the default MOS
frame is 40,000. A 25 Hz game frame is 79,872 cycles. Edge Grinder's frame meter reports
microseconds - double them to compare with anything in either `docs/`.

---

## 1. Boot-and-look smoke test

The first thing after every build, and the only procedure here that trusts a screenshot - for
"did it boot", a screenshot is enough.

1. Build, then take the **post-processed** image - the kit template's `build/game.ssd`, or the
   ports' `build/EDGE-200K.SSD` / `build/PARADROID-200K.SSD`, which are padded because those
   projects publish that file. The assembler's own output (`EDGE-RAW.SSD`, `PARADROID-raw.ssd`) is
   not bootable in either port - the loader expects the compressed layout that
   `tools/make_disc.py` writes. **Padding is a publishing convention, not a boot requirement**:
   jsbeeb stopped complaining in 1.9.0 and jsbeeb-mcp 3.0.0 is the first release whose dependency
   guarantees it (`docs/hardware-facts.md`, and the kit booted a 2,304-byte image on both models
   through the MCP to check). Pad what you publish, so a released size that differs from last time
   is itself a signal; do not pad to test.
2. Choose the model the game is built for. Edge Grinder is a **Master 128** - shadow RAM, ANDY,
   HAZEL, ROM paging - and boots wrongly on anything else. Paradroid targets a B with sideways RAM
   and was verified on jsbeeb's `B-DFS1.2` and on a Master
   ([layer-13-compatibility.md](https://github.com/kieranhj/paradroid-beeb/blob/main/docs/layer-13-compatibility.md)).
   jsbeeb's `B-DFS2.26` model errored in the MCP when Paradroid tried it: the MCP's model list is `B-DFS1.2`, `B-DFS0.9`, `B1770`, `B1770A`, `Master`, `MasterADFS`, `MasterANFS`.
3. SHIFT+BREAK. Wait for the title, take a screenshot, look at it once.
4. **The stale-session trap.** After many boots and keypresses in one jsbeeb MCP session,
   `boot_disc` stops autobooting and the screen shows `Searching` / `File not found` - the tape
   filing system, meaning SHIFT was not seen at BREAK. The disc image is fine. Make a fresh
   machine; do not go hunting through the catalogue. Check first that no key from an earlier test
   is still held, because a held key at BREAK causes the same symptom for a real reason. Paradroid's
   perf audit hit this again on 2026-08-31.
5. If the first MCP connection of a session times out, reconnect (`/mcp`) and try again - Edge
   Grinder's Layer 0 notes exactly that.

```
create_machine  model: "Master"                       # or "B-DFS1.2"
boot_disc       session_id, image_path: "<abs path>/build/game.ssd"   (whatever the project ships)
run_frames      count: 400
screenshot
```

---

## 2. Geometry by poked patterns

For anything about *where* on the screen a row or a band lands. The jsbeeb screenshot crops to
the active display area, so an absolute pixel position in it moves when the display start moves;
Edge Grinder's rule is **measure geometry with poked patterns, not by pixel position**
([layer-2-display.md](https://github.com/kieranhj/edge-beeb/blob/master/docs/layer-2-display.md)).

1. Work out the buffer address of the row or cell you are asking about, from the CRTC start
   address and the stride (in both ports a character row is 640 bytes - MODE 1 or MODE 2 at 80
   bytes per scanline).
2. Poke a run of a recognisable value - `&FF` for white - across that row. For a band, poke two
   rows a known distance apart.
3. Screenshot and measure the distance between the marks, not their absolute position. Edge
   Grinder's panel was confirmed this way: white poked into panel rows 0 and 4, 32 scanlines
   apart in the screenshot, the play area starting immediately below.
4. Vary the thing you are testing (display start, R12/R13, the bank bit) and poke again; the marks
   should move with it, or not, as the theory predicts.
5. For a *shadow* question, poke the same address in both banks with different values and see
   which one shows. This is how the mid-frame bank flip (`hardware-facts.md`) was seen: main RAM
   above the switch, shadow below it, with a step part way along the scanline the write landed in.

Two cautions. The MCP `screenshot` misrendered Paradroid's three-cycle rupture as full-screen
noise while the real jsbeeb page rendered it fine (KC confirmed 2026-08-18); if the picture is
garbage but the buffer is right, suspect the capture path before the game. And a screenshot from
the MCP is `active_only: true` by default, cropped and 2x scaled - pass `false` for the whole
1024 x 625 field if you need the raw geometry.

```
write_memory  address: 0x3000, bytes: [255, 255, ... ]    # a row of white
run_frames    count: 2
screenshot    active_only: false
```

---

## 3. The buffer oracle

The strongest check either port has. An **oracle** is an independent rendering of what the play
buffer should contain; the check is a byte-for-byte diff against what the game actually drew, at
the awkward positions. Paradroid's oracle is `RedrawAll` on a debug key (CTRL+R, `DEBUG_REDRAW`,
on in every dev build), and nearly every commit from Layer 3 on ends "0 of 10,240".

**Edge Grinder never built its redraw oracle.** Its rules file asks for one - redraw the whole
strip from the map at the current scroll position, sprites restored, diff at both bank parities -
and its layer docs say "still no buffer oracle" from Layer 3 to Layer 5. What it built instead
were *model* oracles for two specific screens (procedure 15 and the titles/mega-hero checks
below). Build yours in Layer 3, before the scroll is trusted.

The recipe, from Paradroid's
[CLAUDE.md](https://github.com/kieranhj/paradroid-beeb/blob/main/CLAUDE.md),
[ram-pass.md](https://github.com/kieranhj/paradroid-beeb/blob/main/docs/ram-pass.md) ("The oracle
recipe changed") and
[raster-timing.md](https://github.com/kieranhj/paradroid-beeb/blob/main/docs/raster-timing.md)
("How it was verified, and the trap in the obvious method"):

1. **Drive the view to an awkward position and stop.** Every scrolling bug so far has hidden in
   one of: an odd `mapHX`, a non-zero `line` (scanline offset), a diagonal. Let the view settle -
   about 1,500,000 cycles - so no scroll is still in flight.
2. **Freeze with the player at rest.** Restores replay every pass while draws are off (`sprSaved`
   is only cleared by a draw), so a freeze taken mid-deceleration stamps stale tiles into a
   scrolled buffer on every later pass.
3. **Disable every writer.** Poke *all* the draw call sites to NOPs - in Paradroid that is the
   `JSR SprDrawAll` **and both `JSR SprDrawTr`s** near the top of the main loop. NOPing only the
   first was enough until the tranche split; after it the split path kept drawing and the diff
   showed a player-shaped block of false corruption. Let a pass or two run so the restores take
   every sprite off the buffer. If the deck cannot be made quiet (a door animating under a droid,
   a cleared-deck recolour), freeze `JSR DroidsUpdate` too.
4. **Take both dumps inside ONE pass.** Hold the redraw key and break on the `JSR RedrawAll`
   itself; dump the buffer (A). Clear that breakpoint, break on the instruction after it, run,
   dump again (B). `RedrawAll` takes over 500,000 cycles, so the first run may not reach the
   second breakpoint - run again rather than concluding it was missed. Nothing else has moved
   between A and B: it is the same pass.
5. **Diff.** The result is reported as "N of 10,240" (Paradroid's strip is 10K) and the pass mark
   is 0. Anything droid-shaped in the diff: resume draws, let the overlap heal, re-freeze
   somewhere quiet.
6. Repeat at the other parity of everything in step 1, and - in a double-buffered port - at both
   bank parities.

**Feed the oracle the state the hardware was using, not the state the game has got to.** A
frame-locked port has *two* of every scroll variable: the main loop computes the next position and
parks it, and the VSync hook takes the parked pair when `FRAME_LOCK` fields have passed - so at any
moment the main loop's `scroll`/`line` are up to one game tick ahead of what the CRTC was given,
and only the live pair is on the screen. 1942's view oracle, fed the parked pair, scored **57,284
of 57,344 pixels wrong on a build that was completely correct**, and reported the model's answer
for `line + 1` at every position (2026-09-07, jsbeeb 1.25.0, Master). Read `crtc_live`/`line_live`,
not `scroll`/`line`. The same applies to anything else the hook latches at VSync - a bank parity, a
palette index, a display wrap - and it is worth naming in the oracle's own header, because the
failure looks exactly like a real regression.

The trap in the obvious method: the first attempt dumped, pressed the key, ran 800,000 cycles and
dumped again. That is twenty passes, and a door opening or a recharger turning in between is a
diff that has nothing to do with the change under test. It reported 35 and 196 bytes wrong on
two builds that were both correct; the baseline scoring 0 on the same method was luck.

**Per-project parameters** (yours will differ; record them in your own rules file):

| | Paradroid | Edge Grinder |
|---|---|---|
| buffer | `&5800`, 10K, hardware-wrapped | `&4000-&7FFF` x 2 banks, 16K each |
| oracle | `RedrawAll` on CTRL+R | not built - see procedure 15 for the model checks |
| positions to vary | `mapHX` odd/even, `line != 0`, diagonal | scroll phase odd/even, both bank parities |
| writers to NOP | `SprDrawAll`, both `SprDrawTr` | would be `spr_draw_all` and the scroll's column copy |
| dump size | 10,240 | 16,384 per bank |

**A framebuffer lit-run length is a cheap structural test to run beside the diff.** Count the
scanlines that are lit and check it is one unbroken run of the expected height: if a CRTC cycle
stops displaying where it should not, the run is short and - in a scanline scroll, where the last
`line` scanlines come from the vertical total adjust - the number moves with the scroll instead of
standing still. 1942 asserts `224x272, one run, nothing else lit` on every position it checks
(2026-09-08, jsbeeb 1.25.0, Master). It costs one pass over the framebuffer and it catches whole
classes of frame-shape error that a pixel diff of the play area alone does not see.

**A model oracle is the same check with the reference computed off-machine.** Edge Grinder's
titles ([layer-6e-titles.md](https://github.com/kieranhj/edge-beeb/blob/master/docs/layer-6e-titles.md)
§7) read the whole 8K zoom ring out of jsbeeb; every 16-byte cell had to be exactly the block or
exactly the blank (512 of 512, both bands), and the six cells that make a displayed column were
decoded back to bits and matched against the message rendered through the font in Python - 40 of
40 columns in each band, the top band against a 180-degree rotation, *at the same message
column*, which is what proves the two bands are in step and not merely each self-consistent. The
"MEGA HERO" message ([layer-9c-mega-hero.md](https://github.com/kieranhj/edge-beeb/blob/master/docs/layer-9c-mega-hero.md))
dumped **both** shadow banks with the run stopped during the bonus and compared every one of the
480 cells against `mega.bin`: 0 mismatches in main, 0 in shadow. Taken during the finale instead
it gives 13, all under explosions - so the doc says *when* to dump, and that is part of the recipe.

```
# settle, then freeze the draws
run_for_cycles  cycles: 1500000
write_memory    address: <JSR SprDrawAll>, bytes: [234, 234, 234]     # EA EA EA
write_memory    address: <JSR SprDrawTr #1>, bytes: [234, 234, 234]
write_memory    address: <JSR SprDrawTr #2>, bytes: [234, 234, 234]
run_frames      count: 4
# dump A at the redraw, dump B after it, same pass
key_down        key: "CTRL"    key_down key: "R"
set_breakpoint  address: <JSR RedrawAll>
run_for_cycles  cycles: 200000
save_memory     address: 0x5800, length: 10240, path: ".../a.bin"
clear_breakpoint id: <that one>
set_breakpoint  address: <JSR RedrawAll + 3>
run_for_cycles  cycles: 600000                 # run again if it did not reach it
save_memory     address: 0x5800, length: 10240, path: ".../b.bin"
```

Then `cmp -l a.bin b.bin | wc -l`, or a three-line Python diff that prints offsets. To dump the
*other* shadow bank on a Master, flip ACCCON's X bit (`&FE34` bit 2) from the guest before the
`save_memory` and put it back after - `save_memory` reads through the machine's own memory map.

---

## 4. Breakpoint-pair cycle timing

How long a routine takes, exactly, with nothing added to the build. Paradroid's
[raster-timing.md](https://github.com/kieranhj/paradroid-beeb/blob/main/docs/raster-timing.md)
("The instrument, since `DEBUG_TIME` stopped building") and its
[perf audit](https://github.com/kieranhj/paradroid-beeb/blob/main/docs/perf-audit-2026-08-31.md)
§1; Edge Grinder's Layer 2 measured its two IRQ handlers the same way.

1. Take the addresses of the `JSR` sites (or the handler entries) from the listing.
2. Get the game into a **repeatable state**. Poke inputs; do not hold keys. An injected keypress
   lands a pass earlier or later once code speed changes, and two runs then diverge for reasons
   unrelated to the change. Paradroid poked a speed (`dbgSpdX`/`dbgSpdY`) instead of holding a
   direction.
3. Set an execute breakpoint at the start of the routine and one at the return site. Run to the
   first; read the cycle counter; run to the second; read again; subtract.
4. **On jsbeeb-mcp 3.4.0 and later, `cycles_run` is the cycles actually executed**, and the
   registers reported at a breakpoint stop carry `elapsed_cycles`, so step 3's second call goes
   away. **On 3.3.0 and earlier, never read `cycles_run`** - it reported the number *requested*,
   not the number run - and take `elapsed_cycles` from `read_registers` instead. `elapsed_cycles`
   is a free-running exact total with no 16-bit wrap either way, so it is never wrong on any
   version, and it stays the safe default.
5. **On 3.3.0 and earlier, a run that starts with PC already on a breakpoint returns immediately
   with 0** (jsbeeb-mcp#26, fixed in 3.4.0). Where it applies, the sweep is: read, *clear the
   breakpoint that just fired*, run to the next. Set every site up front and walk them one per
   run; it costs two calls a site. On 3.4.0 the run continues from the stop, and a breakpoint hit
   but not yet reported comes back as `stopped_reason` `pending_breakpoint` with `cycles_run` 0.
6. **One site at a time** if you are patching stubs in rather than using breakpoints;
   instrumenting two reliably hung Paradroid's main loop.
7. Emulation is deterministic, so one sample is exact for that state - but **average about 128
   passes** for anything a sprite touches, because Paradroid's rotor phase cycles every 8 and a
   busy pass is not a typical one. Anchor the timeline on something that recurs (Paradroid: the
   fire-3 handler's `INC fieldCount`, where a window opens).

An older note said breakpoints only fire under `run_frames`; they do fire under `run_for_cycles`.
Both ports' notes carry the correction.

If a reading is wanted from *inside* the guest - to bracket a routine on real hardware, say -
Paradroid used a User VIA T1 bracket: `cycles = 2 * ((before - after) AND &FFFF) - 46`, the 46
being the bracket's own overhead. Edge Grinder's `src/timing.asm` uses the User VIA's T2 for its
frame meter; its three traps are in procedure 6.

```
set_breakpoint  address: <routine entry>
set_breakpoint  address: <return site>
run_for_cycles  cycles: 1000000        # stops at the first
read_registers                          # note elapsed_cycles
clear_breakpoint id: <entry bp>
run_for_cycles  cycles: 1000000        # stops at the second
read_registers                          # subtract
```

---

## 5. Zero-byte instrumentation stubs and histograms

When the question is not "how long" but "where against the raster does this phase end, over
many passes", and the build has no room for a debug flag. Paradroid's
[perf audit](https://github.com/kieranhj/paradroid-beeb/blob/main/docs/perf-audit-2026-08-31.md)
§1 and Appendix A.

1. Find a region of RAM the game never writes. Paradroid used the top half of the stack page,
   `&0130-&017E`, with counters at `&0100-&012F` - after **measuring** that `&0100-&017F` was
   untouched in a 40-second session (seed with `&A5`, play, read back; see procedure 10 for the
   seed-and-check pattern). The lift, transfer and briefing paths were *not* exercised in that
   measurement; the doc says so, which is why the harness must never ship.
2. Hand-assemble a stub per site: `JSR <the real routine>`, then `LDX <state byte> : INC
   counter,X`, then `RTS`. Paradroid's state byte was `ruptState`, which names the fire that has
   just happened - 2 means the beam is over the play area, so a draw phase ending in state 2
   overran its window. A fifth stub bucketed System VIA T1 (`&FE45`, shifted down three) to grade
   *how* late.
3. Re-point each `JSR` operand at its stub - a two-byte poke per site. Keep the original operands
   to restore.
4. Zero the counters, run 128 passes with the player *scrolling* (a stationary player gives the
   level draw nothing to do and it lands anywhere), read the counters back.
5. Read the histogram: every buffer phase should end in its window - in Paradroid's terms, bins
   1/2/3 at the end of each drawer should be zero.

**The trap: verify the stub bytes before you believe anything.** A hand-assembled branch two
bytes short executed `JSR &6001` from the middle of an instruction, wrecked two sessions and
mimicked a game hang - black screen, `BRK` loop in the MOS, field counter frozen - before it was
found. A lift ride was blamed for it and was innocent. Disassemble the stub region from the
emulator and read it back as code before the first run.

The 71 bytes Paradroid used are in Appendix A of the audit, with the warning that the addresses
are that build's. The `INC` for the "late" bucket makes a perfect trap breakpoint: it executes only
at the end of a late pass, so a breakpoint on it lands you inside the exact pass to autopsy.

```
write_memory    address: 0x0100, bytes: [0 x 48]
write_memory    address: 0x0140, bytes: [<stub bytes>]
disassemble     address: 0x0140, count: 32            # read it back first (count is instructions, max 200)
write_memory    address: <JSR operand>, bytes: [0x40, 0x01]
run_for_cycles  cycles: 10223616                     # 128 passes at 2 fields each
read_memory     address: 0x0100, length: 48
```

---

## 6. Frame-lock and drop check by counting

Whether the game is holding its rate, measured, because *it looks smooth* is not evidence: the
emulator runs at the host's ~60 Hz, not the Beeb's 50, so a 5:6 judder is baked in before the
code gets a say (Paradroid memory, "don't judge smoothness in emulator"; it sent a session chasing
a regression that measurement showed was a 31% improvement).

1. Find the loop-pass counter and the field counter (Paradroid: `gameTick`, `fieldCount`; Edge
   Grinder: `frame_count`, `field_count`).
2. Read both. Run **exactly 100 fields** - 3,993,600 cycles. Read both again.
3. The field counter should have advanced by exactly 100 (the IRQ is healthy under load). The pass
   counter should have advanced by 100 / `FRAME_LOCK` - 50 for a 25 Hz game. Fewer is dropped
   frames. Paradroid's table: 50/100 stationary, 50/100 scrolling, 50/100 on a nine-droid deck.
   Edge Grinder's Layer 2 confirmed "10 game frames in 20 fields" the same way.
4. Repeat in the scenarios that load the game: scrolling, a busy screen, firing. A single
   62-in-100 transient measured once after heavy single-stepping and never again is recorded in
   Paradroid's audit as "flagged, not concluded" - measurements taken with the debugger in the
   loop can perturb the thing measured.

The longer form is Paradroid's "128 passes take exactly 10,223,616 cycles". A cheaper in-guest
form is Edge Grinder's `tim_over` in
[`src/timing.asm`](https://github.com/kieranhj/edge-beeb/blob/master/src/timing.asm): field
count minus the field of the last flip at handover, `FRAME_LOCK` or more meaning the flip was
missed. That costs nothing and is the definitive per-frame answer.

If you build a frame meter on a VIA timer, three traps from
[performance.md](https://github.com/kieranhj/edge-beeb/blob/master/docs/performance.md) caught
Edge Grinder's before a single number was good: the timer's two bytes are read one after the
other and can roll between them (throw away any sample that comes out going backwards); a frame
longer than 65.5 ms wraps the counter outright, and deaths and mode changes all do it (one frame
measured 234 fields); and a phase *maximum* includes any interrupt that landed inside it, of which
there are six a frame, so read maxima as upper bounds and take typical cost from single frames.

```
read_memory     address: <gameTick>, length: 1
read_memory     address: <fieldCount>, length: 1
run_for_cycles  cycles: 3993600
read_memory     address: <gameTick>, length: 1
read_memory     address: <fieldCount>, length: 1
```

---

## 7. Sound capture against a reference stream

For a music player whose data is scattered, paged or converted: "it plays" is not the check. A
wrong address plays happily for thousands of frames before the stream runs off what it was given,
and the streams desynchronise into noise. Edge Grinder's
[`tools/verify_vgi.py`](https://github.com/kieranhj/edge-beeb/blob/master/tools/verify_vgi.py)
and [layer-7-music.md](https://github.com/kieranhj/edge-beeb/blob/master/docs/layer-7-music.md).

1. Build the **reference write stream** off-machine, from the same binaries the build `INCBIN`s
   and the same map it assembles - not from an intermediate file - so the placement itself is
   under test. `verify_vgi.py` lays the eleven register streams into a model of the Master's
   address space (bank 3 with HAZEL on top, ANDY, the two sideways tails) and decodes frame by
   frame exactly as the player would.
2. Start capturing SN76489 writes in the emulator, run ten or twenty fields, stop and save the
   log verbatim.
3. Search for the captured byte sequence inside the reference stream. **A unique match is the
   pass**: Edge Grinder's AKL check matched twelve fields at frame 427 and nowhere else in 17,446.
   Zero matches means a placement bug; several means the excerpt was too short to be diagnostic.
4. Run it after any change to the music files, the IRQ, or the memory layout the streams live in.
   Nothing else catches a misplacement.

The capture is also a diagnostic on its own. Edge Grinder's mute crackled on jsbeeb and on b2
(KC); the capture showed `0xd9` (channel 2, attenuation 9) followed 246 cycles later by `0xdf`
(attenuation 15), fifty times a second - the tune's own leading edges - and the fix followed from
the timestamps. The mute was then verified by capturing ten muted fields: forty writes, all four
channels at 15, no tone writes, plus `read_sound_state` showing volumes back the field after the
second press.

```
start_sound_capture
run_frames          count: 20
stop_sound_capture  max_entries: 2000       # paste the output into capture.txt
```

```
python tools/verify_vgi.py capture.txt
```

---

## 8. Measuring a hardware fact by probe

For any register, paging bit or wrap size you are about to depend on. The rule in both ports:
**do not write hardware code from recalled facts**; set the register, read the effect back,
record the readback verbatim, then build on it.

1. Write down the claim as a prediction: "with line 4 low and line 5 high the display wraps to
   `&3000`", "bit 7 of ROMSEL overlays 4K at `&8000`".
2. Choose the probe. **BASIC first** if the thing under test leaves BASIC standing - it is the
   fastest way to poke a register and print a byte. Edge Grinder's four display-wrap sizes and
   the NuLA grey (`?&FE23=&78 : ?&FE23=&88`) were measured from BASIC.
3. **Machine code when the thing under test is the ROM the interpreter lives in.** ANDY overlays
   `&8000`, and BASIC *is* the ROM at `&8000`: paging ANDY in from a BASIC statement removes the
   interpreter mid-statement and hangs. Edge Grinder poked a few bytes of 6502 into main RAM and
   ran them ([layer-7-music.md](https://github.com/kieranhj/edge-beeb/blob/master/docs/layer-7-music.md)
   "ANDY had to be measured"):

   ```
   &FE30 = 4     write &AA to &8000, &BB to &9000
   &FE30 = &84   write &55 to &8000, &CC to &9000
   &FE30 = &84   &8000 reads &55    &9000 reads &CC
   &FE30 = 4     &8000 reads &AA    &9000 reads &CC
   ```

   Which is the whole fact: bit 7 selects it, it is 4K only, `&9000` is the paged bank either way.
4. Read back and **record the readback verbatim** in the layer doc, with the date and the
   emulator. A fact whose evidence is "measured" without the numbers cannot be re-checked.
5. **"I cannot measure this" is itself a claim, and it wants testing.** Edge Grinder's decision 63
   shipped an unverified assumption about NuLA indexing because it believed jsbeeb had no NuLA to
   test against. It did (decision 67, measured 2026-09-05 three ways), the bug reached KC's real
   hardware first, and the process lesson is written into the decisions table: the assumption
   should have been tested before it was written down as untestable.
6. Then - because emulators disagree - see procedure 11.

```
type_input      text: "?&FE40=4:?&FE40=13"        # BASIC route
type_input      text: "PRINT ~?&3000"
run_until_prompt
# machine-code route
write_memory    address: 0x0A00, bytes: [<the probe>]
type_input      text: "CALL &A00"
read_memory     address: 0x0A80, length: 4        # the probe's own results
```

---

## 9. Measuring internal key numbers

Never recall a key number. Both ports read the keyboard straight from the System VIA, so the
internal (matrix) number is what the code carries, and the MOS documentation's tables are the
thing to check, not the source. Edge Grinder's
[layer-9h-keyredef.md](https://github.com/kieranhj/edge-beeb/blob/master/docs/layer-9h-keyredef.md).

1. In BASIC, `*FX229,1` first so ESCAPE can be measured rather than eaten.
2. Poll OSBYTE 121 scanning from key 16 in a loop, printing on every change:
   `A%=121:X%=16:Y%=0` then `PRINT USR(&FFF4)` and decode X from the result.
3. **Prove the scan form on a known key before trusting it.** Z returned 97, which the source had
   said since an earlier measurement; only then were the other thirty-four read.
4. Hold each key in the emulator and note the number.
5. **SHIFT and CTRL are below the scan's floor** - OSBYTE 121 will not report keys 0-2 - so
   measure them through `INKEY(-n)` and calibrate on a known key: SHIFT is INKEY -1, CTRL -2, Z -98,
   and Z's internal number is 97, so internal = the INKEY index less one. SHIFT 0, CTRL 1.
6. Cross-check against any numbers the project already carries. Eight of Edge Grinder's
   cross-checked exactly against the earlier session, which is what says the method was right
   rather than merely repeatable. Paradroid's `bmKeyChar` table agreed with all of them - the
   cross-check, not the source.

```
type_input       text: "*FX229,1"
type_input       text: "10 A%=121:X%=16:Y%=0:K%=(USR(&FFF4) AND &FF00) DIV 256:IF K%<>L% PRINT K%:L%=K%"
type_input       text: "20 GOTO 10"
type_input       text: "RUN"
key_down         key: "Z"
run_for_cycles   cycles: 400000, clear: false
key_up           key: "Z"
run_until_prompt                                  # or read the screen text
```

---

## 10. Reproducing uninitialised-RAM bugs

**jsbeeb powers up with all RAM zeroed**, so a bug caused by memory read before it is written -
`SKIP`ped BSS, reclaimed OS workspace, a flag assumed clear - never reproduces there and shows
up only on real hardware, usually as "first boot only" or "intermittent" (Paradroid memory,
confirmed 2026-08-28 on the white-briefing bug, `disrFlash` in `lowbss`).

1. When a symptom is reported that way, suspect uninitialised state first.
2. Hard reset to the BASIC prompt.
3. Poke the suspect byte, or the whole suspect region, with garbage - `&A5` is the seed both ports
   used, because it is neither 0 nor `&FF` and is unlikely to occur by accident.
4. **Soft reset with SHIFT held.** A soft reset does not clear RAM, so the seed survives into the
   game exactly as a real machine's leftovers would. A hard reset would zero it again.
5. Play to the symptom.

The same seed-and-check is how to prove a region is *free*: seed it, play through every path that
could touch it, read it back. Paradroid's stack-page measurement (procedure 5) is that recipe, and
its doc lists the paths that were not exercised, which is the honest form.

```
reset           hard: true
run_until_prompt
write_memory    address: <suspect>, bytes: [0xA5, 0xA5, ...]
reset           hard: false, autoboot: true
```

---

## 11. Cross-emulator check for display-bank and CRTC tricks

jsbeeb is the instrument for almost everything, and there are things it cannot see. Each of
these was found by a second emulator or by hardware:

- **What the video fetches below `&3000` with the shadow bit set.** jsbeeb displayed Edge
  Grinder's panel at `&2000` under both shadow states; b-em showed garbage on alternate frames
  (KC, 2026-09-02). Decision 17 moved the panel to `&3000` in both banks and the rule became
  *nothing displayed may live below `&3000`*. Real hardware is untested either way.
- **A misplaced field.** Paradroid's handover into the rupture produced one short field and a
  vertical roll; jsbeeb reported 39,93x-cycle fields throughout and showed no fault. KC caught it
  on b2 and photographed it
  ([raster-timing.md](https://github.com/kieranhj/paradroid-beeb/blob/main/docs/raster-timing.md)
  "Round three"). The frame-length instrument measures length, not phase; the doc says "jsbeeb
  cannot confirm this one - b2 is the instrument for it".
- **The mid-frame bank flip** (`hardware-facts.md`) is measured in jsbeeb only; Edge Grinder's
  rules say so explicitly, and that decision 17 is why it matters.
- **Perceived smoothness** - procedure 6: no emulator can judge it.

The procedure:

1. Anything that switches the display bank, changes CRTC shape mid-frame, or displays memory
   the MOS would not, gets a second opinion in **b2 or beebjit** before it is called done, and a
   note in the layer doc saying which emulators have seen it. (Both ports' `build.ps1 -Run`
   launched b-em; b-em is no longer used.) From the tools' own help:

   ```
   beebjit -0 build\game.ssd -autoboot                 # -master for a Master 128, -swram 4 per bank
   b2 -0 build\game.ssd -b                             # -c CONFIG for a saved machine configuration
   ```
2. For a *phase* question, use **b2** and look at the window. b2's debug build carries an HTTP
   API on port 48075 (documented in
   [`doc/Debug-version.md`](https://github.com/tom-seddon/b2/blob/master/doc/Debug-version.md)
   in its tree): `peek/WIN/BEGIN/END` returns memory as binary, with a suffix selecting main,
   shadow, a paged ROM, ANDY or HAZEL, and `paste/WIN` types BASIC in. Paradroid tried it on
   2026-08-21: `peek` was byte-identical to the file on disc and the machine ticked between
   peeks; `poke` to an I/O address had no effect, which the docs say to expect - poke writes
   emulated memory, not the bus - so the supported route for a register write is `paste` the
   BASIC and let the 6502 do it. **There is no screenshot endpoint**; the display half needs eyes
   on the window. That is enough, the buffer being the half these ports trust.

   ```
   curl --data-binary '?&FE22=&27
   ' http://localhost:48075/paste/b2
   curl -o buf.bin "http://localhost:48075/peek/b2/0x5800/+0x2800?s=m"
   ```

3. Real hardware last, and record it: Paradroid's first run on a real Master is dated in
   [layer-13-compatibility.md](https://github.com/kieranhj/paradroid-beeb/blob/main/docs/layer-13-compatibility.md),
   with the list of machines still untested.

A related MCP quirk while reading memory in play: `read_memory` at `&8000` and above returns
whatever bank is paged **at that instant**, and a sprite engine pages its own banks in and out
mid-frame, so a data-bank variable reads plausible nonsense between frames. Break somewhere the
resting bank is up (the top of the main loop), or verify against main RAM or the panel instead.

---

## 12. Byte-identical build check

For a change that should not alter the disc at all - a source split, a build-script change, a
reorder of includes. Edge Grinder's
[layer-0-toolchain.md](https://github.com/kieranhj/edge-beeb/blob/master/docs/layer-0-toolchain.md)
§3, done for the split of a 1,572-line file into six.

1. Build the **old** tree into a baseline SSD and keep it.
2. Make the change; build again.
3. `cmp` the two images. Identical is the pass and the end.
4. If they differ only where they *should* - Edge Grinder's `!BOOT` carries the assembly time
   and a DEV stamp, so the disc always differs there - extract the files that must not have
   changed from both catalogues and compare those. The comparison is per file, not per image.

```bash
cmp build-old/EDGE.SSD build/EDGE.SSD
python - <<'EOF'
# extract 'Edge' and 'BANK0' from each catalogue and compare
EOF
```

Neither repo ships the extraction as a tool; both did it inline. Edge Grinder's later layers use
the same check on the *data* side - "every existing output is byte for byte untouched" caught a
28-byte move in every sprite bank when two flash tables were put in the other order (decision 63).

---

## 13. Listing-stream diff for mechanical changes

For a change meant to be purely mechanical *but which moves addresses* - a width change, a data
removal, a relocation - where the images legitimately differ. Faster than the oracle and, for this
class of change, stronger. Paradroid's
[layer-5-blitter.md](https://github.com/kieranhj/paradroid-beeb/blob/main/docs/layer-5-blitter.md)
and [layer-15-endgame.md](https://github.com/kieranhj/paradroid-beeb/blob/main/docs/layer-15-endgame.md).

1. Keep the `-v` listing of the build before the change.
2. Build after the change; keep that listing.
3. Reduce each listing to one entry per emitted instruction - the opcode and its operand length,
   never the operand's value, so that code which merely moved compares equal.
4. Diff the two streams. Identical (7,753 instructions in Paradroid's blitter pass; 22,954 in the
   RAM pass) proves no instruction was added, removed or reordered, so every difference in the
   image is a width change or data. The emulator run afterwards then only confirms that the new
   addresses do not collide.

**The reducer is checked in now**, which it never was in either port - `py/listing.py`:

```bash
python -m beeb_port_kit.listing stream build-old/game.lst > old.txt
python -m beeb_port_kit.listing stream build/game.lst     > new.txt
diff old.txt new.txt && echo "stream identical, $(wc -l < new.txt) entries"
```

What it cannot validate, measured on the kit's own template (2026-09-07): **an operand's value is
invisible to it.** A build against itself gives 0 differences, one inserted `NOP` gives exactly 1,
and changing `SCROLL_STEP` from 8 to 4 gives **0** - the constant changed, the shape did not. So
compare the images byte for byte first (procedure 12), and reach for the stream only when the
addresses were meant to move; read a clean diff as "the same instructions in the same order",
not as "the same program". It also cannot validate a change that intentionally alters
instructions (Paradroid's SCANSTEP tail folding is called out as "the mechanical-diff check
cannot validate it - use the oracle").

---

## 14. A/B differential at equal game state

For a performance change: prove the new build draws the same bytes as the old one, and measure
the difference in cost, without either comparison being fooled by the game being in a different
place. Edge Grinder's
[performance.md](https://github.com/kieranhj/edge-beeb/blob/master/docs/performance.md) §1 and
Paradroid's headless differential (memory note; the harness ran from a node script patterned on
jsbeeb's `src/app-bench.js`).

1. Boot both builds, same disc protocol, same key script or poked inputs. **A snapshot cannot
   do this part for you**: it holds the code as well as the state, so an old build's state
   restored into a new build's machine restores the old build with it. Snapshots are for
   repeating a measurement *within* one arm - take one at the sampling point and every retry
   starts from the same instant and the same cycle count, which is what makes step 4's controls
   cheap enough to actually run.
2. **Step to an equal game state, not an equal frame number.** The faster build is further
   through the world by the time the sample is taken: Edge Grinder's `scroll_prewind` made the
   init frame shorter (190 fields against 197) and the game was four frames ahead. Step both to
   the same `char_col`/`tile_total` (Edge) or pin the deck and random seeds (Paradroid: boot
   duration seeded the starting deck from a free-running VIA counter, so *any* change to code size
   started the game on a different deck and 3,600 of 10,240 bytes differed for no reason).
3. Dump the play buffer and the collision map from both; diff. Byte-identical is the pass.
4. **Run the same-binary controls or the numbers cannot be read.** Identical build against itself
   must give 0 bytes (proves the harness is deterministic and sensitive). A few-hundred-cycle
   sampling skew against the same binary gives tens of transient frame differences and 0 final
   difference - that is mid-blit sampling, not a defect, and a faster build necessarily shows that
   second signature.
5. For the *cost* half, compare single frames, not phase maxima. A maximum lands on whichever
   frame caught an interrupt; comparing maxima showed -214 cycles on a change worth far more.
   Zero the meter's slots, run four fields, read single frames.

Paradroid's headless harness needed a real `Video` object - `fake6502`'s default fake never
raises VSync and a rupture-driven loop stalls on it - and a boot of `keyDown(16)` plus
`setReset(true)`/`execute`/`setReset(false)`, because the key alone lands at the BASIC prompt.
The script itself is not in the repo; the memory note is what survives.

```
# both sessions, after boot and the same input script
read_memory     address: <char_col>, length: 2          # step until equal in both
save_memory     address: 0x4000, length: 16384, path: ".../a-play.bin"
save_memory     address: 0x04A0, length: 800,   path: ".../a-coll.bin"
```

---

## 15. Off-emulator oracles: never check a thing against itself

The rule behind every procedure above, and the one to apply to anything new: **name the oracle
for every number**, and make sure it is not the code under test wearing a different hat. Edge
Grinder's Arkos player harness
([`tools/akl/README.md`](https://github.com/kieranhj/edge-beeb/blob/master/tools/akl/README.md))
is the worked example, and its own heading is "nothing here is checked against itself":

| stage | checked against | what it catches |
|---|---|---|
| `akl_reference.py`, a Python transcription of the tracker's player | `edgea.ym`, the AY register log **Arkos's own full player** produces from the same song | a misunderstanding of the format |
| `src/aklplayer.asm`, the 6502 | the Python, frame for frame, over all 17,446 frames | a 6502 bug |
| the running game | the simulation, by capturing SN76489 writes in jsbeeb and finding where they match | a wiring, paging or IRQ bug |

Each stage's oracle is one step *further from* the thing being built, and the last one is
procedure 7. The known baseline is written down too - eleven channel-2 periods off by one is
Arkos's documented behaviour, not a defect - so a regression is anything else.

The pattern recurs wherever a port converts data:

- Paradroid's [`tools/verify_bbc.py`](https://github.com/kieranhj/paradroid-beeb/blob/main/tools/verify_bbc.py)
  re-reads the generated BeebASM sources, decodes them **back** to their C64 representation and
  diffs against the original listing - a round trip, so an emission bug cannot cancel a conversion
  bug. The same file diffs an emulator dump of a tile map against a fresh RLE decode.
- Paradroid's [`tools/verify_annotation.py`](https://github.com/kieranhj/paradroid-beeb/blob/main/tools/verify_annotation.py)
  exists because the annotated copy of the specification silently returned 76 bytes of a 256-byte
  table; a data table that returns a fraction of itself produces a port faithful to the part that
  survived. It compares the annotated file against the raw listing block by block.
- Edge Grinder's [`tools/verify_compiled.py`](https://github.com/kieranhj/edge-beeb/blob/master/tools/verify_compiled.py)
  runs the compiled sprite bodies on a simulator of exactly the sixteen opcodes the compiler
  emits, over pseudo-random background, and checks draw, save and restore against a model built
  from the *interpreted* engine's own data and pointer walk - so a wrong box or a bad wrap tail
  fails, not just a wrong pixel.
- Edge Grinder's NuLA encoder reproduces a third party's default palette table byte for byte;
  its dither pairs reproduce a reference PNG cell for cell. Neither proves the hardware, which is
  procedure 8's job; both prove the tool.

The checklist for a new check:

1. Say what the number is being compared against, in the doc, next to the number.
2. Ask whether that reference was produced by the code under test or by something derived from
   it. If yes, find one that was not: the original machine's output, a different implementation,
   a round trip back to the source format.
3. Write down the known, accepted differences (the baseline) so the next run can tell a
   regression from a known quirk.
4. Put the check in a tool with a one-line invocation and a header saying what it proves. Both
   ports' `tools/verify_*.py` headers are the model.

---

## Gaps

Recorded so the next port does not assume they are filled:

- Edge Grinder has no redraw oracle (procedure 3). Its model oracles cover two static screens.
- Neither PORT checks in the listing-stream reducer (procedure 13) or the catalogue extractor
  (procedure 12); both were done inline. The kit ships the reducer now (`py/listing.py`,
  2026-09-07); the catalogue extractor is still inline.
- Paradroid's headless A/B script (procedure 14) survives only as a memory note.
- The mid-frame bank flip, the 8K-wrap ring and the display-below-`&3000` rule are measured on
  one or two emulators and on no hardware (procedure 11).
- Procedure 9's BASIC loop is reconstructed from the doc's description of the method, not
  copied from a saved program; prove it on a known key first, as the doc says.
