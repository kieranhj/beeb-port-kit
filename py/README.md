# beeb_port_kit (Python)

The Python tool code that was identical, or nearly, between two C64 -> BBC Micro ports -
[Paradroid](https://github.com/kieranhj/paradroid-beeb) (Model B) and
[Edge Grinder](https://github.com/kieranhj/edge-beeb) (Master 128) - pulled out so a third port
starts with it instead of rediscovering it. MIT, Kieran Connell.

## The fork-and-hack rule

**Copy the module you need into your project's `tools/` and change it there. Keep its header.**
Every module opens with a docstring that names the file(s) it came from, with GitHub links,
what was proved about it in the two ports, and the line *"Fork this into your project's tools/;
keep this header."* The header is the provenance: when your fork drifts from the kit, the next
person can still find the version that shipped twice and see what you changed.

It is also a package, so the tests can import it and so you can `pip install -e py/` while you
decide which modules you want. A project should not *depend* on it - the modules are short and
your game will want them changed.

Pillow is the only dependency, and only `art/`, `cpc/cpcscr.py` and `modes.render()` use it.
No library module imports either port's code; only the tests do, by path, and skip if the port is
not on the machine.

## What is here

| Module | What it is | From |
|---|---|---|
| `zx02.py` | **What a new port compresses with.** Daniel Serpell's ZX02 - his 6502-tuned fork of ZX0 - and a decompressor, in Python: the default stream (forwards, positive offsets, 8-bit gamma ending on a 0), the one `lib/zx02depack.6502` decodes. `compress()` matches the reference `zx02.exe` (which pads a trailing zero on some inputs); `decompress()` is the oracle every stream is round-tripped through before a disc is written. Why it, and not ZX0: half the depacker, 2.14x the decode speed, +0.11% on the packed size, measured over 43 real files from both ports - the module header has the numbers | new in the kit, from [dmsc/zx02](https://github.com/dmsc/zx02) (MIT) |
| `zx0.py` | Einar Saukas's ZX0 compressor and a decompressor, in Python: the default v2 stream (forwards, inverted new-offset MSB), the one `lib/zx0depack.6502` decodes. `compress()` is byte-identical to the reference `zx0.exe`, and slow; `decompress()` is the oracle both ports run every stream through before writing a disc. **Kept because the two shipping discs are ZX0 discs**; `dfs.compress(..., codec=zx0)` selects it | `tools/zx0.py`, byte-identical in [paradroid-beeb](https://github.com/kieranhj/paradroid-beeb/blob/main/tools/zx0.py) and [edge-beeb](https://github.com/kieranhj/edge-beeb/blob/master/tools/zx0.py) |
| `listing.py` | Baron's symbol dump (`--symbols`) and its `-v` listing: `symbols()` (every symbol as `name -> [address]` - labels, computed constants and the `ZA_AUTO` allocations that exist nowhere else; it reads either file, and a dump has far more in it), `values()` (the dump's non-numeric symbols too) and `opcode_stream()` (one entry per emitted instruction - opcode and operand length, no operand values - for `docs/verification.md`'s procedure 13, proving a change that moved addresses altered no instruction, and a listing only). `python -m beeb_port_kit.listing symbols build/game.symbols.json NAME` from the command line | new with Baron; the reducer both ports wrote inline and neither kept |
| `dfs.py` | Acorn DFS `.ssd` images: read the catalogue (`read_image` -> `Image` of `Entry`), lay files out in boot ACCESS order (`build_image`), pad to 200K, and the two checks a compressed disc needs before it is written: `check_stream` (a stream may not overlap its own output, and may not run past the screen it stages under) and `in_place_delta` (the margin a stream that unpacks over itself needs, measured by walking the decode) | the generic half of `tools/make_disc.py` in [paradroid-beeb](https://github.com/kieranhj/paradroid-beeb/blob/main/tools/make_disc.py) (`in_place_delta`) and [edge-beeb](https://github.com/kieranhj/edge-beeb/blob/master/tools/make_disc.py) (the overlap refusal) |
| `modes.py` | BBC bitmap modes 0/1/2/4/5: `pack_byte`/`unpack_byte` under the one rule (bit k of pixel n at `P*k + (P-1-n)`), the ports' own names `mode1_byte`, `unpack_mode1`, `mode2_byte`, `mode2_unpack`; the eight physical colours and their luma; `dither_pair`, Rich Talbot-Watkins's rule for approximating a richer palette with two MODE 2 colours checkerboarded; `render`/`unrender` between screen memory and a PIL image | [paradroid-beeb `export_bbc.py`](https://github.com/kieranhj/paradroid-beeb/blob/main/tools/export_bbc.py), [`verify_bbc.py`](https://github.com/kieranhj/paradroid-beeb/blob/main/tools/verify_bbc.py); [edge-beeb `bbc.py`](https://github.com/kieranhj/edge-beeb/blob/master/tools/bbc.py) |
| `c64.py` | The C64 side: Pepto's palette, hires and multicolour byte decoding, 24x21 sprite blocks, 8x8 charsets, flat tables, and two source readers - `parse_c64_table` (the `!byte`/`.byte` operands under a label in an ACME/TASS source, with `$xx + n` sums and named constants) and `parse_listing` (an IDA `.BYTE` listing into a 64K image, with the running offset a continuation line needs) | [edge-beeb `bbc.py`](https://github.com/kieranhj/edge-beeb/blob/master/tools/bbc.py), [`export_waves.py`](https://github.com/kieranhj/edge-beeb/blob/master/tools/export_waves.py); [paradroid-beeb `export_bbc.py`](https://github.com/kieranhj/paradroid-beeb/blob/main/tools/export_bbc.py), [`rip_graphics.py`](https://github.com/kieranhj/paradroid-beeb/blob/main/tools/rip_graphics.py), [`export_title.py`](https://github.com/kieranhj/paradroid-beeb/blob/main/tools/export_title.py) |
| `art/sheets.py` | An artist's PNG sheet of cells as logical colours and back. A `Sheet` carries its geometry (cell size, grid, count, scale, mode), the logical colours it may resolve to, and whether the transparency key is legal on it. `read()` refuses a half-width fat pixel, an off-palette RGB, a disallowed one, or a translucent file (a guide layer) - with sheet, cell and pixel, never a nearest match. `pack_cell` packs a cell in column order (a MODE 2 character is its sixteen bytes); `merge` fills not-drawn-yet cells from a mechanical conversion | [edge-beeb `art/sheets.py`](https://github.com/kieranhj/edge-beeb/blob/master/tools/art/sheets.py), [`art/pngart.py`](https://github.com/kieranhj/edge-beeb/blob/master/tools/art/pngart.py) |
| `art/palette.py` | The palette as an Nx1 PNG; RGB -> logical with the aliasing rule (lowest allowed index wins, per sheet); the two reserved keys (grey 96,96,96 transparent, orange 255,128,0 not-drawn-yet); `to_fe21` for the Video ULA and `to_nula` for a VideoNuLA; `.gpl` and `.act` exports for the artist's tools | [edge-beeb `art/palette.py`](https://github.com/kieranhj/edge-beeb/blob/master/tools/art/palette.py) |
| `art/guide.py` | The guide layer: a transparent RGBA overlay the size of a sheet with the fat-pixel grid dotted, cell boundaries solid, every fourth brighter, and cell numbers only where the cell has room for them. Always a separate file, never drawn into the art | [edge-beeb `art/guide.py`](https://github.com/kieranhj/edge-beeb/blob/master/tools/art/guide.py), [`art_grid.py`](https://github.com/kieranhj/edge-beeb/blob/master/tools/art_grid.py) |
| `cpc/dsk.py` | Amstrad CPC `.dsk` (standard and Extended) and the AMSDOS catalogue, for reading a CPC port's work discs; `amsdos_header`/`strip_amsdos` | [edge-beeb `cpc/dsk.py`](https://github.com/kieranhj/edge-beeb/blob/master/tools/cpc/dsk.py) |
| `cpc/cpcscr.py` | CPC screens: the 27 firmware colours and the Gate Array table, mode 0/1/2 byte packing, the 16K screen's scanline interleave, OCP `.PAL` files, rendered to PIL | [edge-beeb `cpc/cpcscr.py`](https://github.com/kieranhj/edge-beeb/blob/master/tools/cpc/cpcscr.py) |

What is deliberately NOT here: anything that is a game's. Which files ship compressed and where
they stage, the tile and map formats, the sprite box tables, the panel layout, the wave table -
those are the project's exporters, and both ports' `tools/` show what they look like.

## Running the tests

From `py/`:

```
python -m unittest discover -s tests -v
```

or, with pytest installed, `python -m pytest -q`. The tests need Pillow. Some of them compare the
kit against the two ports' own tools (`dither_pair` against Edge's `bbc.py`, `in_place_delta`
against Paradroid's `make_disc.py`, `unpack_mode1` against its `verify_bbc.py`, `parse_c64_table`
over Edge's C64 source) and each compressor against its reference exe ([`zx02.exe`](https://github.com/dmsc/zx02/releases), `zx0.exe`); each of those reads
the other repository by path and **skips** if it is absent. `tests/paths.py` holds the paths;
override them with the `EDGE_BEEB`, `PARADROID_BEEB`, `ZX0_EXE` and `ZX02_EXE` environment variables. No test
writes into either port.

## Driving `dfs.py` from a project's `make_disc.py`

`examples/make_disc_example.py` is the whole shape; a real one has longer tables. The project owns
three things, all of which must agree with `src/main.asm`'s loader:

```python
from beeb_port_kit import dfs

DEPK_STREAM = 0x3000                                  # where the loader *LOADs a stream
COMPRESSED = {"BANK0": (DEPK_STREAM, 0x8000),         # name: (stream address, unpack destination)
              "BANK1": (DEPK_STREAM, 0x8000)}
STREAM_TOP = {DEPK_STREAM: 0x8000}                    # what a stream may not run past
LAYOUT = ["!BOOT", "GAME", "BANK0", "BANK1"]          # boot ACCESS order, so the head never seeks back

exe = "bin/zx02"                                      # ONE compressor, always - see below
img = dfs.read_image("build/game-raw.ssd")            # the assembler's own image
for name, (stream, dest) in COMPRESSED.items():
    entry = img.files[name]
    packed = dfs.compress(entry.data, exe, name)      # ZX02, round-tripped through zx02.decompress()
    dfs.check_stream(name, stream, packed, dest, entry.data, top=STREAM_TOP[stream])
    entry.replace(packed, load=stream, exec=stream)   # the catalogue now says where it stages
out = dfs.build_image(img.files, LAYOUT, img.title, img.cycle, img.opt)
open("build/game.ssd", "wb").write(out)
open("build/game-200k.ssd", "wb").write(dfs.pad(out))  # only when publishing: see pad()
```

`check_stream` raises `DiscError` if the stream would run past `top` or overlap its own output.
For a stream that must unpack over itself (Paradroid's font, which lands at `&3700` and unpacks
to `&3000`), pass `in_place=True`: it then requires `stream >= dest + in_place_delta(packed)`,
the margin measured by walking that particular stream's decode.

**Pick one compressor and always use it.** `compress(raw, None)` runs `zx02.py`, which ends one
byte short of the reference on some inputs. A build that uses whichever is installed makes a
disc that depends on the machine. The template builds the reference from vendored source
(`template/tools/zx02src/`, `../docs/build-portability.md` rule 14).

**Comparing two images:** `python -m beeb_port_kit.dfs compare a.ssd b.ssd [--ignore INFO --ignore !BOOT]`
(`INFO` is the kit's build stamp as a disc file, and a release `!BOOT` reprints it, so both carry the time)
prints both SHA256s, then says either "identical images" or which file differs and how.

**Host addresses for a disc built without `make_disc.py`:** `python -m beeb_port_kit.dfs host
image.ssd` rewrites the image in place with every catalogue load and exec address set to
`&FFFFxxxx`. The assemblers write 16-bit addresses, which a second processor reads as the
parasite's. The template's vscroll example does this in its `build.ps1`.

**The assembler's own image is not bootable** once the loader expects compressed streams. Hand the image
this writer produces to the emulator, never the raw one.
