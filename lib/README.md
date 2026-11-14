# lib/ — the 6502 half of the kit

Eight Baron includes (plain 6502, NMOS) that were identical or near-identical between the
[Paradroid](https://github.com/kieranhj/paradroid-beeb) and
[Edge Grinder](https://github.com/kieranhj/edge-beeb) ports, made generic once, and five more
from the third port, [1942](https://github.com/kieranhj/1942-beeb), a Master-only game that
kept reading the disc after its boot: its own 1770 driver (four files) and BREAK-clears-RAM;
then from the fourth, [Stryker's Run](https://github.com/kieranhj/strykers-run) (an original
rebuilt from its disassembly, optimised for the Master, then taken down to a Model B), the
65SC12-to-NMOS macros and a 50 Hz sound effect driver. MIT, Kieran Connell; the 1770 driver is derived from scarybeasts' quicdisc, relicensed for
this use (its header has the wording).

## The fork-and-hack rule

**Copy the file into your project and edit it there. Do not `INCLUDE` it from this repository.**
A third port will want to change something in every one of these — the zero page the depacker
borrows, what the IRQ hooks do, which keys are read, where streams stage — and a shared file that
three games depend on cannot be hacked for one of them. Every file therefore carries a
provenance header: what it is, which port file(s) it came from (with links), what was
**measured** about it and when, and what the includer has to define. **Keep the header when you
fork the file**, and add a line to it saying what you changed. The header is the only thing
that tells the next reader which facts were measured on hardware and which they are about to
break.

Nothing in here is believed without a measurement. Where a symbol is a name from a reference
manual that neither port exercised, the header says so (`beeb.h.6502`'s five unused ACCCON bits).

These files are **[Baron](https://github.com/waitingforvsync/baron)** syntax, 0.4.1 or later; the
kit runs 0.6.0 (2026-10-21) (`.6502`, sections instead of `ORG`/`SAVE`, Baron's own `ASSERT`).
**A fork of `beeb.h.6502` from before 2026-10-11 defines `MACRO ASSERT`, which 0.4.1 refuses
as a reserved name**: delete the macro and every assertion reads as before. The two
shipping ports are BeebASM projects and their own copies are unaffected; a port that wants
BeebASM reverses the table in `../docs/toolchain-baron.md`, which is six lines' work, or takes
the files from this repository's history (commit `5355d03`).

The conversion changed no emitted byte: the test image below came out **byte-identical**
(1,509 bytes) under both assemblers, and the template built on these files is byte-identical
to its BeebASM build.

## The files

| File | What it is | The includer defines |
|---|---|---|
| `beeb.h.6502` | The hardware constants both mains carried: CRTC, Video ULA and NuLA, both VIAs by register, ROMSEL/ROMSHAD/ACCCON with the Master's bit names, IRQ1V, the `KBD_*` latch values, `SL = 64`, the MOS entry points, and the `CRTC r, v` macro. Edge's names; Paradroid's noted beside them | nothing — include it first |
| `zx02depack.6502` | **What a new port uses.** Daniel Serpell's ZX02 (default mode) as the macro `ZX02_DEPACKER`, 131 bytes, ~54 cycles/byte. A BeebASM transcription of his `zx02-optim.asm`, verified by stepping it in py65 over 43 real files from both ports and comparing the output with the source, byte for byte, and end to end by booting the template's disc in jsbeeb. Against `zx0depack.6502`: **half the code, 2.14x the speed, +0.11% on the packed size** (the header has the per-file numbers). Header carries the calling convention, the **in-place rule** and the **beebasm pass-1 sizing trap** | five zero-page symbols `zxsrc zxdst zxofs zxbit zxwrk` (8 bytes; no `zxlen` - the length lives in X), declared *before* the first file that uses one; then `.zx_unpack` + `ZX02_DEPACKER` |
| `zx0depack.6502` | Einar Saukas's ZX0 (default mode) as the macro `ZX0_DEPACKER`, 257 bytes. Written from the compressor's source, verified byte for byte in both ports. **Kept for the two shipping discs, which are ZX0 discs**; a new port takes `zx02depack.6502` instead. The formats are not interchangeable: one depacker, one compressor, and nothing checks they agree but you | six zero-page symbols `zxsrc zxdst zxofs zxlen zxbit zxwrk`, declared *before* the first file that uses one; then `.zx0_unpack` + `ZX0_DEPACKER` |
| `irq.6502` | The IRQ1V owner: `irq_handler` (System VIA T1 and CA1/VSync, nothing passed to the MOS), `install_irq` (which silences the sound chip, since the MOS's driver dies with its interrupt: `sfx50.6502` replaces it for effects), and `uninstall_irq` under `IF IRQ_UNINSTALL` (with the state saves that make it possible). Header: load before install, and if you must load after it, mask or chain (a swallowing handler hangs a Master); flush the MOS sound workspace (`OSBYTE &0F`) *before* uninstall; a hook that pages a sideways bank saves and restores ROMSHAD itself | `irq_timer_hook`, `irq_vsync_hook` (routines), `IRQ_UNINSTALL` = 0/1 |
| `keydown.6502` | One key read straight off the keyboard matrix, 69 cycles against OSBYTE's 243 (measured). Two entries on one body: `keydown_int` (internal key number in, N out — Edge) and `keydown_inkey` (negative INKEY byte in, Z out — Paradroid). Header: the latch line 3 / DDRA `&7F` / `&FE4F` sequence, the phantom sixth key, and that key numbers are measured (OSBYTE 121; INKEY for SHIFT and CTRL). Edge's `read_joystick` as a commented example of packing five keys into the C64's `$dc00` byte | nothing beyond `beeb.h.6502` |
| `loader.6502` | Edge's OSFILE loader: `load_stream` (filename in A/Y, staging page in X, leaves `zxsrc`), `unpack_to` (X:A), `load_bank` (filename + ROMSEL value, unpacks into the paged bank), and under `IF MASTER` `load_hazel` (into `HAZEL_FREE`, `&C300-&DEFF`, the window OSFILE leaves alone, so loads may follow it; measured on jsbeeb's Master 2026-09-11) and `unpack_andy` (fixed 2026-09-11, 1942's BUGS.md #21; the MOS writes three of ANDY's pages — `&80`, `&8800-&882F`, `&8F` — so `../docs/hardware-facts.md` "ANDY" says when all 4K is usable), then `release_fs` (OSBYTE 140: the filing system detaches and stands its NMI hardware down - **hexwab's contract, in the header**, and the kit had it wrong before 2026-09-13) and `claim_nmi` (OSBYTE 143,12 and an `RTI` at `&0D00`), both after the LAST load. The BREAK rule (`OSBYTE 200, 3`) is for a port that unpacks over all of HAZEL from `&C000`, as Edge does. Header: **OSFILE writes the addresses back into its block — reset before every call**, and reset to `&FFFFxxxx`, the host's, or a second processor takes the file (measured, `../docs/hardware-facts.md` "Target configurations"). The block is in the file. Paradroid's `*LOAD` variant is mentioned, not ported | `zxsrc`/`zxdst`, `zx_unpack` (the depacker's entry - it was `zx0_unpack` before 2026-09-07, and still is in the two shipping ports), `LOADER_STAGE`, `MASTER` = 0/1 |
| `boot_stamp.6502` | **The stamp is a disc file, `INFO`** (Paradroid b5ffa94, 2026-09-11), so `*TYPE INFO` reads the build back at any prompt and not only while it scrolls past at boot. Five macros: `BOOT_STAMP_HEAD title` (title, "DEV build" unless `RELEASE`, `VERSION_LINE` and `ASSERT DEBUG_ANY = 0` under it), `BOOT_FLAG flag, text` (one line per flag that is on), `BOOT_STAMP_TIME` (`BUILD ` + `BUILD_TIME`) - the includer wraps those three in a macro of its own, written ONCE, so `INFO` and the boot message cannot drift - then `BOOT_FILE_HEAD` and `BOOT_FILE_TAIL runfile`, which build `!BOOT`: **a `*RUN` stub, the only shape** (Paradroid 61500a8, 2026-09-13, hexwab), printing its own copy of the stamp and OSCLIing `RUN <file>`. Disc option **2** on every build, `exec =` the section's start, and an address the stub can RUN at - not `&7E00`, MODE 7's screen; the template uses `&0900`. The `*EXEC` text shape and `BOOT_RUN` are GONE: `*EXEC` writes into `&1100-&1900`, so it cannot coexist with `OSBYTE 140` or with a game living there (`loader.6502`), and it needs a language ROM | `RELEASE`, `BUILD_TIME`, `DEBUG_ANY`, `VERSION_LINE` (a string) |
| `swram_probe.6502` | Written for the Model B; runs on a Master too. Paradroid's `PARSWR` as of 7f91e77 (2026-09-11). It probes the sixteen slots with distinct values, which catches bank aliasing, and skips slots the MOS found a ROM in. Solidisk-style boards are refused. The highest four RAM banks are handed to the game at `SWR_HAND`, then it RTSes to BASIC. It prints **every bank found** as well as the four taken, in mixed case. A Master 128 that is short is told `(Set LK18 and LK19 west?)`. On success it calls OSBYTE 114,1 so the game's mode change isn't a shadow one. With exactly three clean banks, a ROM image in sideways RAM (ZMMFS) becomes the fourth bank. **That puts two duties on the game (header): fill that bank after the last filing-system call, and zero its `&02A1` byte first.** A standalone overlay `*RUN` from `!BOOT` before the game. `test/probe_test.6502` builds it as a bootable disc; `../docs/hardware-facts.md` §5 has what each path printed in jsbeeb | `SWR_HAND`, `SWR_MAGIC`, and the `CLEAR`/`ORG`/`SAVE` wrapper (in the header) |

### From the CPC demos: the AY in real time, and the smallest depacker

| File | What it is | The includer defines |
|---|---|---|
| `ay2sn.6502` | **The AY-3-8912 on the SN76489 at run time**, for a player that writes AY registers every field: Unspoken's fork of arkos-player-bbc's `ay2sn`, as Square Roots and Isometrikum (before its crunch) used it at the **CPC's 1 MHz** (SN period = AY period x 2, a shift). Below the SN's 122 Hz (AY period >= 512) the note goes to **software bass**: the channel's tone parked at period 1 and the User VIA's T1, free-running, toggling its attenuation (`bass_irq`); one sticky claim. No envelope (neither demo's tunes wrote R11-R13 - measure yours). `sn_write` holds WE 18+ cycles. Tables `ay2sn_tables.6502` from `template/tools/make_ay2sn_tables.py`; the 6502 in Python is `template/tools/ay2sn_model.py`. Cost (Isometrikum): its tune and this 2,337 cycles a field, the bass 1.95 interrupts a field at 152 cycles; toggles land late behind other interrupts (`../docs/cpc-demo-porting.md` section 9) | `ay_regs` (14 bytes) filled by the player; `ay2sn` called with I set from the VSync IRQ; `bass_irq` called when User VIA T1 interrupts; T1 set free-running once (ACR bit 6) |
| `unshrinkler.6502` | Dudek and Fusik's unShrinkler (zlib licence), translated from MADS to Baron instruction for instruction, `PARITY=0 FAST=0`: about 320 bytes and **~4,000 cycles a byte** - 75x slower than ZX02 for the smallest packed size there is (Isometrikum's crunch: 10,623 bytes of Shrinkler streams against 12,271 of ZX02). The stream is Shrinkler's `-d -b` raw data (`template/tools/shrinkler.py`, whose transcribed decoder is the oracle). The output may overlap the stream's already-read part | `SHR_DATA` (1.5K page-aligned workspace), 19 zero-page bytes `shr_zp`; then `shr_zp+0/1` the stream, `+2/3` the output, `jsr unshrinkler` |

### From 1942: reading the disc after the boot, and a BREAK that cleans up

| File | What it is | The includer defines |
|---|---|---|
| `qdisc.6502` | **Master only.** A DFS-free, non-blocking sector reader for the WD1770, after scarybeasts' quicdisc: the game calls `release_fs` (`*FX 140,0`) after its boot and then drives the controller itself, a self-modifying NMI routine at `&0D00` storing each byte. `qd_seek`, `qd_read` (a run of sectors on one track, ended by FORCE INTERRUPT at the page count), `qd_busy`, `qd_wait`, `qd_warm` (keep the motor spinning before a load you can see coming). The routine is DISARMED (`RTI`) between reads, because on an Acorn board the NMI is DRQ OR INTRQ and a seek's completion would otherwise store a junk byte. 35 cycles a byte, counted; 35.4 measured. **The kit's third answer** to "does the game read the disc after it starts" - `loader.6502`'s contract has the other two. Header: the E-bit settle on a real 1770 (15-30 ms every read), a busy 1770 ignoring commands, the target staying paged for the whole read | `QD_NMI_A`, one zero-page byte (1942: `&A0`, the MOS's NMI-owner workspace). It owns `&0D00-&0D31` |
| `qdisc_init.6502` | Boot-only half: `qd_cfg` (**before** `*FX 140`: the drive the game was run from, out of OSGBPB 5, and `*CONFIGURE FDRIVE`'s step rate out of CMOS byte 11 - **2 and 3 clamped to 12 ms**, because they mean 20/30 ms on a 1770 and 2/3 ms on a 1772), the NMI routine's source, and `qd_init` (patch every drive select, restore and seek; install; restore to track 0) | nothing more |
| `qdload.6502` | Files by NAME after the release: `qd_load_stream` has `load_stream`'s contract (A/Y the name, X the page, leaves `zxsrc`), `qd_load_part` loads sectors `qd_poff`..+`qd_plen` of a file. Blocks; `qd_err` says if a run failed four times. Only the files listed with `QD_FILE` are known, matched on their first `QD_NCH` characters, directory ignored, at most 255 sectors each | `zxsrc`, `QD_NCH` (1-7), and after the include `.qd_cat`, one `QD_FILE "NAME"` a file, `.qd_cat_end` |
| `qdload_init.6502` | Boot-only half: `qd_boot` (after the release) installs the driver and reads the catalogue's two sectors once, filling the table; returns how many listed files were not on the disc. **Fixed on the way in**: 1942's copy never matched the LAST catalogue entry - the disc's first file (`Y < 8N` where entry N-1 is at `8N`) | `QD_CAT_STAGE`, a page-aligned 512 bytes it may overwrite |
| `break.6502` | **BREAK clears RAM.** `brk_arm` (call it first): `*FX 200,2`, and the BREAK intercept at `&0287` (`*FX 247`) pointing at `brk_clear`, which stores 2 at `&0258` and `JMP (&FFFC)`s so the reset's second pass clears. MOS 3.20 clears memory at a reset only if the system VIA's IER is 0 or `(&0258 >> 1) = 1`, so `*FX 200,2` alone is enough until the game writes `&0258`; the intercept covers a game that uses that page. **Nothing of the game's may live at `&0287-&0289`** (1942 BUGS.md #92: two variables at `&0288` made a BREAK in play `JMP &005D`) | nothing; `brk_clear` must be resident |

### From Stryker's Run: one source for a Master and a Model B, and sound without the MOS

| File | What it is | The includer defines |
|---|---|---|
| `nmos.6502` | **The 65SC12's own instructions as macros**, one per instruction AT A SITE, named for the NMOS form that replaces it there: `STZ_A addr` is `STZ` where A is known 0 (and `STA` with `NMOS`), `STZ_LDA` is `STZ` where A, N and Z are dead (`LDA #0 : STA`), `BRA_CS` a `BRA` where C is known 1 (`BCS`), `INC_A_ADC`, `PHX_A` and so on: 33 macros, each with its condition and cost. Without `NMOS` every one IS the 65SC12 instruction, so the Master build stays byte-identical; with it Baron's `cmos = FALSE` on every section rejects anything left. **The forms are chosen, and re-proved, by `template/tools/nmosify.py` from the dataflow annotation** - `check` on the build without `NMOS` and `check --nmos` on the build with it, both, because two forms each safe alone can clash (the header has Stryker's Run's two). Stryker's Run (decision 73): 281 sites, 232 by rule and 49 by hand, at most 683 cycles a pass (0.9%); the NMOS build played the whole game state-identical to the Master's | `NMOS` = 0/1, and `cmos = (NMOS = 0)` on every section |
| `sfx50.6502` | **Sound effects at 50 Hz, for a game that owns IRQ1V.** `irq.6502` stops the MOS's tick and its SOUND/ENVELOPE driver with it; this is the replacement. `sfx_tick` once a field from the vsync hook; an effect is a list of 6-byte RAMPS (over N fields the period, or the noise control, and the amplitude each step linearly), fitted to the MOS's own playing of the original's SOUND and ENVELOPE by `py/beeb_port_kit/sfx50.py` from `template/tools/sfxcapture.mjs`'s capture - not written by hand. Requests by chip channel (`sfx_request + C` = effect + 1; a request replaces what the channel played), `sfx_silence` at each handover. The chip written as MOS 3.20 writes it, the noise control and a tone's amplitude only when they change. Stryker's Run (decision 25): interrupts 10.9% of the CPU to 2.2%, its 8 effects in 158 bytes. Plain 6502 here (its 65SC12 forms as `nmos.6502`'s NMOS ones). **An effect ends a field early**: the channel is silenced in the tick that outputs its last field; `sfx50.py --pad-end` gives it one more. Effects at `&1000` or above (the header says why) | `sfx_request` (4 bytes, zero, where the interrupt sees them), `sfx_effect_lo`/`_hi` (`sfx50.py`'s file), `beeb.h.6502`'s System VIA names |

## Proving ZX02 is the one to use

`test/bench/bench_depack.py` is where the ZX02-against-ZX0 numbers come from: it assembles both
depackers, compresses the files you name with both compressors, steps both decodes through py65
and checks each one against the source file byte for byte. From the kit's root, with `py65`
installed:

```
python lib/test/bench/bench_depack.py FILE [FILE ...]
```

It printed, over 43 data files from the two shipping ports (242,481 bytes), on 2026-09-07:
131 bytes against 257, 53.9 cycles/byte against 115.4 (2.14x), +0.11% on the packed total.

## Proving it runs

Assembling proves the syntax, and nothing more. `unpack_andy` assembled in `test_lib.6502` from
the day it was written. The first port to call it, 1942, found it put its stream 135 bytes out
(its BUGS.md #21). Two routines now have a disc that boots and checks what they did:

| Test | What it proves | Pass |
|---|---|---|
| `test/probe_test.6502` | `swram_probe.6502` on a real boot, every path by poking the ROM type table | `hardware-facts.md` §5 has the table |
| `test/andy_test.6502` (Master) | `unpack_andy` puts a 64-byte pattern at `&8100` in ANDY and puts ROMSEL back | `&0900` holds the pattern and `&0A00` reads `40 81 <bank>` |
| `test/run_test.6502` | the three the 2026-09-11 audit found had never run: `load_bank` (a stream into sideways bank 4), `install_irq`/`uninstall_irq` (the MOS clock stops and restarts), `keydown_inkey` (a key held through the emulator) | `&0900` holds the pattern, `&0A00` = `40 80`, `&0A02` = 4; the clock is frozen across 50 fields and moves after the uninstall; `&0A13` = 50; `&0A20` = 0 with the key held, `&80` without |

And five headless ones, which assemble their own disc, boot it on jsbeeb (the one
`template/.mcp.json` pins, found by `template/tools/jsbeeb_src.mjs`), check everything and say
so in the **exit code**. From the kit's root, with `template/bin` populated:

| Test | What it proves | Measured |
|---|---|---|
| `node lib/test/qdisc_test.mjs` (`qdisc_test.6502`) | the four 1770 files: `qd_cfg`, `*FX 140`, `qd_boot`; the file table against the catalogue (its first and last entries, and one file not on the disc); every track of both sides of a patterned DOUBLE-sided disc byte-exact, with a sentinel after the buffer and a SEEK before each read; a run inside a track; `qd_load_stream` of four files and `qd_load_part` across two track boundaries, each with a sentinel and a `qd_warm` before it | jsbeeb 2.10.2, 2026-10-25: 161 reads, 0 bytes wrong, 0 sentinels moved; 5 loads exact; 35.4 cycles a byte in the NMI; a whole track 506,810 cycles, a one-track seek 12,151 (FDRIVE 0 in jsbeeb's CMOS). Without the last-entry fix the table check fails (measured) |
| `node lib/test/break_test.mjs` (`break_test.6502`) | `break.6502`, four cases from one snapshot, IER non-zero (`&53`, the MOS's): no `*FX 200` keeps RAM; `*FX 200,2` clears; `*FX 200,2` then `&0258` = 0 KEEPS it; `brk_arm` then `&0258` = 0 clears. Each time the MOS must come back and answer `*FX 0` | jsbeeb 2.10.2 Master, 2026-10-25: all four as stated, `&3000-&5FFF` and the program itself zeroed in the two that clear |
| `node lib/test/model_stub_test.mjs` | `py/beeb_port_kit/dfs.model_stub`: a game built for `&0E00` behind the stub runs on a Master; a B (DFS 1.2) and a B1770 print the message, and BASIC answers `PRINT 6*7`. Control: the same game as a plain `!BOOT` at `&0E00` hangs a B inside the DFS | jsbeeb 2.10.2, 2026-10-25: as stated; the plain `!BOOT` left both Bs in DFS code (PC `&DC5D`, `&8E14`) with BASIC dead |
| `node lib/test/sfx50_test.mjs [MODEL]` (`sfx50_test.6502`) | `sfx50.6502` under `irq.6502`: `sfx50.py` fits two effects of Stryker's Run's MOS capture (`py/tests/data`: a noise burst, and a falling tone in three ramps), the driver plays both at once, and every chip write is replayed into the chip's registers at each vsync: each channel must hold exactly what `sfx50.play()` says, field by field, then silence, and the other two channels silence throughout. Twice: as fitted, and `--pad-end` | jsbeeb 2.10.2, 2026-10-25, Master and B-DFS1.2 alike: 0 fields wrong of 16 + 35 heard (17 + 36 padded), 107 (111) chip writes; the ramps within 7 of the MOS's period (of ~450) and 1 of its amplitude. As fitted each effect's last MOS field is cut (the driver's end, above); padded, none |
| `node lib/test/range_free.mjs DISC DRIVER.mjs` | NOT a pass/fail on the kit: the **"is this RAM free?" instrument**, from 1942's `measure_lowram` and `measure_break`. Your DRIVER module plays the game; it hooks every write into the ranges (default: the MOS low RAM a Master game might take) and names the writer, then fills each block with four patterns and presses BREAK. `range_free_example.mjs` is its sanity check: on `break_test`'s disc, where the MOS still owns the IRQ, it must FAIL | the example: 27 bytes written by the MOS in `&0240-&02CD`; BREAK needs `&0200-&027F` and `&0280-&02FF` |

Between them, every routine in `lib/` has now been run, not just assembled, except the ZX0
depacker (stepped in py65 by the bench below, and it is what both shipping discs use).

Each file's header has its build line. **A routine with no runtime test should say so in its
header**, so the first caller knows it's first.

## Proving it assembles

`test/test_lib.6502` includes `beeb.h.6502`, a dummy zero page, every routine with dummy hooks (the 1770 driver and `break.6502` too, since 2026-10-25; `nmos.6502` with three of its macros, NMOS forms, and `sfx50.6502` with a one-ramp effect, 2026-10-25),
both depackers, the ZX02 one twice (Paradroid instantiated its depacker twice), the probe, and `INFO` plus a
`!BOOT` in both shapes. From the kit's root:

```
baron --warn 2 -p lib/test/build -D RELEASE=0 lib/test/test_lib.6502
baron --warn 2 -p lib/test/build -D RELEASE=1 lib/test/test_lib.6502
```

`nmos.6502`'s macros are proved both ways by their own test, with py65 (`pip install py65`):

```
python lib/test/nmos_test.py [TRIALS]
```

It assembles `test/nmos_test.6502` (every macro once) three times: without `NMOS` the macros'
section must be byte-identical to a section of the bare 65SC12 instructions; with `NMOS` it
must assemble under `cmos = FALSE`; and with one raw `STZ` added Baron must refuse it. Then it
runs each macro's NMOS form on py65's NMOS 6502 against its 65SC12 instruction on the 65C02
from the same random states, made to meet the macro's condition, and compares everything the
condition does not call dead (registers, flags, S, the path a branch took, zero page, the live
stack, the operand's page). Measured 2026-10-25 (Baron 0.6.0, py65 1.2.0): 34 sites, 112 bytes
identical; NMOS build 151 bytes; the raw `STZ` refused; 34 x 400 trials, 0 differences; with
four conditions weakened (the control), 156 of 1,700 trials differ. Exit code = verdict.

`--warn 2` is what the template's builds pass; `lib/` is silent at that level, both values of
`RELEASE` (measured 2026-09-23, Baron 0.4.0, and the three files come out byte-identical to the
0.3.0-era binary's; again 2026-10-11, 0.5.3 against 0.4.0, and 2026-10-21, 0.6.0 against 0.5.3, byte-identical). Baron is silent on success, warnings never change the exit code, and every
error of a run is reported in one go — so check the **exit code**. In PowerShell do not redirect
stderr or `$ErrorActionPreference = 'Stop'` throws on a successful build. `lib/test/build/` is scratch; `INFO` there is the stamp read back, and `BOOT` is the stub, with whichever
lines the `RELEASE` you passed puts in it.

## What is deliberately not here

- The rupture itself (the per-game CRTC register sequence the two hooks write). It is the one
  thing that was *different* in every respect between the two ports; `PORTING.md` describes how
  to design one and `docs/hardware-facts.md` the measured write windows.
- Paradroid's sound-tick paging shim inside the IRQ. Put it in your VSync hook; `irq.6502`'s
  header says how (save ROMSHAD, not ROMSEL).
- Paradroid's `*LOAD`-through-OSCLI loader. OSFILE is the smaller thing to generalise.
- Any 65C12 opcode in the routines. Both ports are `CPU 0`; decide before you use one. (1942's
  1770 files used `STZ`, `BRA`, `PHY`; the copies here are rewritten in plain 6502 so they
  assemble in a section without `cmos = TRUE`, and so is `sfx50.6502`.) A Master port that
  wants its 65SC12 code and a Model B build from one source writes it with `nmos.6502`'s macros.
- 1942's background reader (`bgread.6502`: rationed sector reads during play, into a bank the
  game is not drawing from, with the NMI's target outside anything ROMSEL or ACCCON moves). It
  is a pattern on top of `qdisc.6502`, not a library; its header in that repository says how.
