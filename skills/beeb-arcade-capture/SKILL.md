---
name: beeb-arcade-capture
description: Capture an arcade original (or any emulated binary with no source) out of MAME as ground truth - the machine manifest, the live DIP switches, a human recording, per-frame RAM records, the measured screen rotation, and captures driven into states no recording reaches (held state bytes, forced input, invincibility, an autopilot), with the ROM-checksum trap checked. Use when starting a port from a ROM set, when a model or a ROM read needs something to be scored against, when a state byte never changes in the recording, or when a MAME run hangs, writes nothing, or disagrees with itself.
---

# Capturing the original out of MAME

With no source, the running machine is the specification: every rule the port ships is scored
against a capture (`docs/arcade-porting.md`). 1942 guessed its map format wrong twice from the ROM
before capturing tilemap RAM, and wrote the player's death from the disassembly, wrongly, because
its recording never died.

**Tools:** `py/beeb_port_kit/mame/` (`runner`, `records`, `romset`, `orient`); `template/tools/mame/*.lua`
**Every address and byte string is HEX.** Captures go OUTSIDE the repository.
**Pass:** every expected file fresh, the reader parses the whole file, the state you meant to reach is in it

## Steps

1. **Read the manifest, do not recall it.**
   `mame -listxml <game> > game.xml`, then `romset.parse_listxml(text, game)`: CPUs and clocks,
   sound chips, the display's `rotate`, every DIP switch, every ROM with its CRC.
   `romset.RomSet([zip, parent_zip], machine.roms)` must load without complaint. (1942's decision 1
   reasoned about a "3 MHz Z80" that was the audio CPU.)

2. **Find out what cabinet you are capturing.**
   `python -m beeb_port_kit.mame.runner --game G --cfg` lists what `cfg/G.cfg` overrides; MAME
   applies it to `-playback` too and rewrites it on every exit. Then `dips.lua` with `DIPS_ADDRS`
   set to where the game reads its DIP ports. 1942's captures were all EASY with five lives for
   weeks, by a hand edit nobody remembered. Record the setting as a decision; mark every dependent
   constant `DIPSWITCH:`.

3. **Record a human playthrough** (`--record name.inp`), as far into the game as a person can get.
   Write down its length in frames: MAME runs on after the input ends, and nothing past it is play
   (1942's "stage 2" was stage 1 resumed, `BUGS.md` #13). Replay is deterministic until the cfg's
   DIP switches change.

4. **Capture per-frame RAM** with `capture_ram.lua` and a `CAPTURE_SPEC` naming the globals, the
   sprite RAM and the object table (`slots@BASE,N,STRIDE,LEN`). Read it with
   `records.load_capture(out, "ram.bin")` - the spec rides in `schema.txt`, so writer and reader
   cannot disagree. Always through the runner, with `--expect` naming every file: it guards the
   second instance, the relative path, the stale file, the silent Lua error and the hang.

5. **Measure the rotation** if the cabinet is vertical: `orient.lua` dumps the RAM a screen is
   built from plus a snapshot of the same frame (MAME writes it to its own `snap/G/`); rebuild that
   frame in raw space and run `orient.score_rotations` against the snapshot. Choose an ASYMMETRIC
   frame - it refuses a near-tie. 1942: ROT270 96.3%, the rest 46-48%. Then name the two spaces in
   the project's rules file.

6. **List every state byte that is constant in the recording.** Each is unmeasured
   (`BUGS.md` #12). Drive it:
   - a pending-state byte the init copies: `MAME_PLUGINS=hold_byte`, `HOLD_ADDR`, `HOLD_VALUE`,
     `HOLD_TAKEN_ADDR`/`VALUE` - held only until taken. Try the ATTRACT DEMO first: 1942's plays
     any held stage with no coin and cannot lose a life;
   - input the recording never gave: `force_input` - patch the input read in ROM (`FORCE_PATCH`,
     `ADDR:EXPECT:NEW` with `{v}`), since a RAM poke is overwritten before it is read; or
     `FORCE_FIELDS` for coins and starts;
   - a long run that must not end: `invincible` (redirect the hit tests into the game's own
     "already hit" path - never poke the lives) and `autopilot` from where the recording ends.
   Check it held (lives never fall; the state you wanted appears).

7. **Watch for the ROM checksum.** Read `patches.txt`: a non-zero XOR or sum delta, or a game that
   freezes minutes in, means a checksum. Rerun with `TRACE_FROM` before the freeze; a PC parked on
   a `halt` names it; patch the compare's branch (1942: `$7137 jr z` -> `jr`). The per-frame
   autopilot byte changes the sum every frame.

8. **Find hardware registers by cause** when the manifest does not say: `find_reg.lua` writes every
   value to every candidate address and reports which changed a watched window (1942: `$C806`, the
   bank select, and nothing else).

9. **Sub-CPUs**: `subcpu_ram.lua` on a clone that shares the sub-CPU ROM (confirm the CRC), with
   commands injected into the main CPU's own request ring. Its oracle use is `beeb-rom-model-probe`.

10. **Debugger sessions** (`--debug cmds.txt`, sample in `template/tools/mame/debugscript.txt`):
    `dasm` then `quit` to read code; to watch, `trace FILE,0` + `wpset ...,{tracelog ...; g}` +
    `go`, with `--script stop_at.lua --frames N` to end it - `go` never returns, 0.177 has no
    `logfile`, and `-debugger none` hangs.

11. **Leave nothing running** (`tasklist`/`pgrep`), move any snapshot out of MAME's `snap/`, and
    record in the project's arcade-facts file what each capture is, its frame count, where it
    lives, and what it reaches.
