# PLAN.md

The live plan. One paragraph per layer, revised as work proceeds; the layer numbering is
`../PORTING.md` §4's. A layer is done when it is visible in the emulator and its `docs/` file,
its `docs/decisions.md` rows and this page are written.

## State

Layer 0 done (2026-09-07). Nothing of the game exists yet: the template boots, shows a panel over
a scrolling strip at 25 Hz, **each in a palette of its own so all eight MODE 1 colours are up at
once** (decision 4, added the same day at KC's request), and every kit piece has run once.

## Layers

| # | Layer | Status |
|---|---|---|
| 0 | **Toolchain.** Repo layout, build script, disc post-processor, emulator connected, docs skeleton | **DONE** - `docs/layer-0-toolchain.md` |
| 1 | **Data pipeline.** Rip the original's graphics and tables, convert offline, commit to `src/data/`, render back to PNG to check | TODO |
| 2 | **Display.** Screen mode, the rupture for the panel, own IRQ handler, frame lock, palette, direct keyboard | TODO - the template is a head start: re-cut the geometry to the original's and re-measure the T1 constants, `T1_TUNE2` (the palette switch's phase) with them. The two-palette split is in; a port that keeps it keeps the panel's last scanline blank |
| 3 | **Scroll or render.** The play area from the map; the buffer oracle | TODO |
| 4 | **Sprites.** The engine, measured: cycles per sprite, slots, save and restore | TODO |
| 5 | **Player.** Movement, controls, background collisions, the original's speed model | TODO |
| 6 | **Enemies.** The original's tables verbatim, its AI or wave manager, combat | TODO |
| 7 | **Game flow.** Lives, score, HUD, state machine, titles, game over, completion | TODO |
| 8 | **Sound and music.** | TODO |
| 9 | **Loader and disc.** Compression, load order, boot blanking, loading screen | TODO - the loader, depacker and disc builder are in; the load order and the loading screen are not |
| 10 | **Art.** The hand-authored pass and its pipeline | TODO |
| 11 | **Balance, memory, compatibility.** | TODO |
| 12 | **Release.** Release build, redefinable keys, pause, the padded disc, publication | TODO |

## Parked

- An aligned switch into the rupture (Paradroid's `RuptAlign`): the template writes the B shape
  and installs the IRQ under an R8 blank, which costs a malformed field or two that jsbeeb does
  not show and b2 would. Port it when the boot sequence is real (Layer 9).
- `FRAME_DROP_ROWS` on a tube: Paradroid's 3 is inherited, not measured for this picture.
