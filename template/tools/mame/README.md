# MAME harnesses

Lua templates for using MAME as a measuring instrument on a game you have no source for.
Distilled from the 1942 arcade port (`1942-beeb/tools/mame/`, MAME 0.177, 2026-09-07 to 10-14),
where every rule the port shipped was a Python model of a ROM routine scored against a capture
these harnesses took. The method is [`docs/arcade-porting.md`](../../../docs/arcade-porting.md);
the Python half is `py/beeb_port_kit/mame/`.

**Everything is an environment variable, and every address and byte string is HEX.** Nothing
here knows a game's addresses; lines marked `GAME:` are 1942's values, as examples.
**Run them through the runner**, never by hand:

```
python -m beeb_port_kit.mame.runner --mame <MAME dir> --game <machine> \
    --script tools/mame/capture_ram.lua --out D:/scratch/cap --frames 3000 \
    --expect ram.bin,schema.txt --env CAPTURE_SPEC="f:frame;spr:bytes@cc00-cc7f"
```

It refuses to start beside another MAME (a second instance of one machine blocks for ever), makes
`--out` absolute (MAME's working directory is its own), kills a run that does not finish, checks
the exit code, fails if an expected file is absent **or older than the run**, reports
`lua_error.txt`, and prints the DIP switches the `cfg/<game>.cfg` overrides. **Keep captures
outside the repository** (1942's whole game was 92 MB).

| File | What it does | From 1942-beeb |
|---|---|---|
| `_compat.lua` | Loaded by all the others. Old (0.177) and new Lua API shims; open-the-output-first and catch-every-error (a Lua error otherwise leaves MAME running silently for ever); `C.patch(region, addr, expect, new)`, which **asserts the original bytes** and keeps a running XOR and sum delta; the record writer for `records.py`'s spec; one frame dispatcher so templates compose (`MAME_PLUGINS`) | every harness |
| `capture_ram.lua` | Per-frame RAM records laid out by `CAPTURE_SPEC`, with `schema.txt` beside them for `records.load_capture` | `fullgame.lua`, `enemy.lua`, `map.lua` |
| `hold_byte.lua` | Hold one byte until the game has taken it - the cheapest way to any state (1942: hold the pending stage, let the attract demo play it) | `stage.lua` |
| `force_input.lua` | Patch the input read in ROM (RAM is overwritten before it is read), or drive ioport fields on a schedule | `upclamp.lua`, `enemy.lua`, `orient.lua` |
| `invincible.lua` | Redirect the player-hit tests into the game's own "already hit" path; the ROM-checksum checklist; `TRACE_FROM` logs PC/SP per frame to find a halt | `fullgame.lua` |
| `autopilot.lua` | SKELETON: rewrite the input read every frame from where the recording ends, so a capture reaches content no human run did | `fullgame.lua` |
| `find_reg.lua` | Find a register by cause: write every value to every address, see which changes a window | `bankreg.lua` |
| `subcpu_ram.lua` | A sub-CPU's RAM every frame, with commands injected into the main CPU's own request ring - the oracle for a `z80sub.py` model | `snd_ram.lua` |
| `orient.lua` | The RAM a screen is built from plus a snapshot of the same frame, for `orient.score_rotations` | `orient.lua` |
| `dips.lua` | Every input port and field, its live setting against the driver's default, and the addresses the game reads them at | `dips.lua`, `dipnames.lua` |
| `stop_at.lua` | End a session after `CAPTURE_FRAMES` - what a debugger session that `go`es needs | new |
| `debugscript.txt` | A sample for `-debug -debugscript`: `dasm`, `trace` + `wpset`/`bpset` with `tracelog` actions | `boss_wp.txt`, `snd_dasm.cmd` |

## Composing

```
MAME_PLUGINS=invincible,force_input   ...   capture_ram.lua
```

loads the named templates into the running one. Each frame, the "drive" handlers (hold, force,
patch, autopilot) run before the "record" handlers (capture, sub-CPU, dips), so a record sees the
frame the drivers made.

## Measured on MAME 0.177 with 1942, 2026-10-25 (`py/tests/test_mame_smoke.py`, opt-in)

- `capture_ram` + `hold_byte` (hold `$E106` = 4, taken when `$E103` reads 4): 900 records,
  `($E103)` becomes 4 at **frame 638**, exactly 1942-beeb `arcade-facts.md` §28's figure.
- `dips` with `DIPS_ADDRS=c000-c004`: `$C003` = `37`, `$C004` = `DF`, Lives and Difficulty
  flagged "NOT THE DRIVER'S DEFAULT" - §34's Easy and five lives.
- `find_reg` over `$C800-$C8FF`, watching one byte every `$400` of `$8000-$BFFF`: `$C806` and
  nothing else; value 1 reads `FF` above `$A000`, value 3 all `FF` - §7's table.
- `invincible` with 1942's three patches and `force_input` forcing UP from frame 700 over
  `kieran.inp`: lives 5 and `($E099)` 0 on all 3,000 frames. `patches.txt` shows the two hit
  patches **cancel each other's XOR and sum** (delta `00`/`00`), which is why 1942's first
  invincible run got past the ROM checksum and its autopilot did not.
- `force_input` fields `Coin 1@60-80;1 Player Start@150-170`: `($E000)` bit 7 (in game) clear at
  frame 50, set at 400.
- `subcpu_ram` on the clone `1942a`, `INJECT=05@100` into the ring at `($E222)`: the sound CPU's
  IRQ counter steps **4 a frame on 349 of 349** frames; the latch reads `05` for one frame.
- `orient` under `-video none`: the snapshot is written (to MAME's own `snap/1942/`).
- A Lua error (`CAPTURE_SPEC` unset) returns in 0.9 s as a `MameError` naming the line; a patch
  whose expected bytes are wrong is refused with the byte that differed.
- The debugger: `go` never returns to the script, so `quit` after it hangs to the timeout;
  0.177 has no `logfile`; `trace FILE,0` with `tracelog` actions works, and logs every
  instruction too (1.5 MB in 300 frames). Pair a watching debugscript with `stop_at.lua`.
- **MAME rewrites `cfg/<game>.cfg` on every exit** (1942's coin counter moved 136 -> 139 over
  these runs; the DIP overrides survived). It is live state, not a file you set once.
