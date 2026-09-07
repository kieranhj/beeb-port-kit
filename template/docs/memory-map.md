# The memory map, and what is left in it

Figures are from the build listing of 2026-09-07 (`build/GAME.lst`, the `PRINT` block at its
end). They go stale the moment anything grows: take live numbers from the listing.

## Main RAM, BBC Model B

| Range | Bytes | Contents | Free |
|---|---|---|---|
| `&0000-&001C` | 29 | zero page, ours, wiped at boot: the depacker's six slots first (the pass-1 trap), then the rupture's and the loop's state. `GUARD &90` | 115 to `&90` |
| `&0090-&00FF` | | MOS and DFS zero page | - |
| `&0100-&01FF` | | stack | - |
| `&0200-&03FF` | | MOS vectors and workspace; `IRQ1V` (`&0204`) is ours outright | - |
| `&0400-&0DFF` | | language and MOS workspace: ours once `*RUN` has handed over and the MOS tick is gone (`&0800-&0BFF` is the sound/serial/soft-key space both ports reclaimed). Unused here | all of it, unverified for this program |
| `&0E00-&18FF` | 2,816 | DFS's workspace on a Model B (PAGE = `&1900`). Live until the last load returns; free after `install_irq`. Unused here | after boot |
| `&1900-&1DBD` | 1,213 | the code image (1,264 under `MASTER=1`; 1,036 before the two palettes): `main`, the loop, `setup_display`, `fill_play`, the rupture, the forked lib, the depacker, the OSFILE block | `&1243` = 4,675 to `&3000` |
| `&3000-&49FF` | 6,656 | the screen's top: **`LOADER_STAGE`** at boot (the `PANEL` stream, 54 bytes, blanked by R8). Displayed by nothing once the rupture runs | all of it in play |
| `&4A00-&53FF` | 2,560 | the panel, 4 rows, rupture cycle A | 0 |
| `&5400-&57FF` | 1,024 | between the panel and the strip. Displayed by nothing | 1,024 |
| `&5800-&7FFF` | 10,240 | the play strip, 16 rows, the 10K hardware ring, rupture cycle B | 0 |
| `&7E00-&7EFF` | | where `!BOOT` is **assembled** (inside the strip, which does not exist at assembly time); never loaded there | - |
| `&8000-&BFFF` | 16K | sideways ROM/RAM, paged by `ROMSEL`. Unused here; `../lib/swram_probe.asm` finds the RAM banks on a B | - |

## Master 128 (`MASTER=1`)

The same map. Shadow RAM, ANDY (`&8000-&8FFF`, ROMSEL bit 7) and HAZEL (`&C000-&DFFF`, ACCCON
bit 3) are all untouched; `loader.asm`'s `load_hazel` and `unpack_andy` assemble and are not
called. `MODE 1` (not 129) keeps the display in main RAM.
