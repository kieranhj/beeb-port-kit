"""
palette.py - the game palette as a PNG, and the mapping between the RGB an
artist paints and the logical colour the hardware shows.

beeb-port-kit: from
  https://github.com/kieranhj/edge-beeb/blob/master/tools/art/palette.py
generalised: the entry count, the two reserved keys and the sheet's allowed
set are parameters rather than Edge's constants. Proven: Edge Grinder's
five art sheets and its palette.asm go through this; the aliasing rule
(lowest allowed index wins) is what let its title font fade on the palette
alone while the panel stayed lit (its decision 53). Fork this into your
project's tools/; keep this header.

The palette PNG is N pixels wide, 1 tall, pixel n being the RGB of logical
colour n. Everything that reads the artist's sheets resolves colour through
this file and nothing else - an RGB that is not in it is an error with
coordinates, never a nearest match.

Two RGBs are NOT colours and may not appear in the palette:

  * the transparency key (default grey 96,96,96): see-through on a sheet
    that allows it, an error on one that does not;
  * the not-drawn-yet key (default orange 255,128,0): a cell painted
    entirely in it is 'not done', and the exporter falls back to the
    mechanical conversion for it, so a partial drop still builds.

Because entries can alias (MODE 2's 8-15 are 0-7 again, and a sprite
engine wants a second black that is not its transparency key), RGB ->
logical needs a rule, and the rule is per sheet: each carries the set of
logical colours it is ALLOWED to resolve to, and an RGB takes the LOWEST
index in that set. An RGB that is in the palette but not in a sheet's
allowed set is an error naming both, not a silent substitution.
"""

import os

from PIL import Image

from .. import modes

KEY_TRANSPARENT = (96, 96, 96)
KEY_FALLBACK = (255, 128, 0)


class PaletteError(ValueError):
    pass


def reserved(key_transparent=KEY_TRANSPARENT, key_fallback=KEY_FALLBACK):
    return {key_transparent: "transparency key", key_fallback: "not-yet-drawn key"}


def seed(mode=2):
    """The palette a MODE's logical colours show under the MOS's default
    &FE21 setup, as `entries(mode)` RGB triples. MODE 2: 0-7 physical, 8 a
    second black, 9-15 aliasing 1-7 (the shape both ports' setup_display
    wrote)."""
    if mode == 2:
        return [modes.BBC_RGB[n] for n in range(8)] + [modes.BBC_RGB[0]] + \
               [modes.BBC_RGB[n] for n in range(1, 8)]
    return modes.default_palette(mode)


def entries(mode=2):
    return 1 << modes.MODE_INFO[mode][1]


def load(path, count=16, keys=None):
    """The `count` entries as RGB triples. A reserved key in the palette is
    refused - it could never be painted."""
    keys = reserved() if keys is None else keys
    with Image.open(path) as src:
        im = src.convert("RGB")
    if im.size != (count, 1):
        raise PaletteError(f"{path}: expected {count}x1, got {im.size[0]}x{im.size[1]}")
    pal = [im.getpixel((n, 0)) for n in range(count)]
    for n, rgb in enumerate(pal):
        if rgb in keys:
            raise PaletteError(f"{path}: entry {n} is the {keys[rgb]} {rgb}, "
                               "which may not be a palette colour")
    return pal


def save(pal, path):
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)
    im = Image.new("RGB", (len(pal), 1))
    for n, rgb in enumerate(pal):
        im.putpixel((n, 0), tuple(rgb))
    im.save(path)


def lookup(pal, allowed=None):
    """RGB -> logical colour, restricted to `allowed` (default: every entry).
    The lowest allowed index with that RGB wins."""
    allowed = range(len(pal)) if allowed is None else allowed
    out = {}
    for n in sorted(allowed, reverse=True):
        out[tuple(pal[n])] = n
    return out


def is_physical(pal):
    """True if every entry is one of the eight BBC colours, so the palette
    is legal without a VideoNuLA."""
    return all(tuple(c) in modes.BBC_RGB for c in pal)


def to_fe21(pal):
    """The bytes setup_display writes to &FE21: for each logical n, the
    physical colour, as (n << 4) | (physical ^ 7). Requires is_physical()."""
    if not is_physical(pal):
        raise PaletteError("palette has colours MODE 2 cannot show; use to_nula()")
    return bytes((n << 4) | (modes.BBC_RGB.index(tuple(c)) ^ 7)
                 for n, c in enumerate(pal))


def to_nula(pal):
    """The bytes for &FE23 under VideoNuLA logical mapping (&FE22 = &11):
    two per entry, [index<<4 | red] then [green<<4 | blue], 4 bits each.
    The encoding is the VideoNuLA User Guide's, proved against its worked
    example in edge-beeb's export_palette.py."""
    out = bytearray()
    for n, (r, g, b) in enumerate(pal):
        out += bytes(((n << 4) | (r >> 4), ((g >> 4) << 4) | (b >> 4)))
    return bytes(out)


def gpl(pal, name, keys=None):
    """A GIMP palette file (GIMP, Aseprite, Krita read it)."""
    keys = reserved() if keys is None else keys
    lines = ["GIMP Palette", f"Name: {name}", "Columns: 8", "#"]
    for n, (r, g, b) in enumerate(pal):
        lines.append(f"{r:3d} {g:3d} {b:3d}\tlogical {n}")
    for rgb, what in keys.items():
        lines.append(f"{rgb[0]:3d} {rgb[1]:3d} {rgb[2]:3d}\t{what} (NOT a colour)")
    return "\n".join(lines) + "\n"


def act(pal):
    """Adobe colour table: 256 RGB triples, which Aseprite and GIMP both read."""
    out = bytearray()
    for r, g, b in pal:
        out += bytes((r, g, b))
    return bytes(out) + bytes(3 * (256 - len(pal)))
