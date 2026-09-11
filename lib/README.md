# lib/ — the 6502 half of the kit

Eight Baron includes (plain 6502, NMOS) that were identical or near-identical between the
[Paradroid](https://github.com/kieranhj/paradroid-beeb) and
[Edge Grinder](https://github.com/kieranhj/edge-beeb) ports, made generic once. MIT, Kieran
Connell.

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

These files are **[Baron](https://github.com/waitingforvsync/baron)** syntax as of 2026-09-07
(`.6502`, sections instead of `ORG`/`SAVE`, `ASSERT` as a macro in `beeb.h.6502`). The two
shipping ports are BeebASM projects and their own copies are unaffected; a port that wants
BeebASM reverses the table in `../docs/toolchain-baron.md`, which is six lines' work, or takes
the files from this repository's history (branch `zx02-depacker`).

The conversion changed no emitted byte: the test image below came out **byte-identical**
(1,509 bytes) under both assemblers, and the template built on these files is byte-identical
to its BeebASM build.

## The files

| File | What it is | The includer defines |
|---|---|---|
| `beeb.h.6502` | The hardware constants both mains carried: CRTC, Video ULA and NuLA, both VIAs by register, ROMSEL/ROMSHAD/ACCCON with the Master's bit names, IRQ1V, the `KBD_*` latch values, `SL = 64`, the MOS entry points, and the `CRTC r, v` macro. Edge's names; Paradroid's noted beside them | nothing — include it first |
| `zx02depack.6502` | **What a new port uses.** Daniel Serpell's ZX02 (default mode) as the macro `ZX02_DEPACKER`, 131 bytes, ~54 cycles/byte. A BeebASM transcription of his `zx02-optim.asm`, verified by stepping it in py65 over 43 real files from both ports and comparing the output with the source, byte for byte, and end to end by booting the template's disc in jsbeeb. Against `zx0depack.6502`: **half the code, 2.14x the speed, +0.11% on the packed size** (the header has the per-file numbers). Header carries the calling convention, the **in-place rule** and the **beebasm pass-1 sizing trap** | five zero-page symbols `zxsrc zxdst zxofs zxbit zxwrk` (8 bytes; no `zxlen` - the length lives in X), declared *before* the first file that uses one; then `.zx_unpack` + `ZX02_DEPACKER` |
| `zx0depack.6502` | Einar Saukas's ZX0 (default mode) as the macro `ZX0_DEPACKER`, 257 bytes. Written from the compressor's source, verified byte for byte in both ports. **Kept for the two shipping discs, which are ZX0 discs**; a new port takes `zx02depack.6502` instead. The formats are not interchangeable: one depacker, one compressor, and nothing checks they agree but you | six zero-page symbols `zxsrc zxdst zxofs zxlen zxbit zxwrk`, declared *before* the first file that uses one; then `.zx0_unpack` + `ZX0_DEPACKER` |
| `irq.6502` | The IRQ1V owner: `irq_handler` (System VIA T1 and CA1/VSync, nothing passed to the MOS), `install_irq` (which silences the sound chip, since the MOS's driver dies with its interrupt), and `uninstall_irq` under `IF IRQ_UNINSTALL` (with the state saves that make it possible). Header: filing-system calls precede install; flush the MOS sound workspace (`OSBYTE &0F`) *before* uninstall; a hook that pages a sideways bank saves and restores ROMSHAD itself | `irq_timer_hook`, `irq_vsync_hook` (routines), `IRQ_UNINSTALL` = 0/1 |
| `keydown.6502` | One key read straight off the keyboard matrix, 69 cycles against OSBYTE's 243 (measured). Two entries on one body: `keydown_int` (internal key number in, N out — Edge) and `keydown_inkey` (negative INKEY byte in, Z out — Paradroid). Header: the latch line 3 / DDRA `&7F` / `&FE4F` sequence, the phantom sixth key, and that key numbers are measured (OSBYTE 121; INKEY for SHIFT and CTRL). Edge's `read_joystick` as a commented example of packing five keys into the C64's `$dc00` byte | nothing beyond `beeb.h.6502` |
| `loader.6502` | Edge's OSFILE loader: `load_stream` (filename in A/Y, staging page in X, leaves `zxsrc`), `unpack_to` (X:A), `load_bank` (filename + ROMSEL value, unpacks into the paged bank), and under `IF MASTER` `load_hazel` (into `HAZEL_FREE`, `&C300-&DEFF`, the window OSFILE leaves alone, so loads may follow it; measured on jsbeeb's Master 2026-09-11) and `unpack_andy` (fixed 2026-09-11, 1942's BUGS.md #21; the MOS writes three of ANDY's pages — `&80`, `&8800-&882F`, `&8F` — so `../docs/hardware-facts.md` "ANDY" says when all 4K is usable), then `claim_nmi` (OSBYTE 143,12 and an `RTI` at `&0D00`, called after the last load, instead of `*TAPE`). The BREAK rule (`OSBYTE 200, 3`) is for a port that unpacks over all of HAZEL from `&C000`, as Edge does. Header: **OSFILE writes the addresses back into its block — reset before every call**, and reset to `&FFFFxxxx`, the host's, or a second processor takes the file (measured, `../docs/hardware-facts.md` "Target configurations"). The block is in the file. Paradroid's `*LOAD` variant is mentioned, not ported | `zxsrc`/`zxdst`, `zx_unpack` (the depacker's entry - it was `zx0_unpack` before 2026-09-07, and still is in the two shipping ports), `LOADER_STAGE`, `MASTER` = 0/1 |
| `boot_stamp.6502` | `!BOOT` generation as three macros: `BOOT_STAMP_HEAD title` (REM title, "DEV build" unless `RELEASE`, `VERSION_LINE` and `ASSERT DEBUG_ANY = 0` under it), `BOOT_FLAG flag, text` (one REM per flag that is on), `BOOT_STAMP_TAIL runfile` (`REM BUILD` + `TIME$`, `*RUN`). The header shows the `CLEAR`/`ORG`/`SAVE` wrapper and why it lives at a scratch address. **With `BOOT_RUN = 1` the same three macros build a `*RUN` stub instead**: it prints the stamp without `REM`s and OSCLIs `RUN <file>`. Needs disc option 2, `exec =` the section's start, and an address that isn't the MODE 7 screen (the template uses `&0900` for its RELEASE build) | `RELEASE`, `BOOT_RUN` (no default: a `DEFINED()` one never settles in Baron), `DEBUG_ANY`, `VERSION_LINE` (a string) |
| `swram_probe.6502` | Written for the Model B; runs on a Master too. Paradroid's `PARSWR` as of 7f91e77 (2026-09-11). It probes the sixteen slots with distinct values, which catches bank aliasing, and skips slots the MOS found a ROM in. Solidisk-style boards are refused. The highest four RAM banks are handed to the game at `SWR_HAND`, then it RTSes to BASIC. It prints **every bank found** as well as the four taken, in mixed case. A Master 128 that is short is told `(Set LK18 and LK19 west?)`. On success it calls OSBYTE 114,1 so the game's mode change isn't a shadow one. With exactly three clean banks, a ROM image in sideways RAM (ZMMFS) becomes the fourth bank. **That puts two duties on the game (header): fill that bank after the last filing-system call, and zero its `&02A1` byte first.** A standalone overlay `*RUN` from `!BOOT` before the game. `test/probe_test.6502` builds it as a bootable disc; `../docs/hardware-facts.md` §5 has what each path printed in jsbeeb | `SWR_HAND`, `SWR_MAGIC`, and the `CLEAR`/`ORG`/`SAVE` wrapper (in the header) |

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

Between them, every routine in `lib/` has now been run, not just assembled, except the ZX0
depacker (stepped in py65 by the bench below, and it is what both shipping discs use).

Each file's header has its build line. **A routine with no runtime test should say so in its
header**, so the first caller knows it's first.

## Proving it assembles

`test/test_lib.6502` includes `beeb.h.6502`, a dummy zero page, every routine with dummy hooks,
both depackers, the ZX02 one twice (Paradroid instantiated its depacker twice), the probe, and a `!BOOT` with both stamp
branches. From the kit's root:

```
baron -p lib/test/build -D RELEASE=0 lib/test/test_lib.6502
baron -p lib/test/build -D RELEASE=1 lib/test/test_lib.6502
```

Baron is silent on success and reports every error in one run, so check the **exit code** — in
PowerShell do not redirect stderr or `$ErrorActionPreference = 'Stop'` throws on a successful
build. `lib/test/build/` is scratch; `boot.txt` there is the stamp read back.

## What is deliberately not here

- The rupture itself (the per-game CRTC register sequence the two hooks write). It is the one
  thing that was *different* in every respect between the two ports; `PORTING.md` describes how
  to design one and `docs/hardware-facts.md` the measured write windows.
- Paradroid's sound-tick paging shim inside the IRQ. Put it in your VSync hook; `irq.6502`'s
  header says how (save ROMSHAD, not ROMSEL).
- Paradroid's `*LOAD`-through-OSCLI loader. OSFILE is the smaller thing to generalise.
- Any 65C12 opcode. Both ports are `CPU 0`; decide before you use one.
