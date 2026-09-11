# Target portability: which machines, decided (2026-09-11)

A port should run on as many of the machines people actually own as its goals allow, and
**say plainly** on the ones it doesn't. Which ones it tries for is the owner's decision, and
the answer varies by project. Edge Grinder is Master-only by design, so half of this page
doesn't apply to it. So this page is a list of questions with what each answer costs, not a
list of answers. Copy the rows that apply into the port's `docs/decisions.md` as numbered
decisions, on day one, next to decision 1 ("choose the machine", `PORTING.md` §2.2).

The list is [paradroid-beeb issue #18](https://github.com/kieranhj/paradroid-beeb/issues/18):
hexwab's checklist, KC's ruling on each item, Paradroid's fixes and a contributor's MAME runs.
The kit's own measurements are in `hardware-facts.md` ("Target configurations" and §5). The
rule behind them all: **the loader absorbs the differences between machines, once, and the
game then assumes nothing.** Most fixes cost a few bytes of loader, the game pays nothing,
and the expensive part is testing.

## The kit's defaults: do these whatever the target

Each is in the template and was measured before and after (jsbeeb, 2026-09-11). Keep them
when changing the boot.

| Default | Without it |
|---|---|
| Every catalogue address `&FFFFxxxx` (`dfs.to_host`) **and** the loader's OSFILE block the same | Second processor: the files load into the parasite. The template showed a black screen on B + 65C02 and Master + 65C102 |
| OSBYTE 114,1 before the one `VDU 22` | Master or B+ under `*SHADOW`: the display comes up in shadow RAM while the game writes main (ACCCON `&1B`) |
| Every CRTC register written after the mode change | `*TV`, interlace or a third-party OS's values leak into the frame |
| `claim_nmi` (OSBYTE 143,12 and `RTI` at `&0D00`) after the last load, never `*TAPE` | `*TAPE` unplugs the filing system and forces a `*DISC` on someone who booted from MMFS or ADFS; only Econet minds the claim |
| `swram_probe.6502`, if the game uses sideways RAM | A board jumpered anywhere but 4-7 loads a game that isn't there and hangs with a blank screen |

**What they cost, measured:** the first four together added **87 bytes** to the template's
`Game` (1,081 to 1,168), all of it boot code a port can overlay once the game is running. The
probe is 809 bytes in its own disc file, which the game never keeps.

## The configurations

"Test it in" names what can actually run the configuration. **jsbeeb** is the one Claude drives
through the MCP. **b2**, **b-em** and **MAME** are run by hand, or by Claude through their
command lines. "Paradroid" is its release on `main` (2026-09-11). "Edge" is Master-only, so
"n/a" means a B configuration.

| # | Configuration | What goes wrong, and the fix | Test it in | Paradroid | Edge |
|---|---|---|---|---|---|
| 1 | **Model B, Acorn DFS 1.20**, the baseline | Nothing, if the build was developed on it | jsbeeb `B-DFS1.2` | plays | n/a |
| 2 | Model B, DFS 0.90 or Acorn 1770 DFS | Nothing seen yet | jsbeeb `B-DFS0.9`, `B1770` | plays | n/a |
| 3 | Model B, third-party DFS: Watford DDFS, Opus, Solidisk | Workspace and NMI code differ. Paradroid ran it in b2 (DDFS 1.53, 1.54T); b-em's `-m19` died at `*RUN PARA`, apparently b-em's own fault | b2 (DDFS), b-em presets 17-19 | DDFS runs (b2, KC); others not a priority (KC) | n/a |
| 4 | Model B, sideways RAM **not at 4-7**, on a board that aliases, or on too few banks | Probe it: 16 distinct values, only banks with a zero ROM type byte, the highest four. `swram_probe.6502` | jsbeeb (poke `&02A1` to hide banks), MAME boards | probes | n/a |
| 5 | Model B, **Solidisk-style write-select** sideways RAM | Writes need the index in the User VIA and `&FE32` too. Detected and **refused**, because the game writes through ROMSEL alone | MAME `-internal swr64` | refuses, with a message | n/a |
| 6 | Model B, **a filing system softloaded into sideways RAM** (ZMMFS: common, because `PAGE` at `&0E00` beats more RAM) | Its bank is marked in `&02A1`, so a 4-bank B finds 3. The probe takes the image bank as the fourth, and the **game** fills it after the last filing call, zeroing its type byte first | jsbeeb with a stand-in ROM image (below); b2 has MMFS; MAME's SD-card setup defeated hexwab | built, jsbeeb stand-in only | n/a |
| 7 | Model B with a **third-party shadow board** (Aries...), which ignores `&FE34` | OSBYTE 133,1, then **only if** Y is negative OSBYTE 114,1; blank, clear, `VDU 22`, zero `&FE34`, write every CRTC register. Once, in the loader. hexwab's *Starship Command 2022* dance | MAME, **for the shadow board only**: its 6845 can't run a game | out of scope (KC) | n/a |
| 8 | **B+ 128K** | Shadow as on a Master: OSBYTE 114,1 covers it. `&FE34` differs. jsbeeb has no B+ | b-em preset 9 | untested | n/a |
| 9 | **Master 128**, MOS 3.20, and 3.50 | Four sideways banks at 4-7 **if LK18 and LK19 are set west**. Shadow, ANDY and HAZEL available | jsbeeb `Master` (3.20); b-em presets 10, 15 | plays; real hardware too (KC) | the target |
| 10 | Master under **`*SHADOW`** and a soft BREAK | Kit default (OSBYTE 114,1) | jsbeeb: type `*SHADOW`, soft reset, boot | fixed | not checked |
| 11 | Master with **`*CONFIGURE TV`** (interlace, vertical offset), then a hard reset | Kit default (write every CRTC register). Respecting the settings instead needs stability tests an emulator can't do; not worth it (hexwab) | jsbeeb: `*CONFIGURE TV 252,0`, hard reset | fixed | not checked |
| 12 | Master 128 **with LK18/LK19 not set**: two banks | Refuse, and say `(Set LK18 and LK19 west?)`. OSBYTE 0 with X=`&FF` returns 3 on the Master 128 only, not the Compact or ET | jsbeeb: poke `&02A7-&02A8` over RAM with an RTS at `&8003` | fixed | not checked |
| 13 | **Second processor**: B + 65C02, Master + 65C102 Turbo, Master 512 | Kit default (host addresses in both places). The game then overwrites the Tube host code; that's harmless only if it makes no filing-system call after taking the machine | jsbeeb `tube: true`; b-em presets 11, 12, 20 | loads into the host and plays | presumably breaks (its loader's block has the same zero bytes); not checked |
| 14 | **Master Compact** (ADFS, no DFS ROM) and the ADFS models | Can't read a DFS image at all. An ADFS version is real work, but **don't preclude it**: no `*DISC`, no `*TAPE` | b-em preset 13; jsbeeb `B1770A`, `MasterADFS` | not tried | not tried |
| 15 | Booted from **MMFS, ADFS or Econet** rather than DFS | Anything that forces DFS (`*DISC`) or unplugs the filing system (`*TAPE`) breaks it. Kit default: claim the NMI instead | b2 (MMFS); jsbeeb `MasterANFS` | fixed (intro's `*TAPE`/`*DISC` removed) | not checked |
| 16 | **`*CONFIGURE LANG 11`** (Edit) or **a B with no BASIC ROM** | `*EXEC !BOOT` fails: it types into Edit, or stops at "Language?". The fix is `*OPT 4,2` (`*RUN`): the game is entered with interrupts off (call OSBYTE 126 first) and reports errors by `BRK`, which works without a language. **It conflicts with the `!BOOT` stamp's `REM` lines**, so it's an open decision | jsbeeb: `*CONFIGURE LANG 11` and a hard reset | deliberately left open | not checked |
| 17 | **Real hardware** | Everything the emulators disagree about: the display below `&3000` under shadow, mid-frame CRTC writes, bank switches | a real machine | Master 128 (KC) | Master 128 |
| 18 | Electron | A different machine | - | out of scope (`PORTING.md` §2.2) | out of scope |

## What each emulator can and can't tell you

| Emulator | Use it for | Don't trust it for |
|---|---|---|
| **jsbeeb** (the MCP) | Everything scriptable: the B and Master models above, both second processors, `*SHADOW` and `*CONFIGURE` states, pokes into the ROM table. Every row marked jsbeeb above is a five-minute test | MMFS, B+, the Compact; the video below `&3000` under shadow (it disagrees with b-em) |
| **b2** | Watford DDFS, MMFS, a second opinion on a rupture | - |
| **b-em** | Its presets (4, 5, 9-13, 15, 17-20 are the interesting ones) | Its Watford DDFS preset (`-m19`) died where b2 runs; alternate-frame garbage below `&3000` under shadow |
| **MAME** | Expansion boards: Solidisk, Twomeg, Peartree MR4800, Watford ROM/RAM, third-party shadow | **The game itself**: its 6845 can't play Paradroid. Its Watford ROM/RAM board never sets its own write-select, so no probe can find a bank there (read in `weromram.cpp`). **Read MAME's source for a board before blaming the game** |

## Testing what the emulators can't run

- **A ROM image in sideways RAM** (ZMMFS and friends): poke the bank's `&02A1` byte non-zero,
  and give the bank a service entry that returns: `RTS` (`&60`) at `&8003`. Without it the MOS
  calls into zeros, BRKs, offers the BRK to the same bank and loops at `&8003`. Paradroid's
  version counted the service calls it got, which proved the image's last call was the NMI
  claim.
- **A refusal path on a machine with plenty of RAM**: hide banks the same way, or patch the
  probe's `CMP #4` thresholds in a `*LOAD`ed copy and `CALL` it.
- **A fresh machine per configuration.** `*SHADOW` needs a soft reset to take effect and a
  hard reset clears it. `*CONFIGURE` survives a hard reset. A machine that has run one test
  carries its state into the next.
- **Give the disc time.** jsbeeb's 1770 DFS takes more than 50 frames to load a file; a CPU
  in DFS's NMI code (`&0D00` up) is loading, not hung.
- **Say what wasn't tested.** Every Paradroid report on #18 carried "jsbeeb only, no human
  testing yet". That is the honest state of most rows above, and the release notes should say
  so.

## Recording it

One row per configuration the port has decided about, in `docs/decisions.md`:

```
| 7 | 2026-09-xx | **Second processors: load into the host, don't use the parasite.** Kit default kept. Tested: jsbeeb B + 65C02, Master + 65C102 | `tools/make_disc.py`, `src/lib/loader.6502` |
| 8 | 2026-09-xx | **Third-party shadow boards: not supported.** No test machine; MAME only | - |
```

"Not supported" is a fine answer. "Not considered" is not.
