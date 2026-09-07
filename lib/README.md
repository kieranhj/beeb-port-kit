# lib/ — the 6502 half of the kit

Seven BeebASM includes (plain 6502, `CPU 0`) that were identical or near-identical between the
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
manual that neither port exercised, the header says so (`beeb.h.asm`'s five unused ACCCON bits).

## The files

| File | What it is | The includer defines |
|---|---|---|
| `beeb.h.asm` | The hardware constants both mains carried: CRTC, Video ULA and NuLA, both VIAs by register, ROMSEL/ROMSHAD/ACCCON with the Master's bit names, IRQ1V, the `KBD_*` latch values, `SL = 64`, the MOS entry points, and the `CRTC r, v` macro. Edge's names; Paradroid's noted beside them | nothing — include it first |
| `zx0depack.asm` | Einar Saukas's ZX0 (default mode) as the macro `ZX0_DEPACKER`, 257 bytes. Written from the compressor's source, verified byte for byte in both ports. Header carries the calling convention, the **in-place rule** (a stream may not be overtaken by its own output) and Edge's **beebasm pass-1 sizing trap** | six zero-page symbols `zxsrc zxdst zxofs zxlen zxbit zxwrk`, declared *before* the first file that uses one; then `.zx0_unpack` + `ZX0_DEPACKER` |
| `irq.asm` | The IRQ1V owner: `irq_handler` (System VIA T1 and CA1/VSync, nothing passed to the MOS), `install_irq`, and `uninstall_irq` under `IF IRQ_UNINSTALL` (with the state saves that make it possible). Header: filing-system calls precede install; flush the MOS sound workspace (`OSBYTE &0F`) *before* uninstall; a hook that pages a sideways bank saves and restores ROMSHAD itself | `irq_timer_hook`, `irq_vsync_hook` (routines), `IRQ_UNINSTALL` = 0/1 |
| `keydown.asm` | One key read straight off the keyboard matrix, 69 cycles against OSBYTE's 243 (measured). Two entries on one body: `keydown_int` (internal key number in, N out — Edge) and `keydown_inkey` (negative INKEY byte in, Z out — Paradroid). Header: the latch line 3 / DDRA `&7F` / `&FE4F` sequence, the phantom sixth key, and that key numbers are measured (OSBYTE 121; INKEY for SHIFT and CTRL). Edge's `read_joystick` as a commented example of packing five keys into the C64's `$dc00` byte | nothing beyond `beeb.h.asm` |
| `loader.asm` | Edge's OSFILE loader: `load_stream` (filename in A/Y, staging page in X, leaves `zxsrc`), `unpack_to` (X:A), `load_bank` (filename + ROMSEL value, unpacks into the paged bank), and under `IF MASTER` `load_hazel` and `unpack_andy`, with the BREAK rule (`OSBYTE 200, 3`). Header: **OSFILE writes the addresses back into its block — reset before every call.** The block is in the file. Paradroid's `*LOAD` variant is mentioned, not ported | `zxsrc`/`zxdst`, `zx0_unpack`, `LOADER_STAGE`, `MASTER` = 0/1 |
| `boot_stamp.asm` | `!BOOT` generation as three macros: `BOOT_STAMP_HEAD title` (REM title, "DEV build" unless `RELEASE`, `VERSION_LINE` and `ASSERT DEBUG_ANY = 0` under it), `BOOT_FLAG flag, text` (one REM per flag that is on), `BOOT_STAMP_TAIL runfile` (`REM BUILD` + `TIME$`, `*RUN`). The header shows the `CLEAR`/`ORG`/`SAVE` wrapper and why it lives at a scratch address | `RELEASE`, `DEBUG_ANY`, `VERSION_LINE` (a string) |
| `swram_probe.asm` | **Model B only.** Paradroid's `PARSWR` as-is: probes the sixteen slots with distinct values (catches bank aliasing), skips slots the MOS found a ROM in, refuses Solidisk-style boards, hands the highest four RAM banks to the game at `SWR_HAND` and RTSes to BASIC. A standalone overlay `*RUN` from `!BOOT` before the game | `SWR_HAND`, `SWR_MAGIC`, and the `CLEAR`/`ORG`/`SAVE` wrapper (in the header) |

## Proving it assembles

`test/test_lib.asm` includes `beeb.h.asm`, a dummy zero page, every routine with dummy hooks,
the depacker twice (Paradroid instantiated it twice), the probe, and a `!BOOT` with both stamp
branches. From the kit's root:

```
beebasm -i lib/test/test_lib.asm -o lib/test/build/test.bin -D RELEASE=0
beebasm -i lib/test/test_lib.asm -o lib/test/build/test.bin -D RELEASE=1
```

beebasm writes its progress to stderr, so check the **exit code**, not the stream — in
PowerShell do not redirect stderr or `$ErrorActionPreference = 'Stop'` throws on a successful
build. `lib/test/build/` is scratch; `boot.txt` there is the stamp read back.

## What is deliberately not here

- The rupture itself (the per-game CRTC register sequence the two hooks write). It is the one
  thing that was *different* in every respect between the two ports; `PORTING.md` describes how
  to design one and `docs/hardware-facts.md` the measured write windows.
- Paradroid's sound-tick paging shim inside the IRQ. Put it in your VSync hook; `irq.asm`'s
  header says how (save ROMSHAD, not ROMSEL).
- Paradroid's `*LOAD`-through-OSCLI loader. OSFILE is the smaller thing to generalise.
- Any 65C12 opcode. Both ports are `CPU 0`; decide before you use one.
