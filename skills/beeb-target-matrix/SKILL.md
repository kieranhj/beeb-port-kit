---
name: beeb-target-matrix
description: Boot a BBC Micro port's disc on every machine configuration jsbeeb can emulate that the port claims to support - Model B with each Acorn DFS, Master, both second processors, *SHADOW, *CONFIGURE TV, sideways RAM hidden or taken by a ROM image - one fresh machine each, and check each one plays, not just draws. Then list what still needs b2, b-em, MAME or real hardware. Use before a release, after changing the boot or loader, or when a tester reports "it doesn't work on my machine".
---

# Target matrix: every configuration jsbeeb can run

`beeb-smoke-test` asks whether the build boots on the target model. This skill asks the
same question on every configuration the port has **decided** to support: the rows it
recorded from the kit's `docs/target-portability.md`. Each run takes about five minutes. On
2026-09-11 it found that the kit template showed a black screen on both second processors and
the wrong picture under `*SHADOW`, after weeks of passing its smoke test.

**Which rows:** the port's `docs/decisions.md` (one row per configuration; see
`docs/target-portability.md` "Recording it"). No rows means that decision comes first.
**Image:** the shipping image, as for `beeb-smoke-test`, and for each fix a **before** image
kept aside, so a pass can be shown to be a fix rather than a test that can't fail
**"Plays" means all three:** the picture is right; the frame counters are moving (read them
twice, a few frames apart; addresses from `tools/listing.py symbols build/<NAME>.symbols.json`); and whatever the boot
leaves behind is there (`&0D00` = `&40` after `claim_nmi`, `&B0-&CF` still what you seeded it with after `release_fs`, the handover at `&0A00` after the
sideways RAM probe)

## Steps

1. **Build, and keep the previous image.** Copy the last shipped (or last committed) image
   to a scratch folder before rebuilding. A configuration that fails on the old image and
   passes on the new one is a measured fix. One that passes on both proves nothing about the
   change: the template's `*CONFIGURE TV` test was like that, and the notes say so.

2. **One fresh machine per configuration.** State carries over between tests: `*SHADOW`,
   CMOS settings, poked tables, a held key. `create_machine` for each, `destroy_machine`
   after. Run them in parallel: they don't depend on each other.

3. **Set up the configuration, then boot.** The order matters for each:

   | Configuration | Set up | Then |
   |---|---|---|
   | B, DFS 1.20 / 0.90 / 1770 | `create_machine model: "B-DFS1.2"` (or `"B-DFS0.9"`, `"B1770"`) | `boot_disc` |
   | Master 128 | `create_machine model: "Master"` | `boot_disc` |
   | Second processor | `create_machine model: ..., tube: true` | `boot_disc` |
   | `*SHADOW` | `type_input "*SHADOW"`, then `load_disc` (not `boot_disc`) | `reset hard: false, autoboot: true`. A hard reset would clear it |
   | `*CONFIGURE TV 252,0` (or any CMOS setting) | `type_input "*CONFIGURE TV 252,0"` | `boot_disc`: CMOS survives its hard reset (measured 2026-09-11: `*STATUS TV` read `252,0` after `reset hard: true`) |
   | Sideways RAM hidden (short machine) | at the prompt, `write_memory` a non-zero byte into `&02A1 + bank` for each bank to hide, **and** `60 00 00 82` at `&8003` in that bank | `type_input "*RUN <probe>"`, or boot the rest by hand |
   | A ROM image in sideways RAM (ZMMFS stand-in) | the same for one bank of four | as above |

   **The fake ROM needs `RTS` at `&8003`.** Marking a bank in `&02A1` makes the MOS call it
   with every service call. A bank of zeros BRKs there, gets offered its own BRK and loops at
   `&8003` before your code runs (kit, 2026-09-11). Poke after the machine reaches the
   prompt: a reset rebuilds the table.

4. **Give it time.** `run_frames count: 400` after a boot. jsbeeb's 1770 DFS (every Master)
   takes more than 50 frames to load even a small file. A CPU in DFS's NMI code (`&0D00` up)
   is loading, not hung. **After `type_input`, read the screen with `run_frames`, not
   `run_until_prompt`**: the command may already have run and returned during the typing, and
   `run_until_prompt` then waits for a prompt that never comes.

5. **Check "plays", all three parts.** `screenshot`, then `read_memory` the counters, then
   `run_frames count: 50` and read them again. Then read what the boot should have left behind.
   On a Master, `read_memory` also reports ACCCON: `&18` when the main screen is displayed,
   `&1B` when a `*SHADOW` machine's display went to shadow RAM. **And `read_sound_state`**:
   every channel should read `vol=15` (silent) unless the game is making a sound. The kit's `*RUN`
   release boot left the BREAK beep sounding on a Model B, at 523 Hz and `vol=2`, with the picture
   perfect and the counters running. Only the sound read caught it (2026-09-11).

6. **A failure: read where it stopped before guessing.** `read_registers`, then `disassemble`
   around the PC. The kit's second-processor failure was a PC in the Tube host code at `&0700`,
   just after writes to `&FE4B`-`&FE4E`: a load sent across the Tube. The fix was the
   loader's OSFILE block, not the catalogue that had already been fixed. A PC at `&8003` is the
   fake-ROM loop above. A PC at the MOS IRQ entry with the counters at zero is the game never
   starting.

7. **List what jsbeeb can't run**, from the port's rows: other DFSs and MMFS (b2), the B+ and
   the Compact (b-em presets 9 and 13), expansion boards (MAME, which can't run a game), real
   hardware. Name them in the report. A row nobody tested says "untested", not "supported".

8. **Report as a table**: configuration, before, after, and the numbers (counters, ACCCON,
   `&0D00`, handover) that make "plays" a measurement. The kit's own is in
   `docs/hardware-facts.md` "Target configurations". Put the table in the commit body.
