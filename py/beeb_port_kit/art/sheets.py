"""
sheets.py - an artist's PNG sheet of cells as BBC logical colours, and back.

beeb-port-kit: from
  https://github.com/kieranhj/edge-beeb/blob/master/tools/art/sheets.py
      Sheet, read (with the fat-pixel, key and allowed-set checks), write,
      pack_cell
  https://github.com/kieranhj/edge-beeb/blob/master/tools/art/pngart.py
      merge (the not-drawn-yet fallback)
generalised: cell size, grid, scale, mode and the two keys are the Sheet's
parameters, and read() refuses a file with translucent pixels (Edge's
paint_map.py import did that; here every sheet gets it). Edge's five named
sheets, its HUD-cell warning and its starfield rule are gone. Proven: Edge Grinder's characters, sprites, panel,
HUD font and title font are read from PNG through read() and pack_cell(),
and its validate_art.py --roundtrip proves write() then read() loses nothing.
Fork this into your project's tools/; keep this header.

A sheet is drawn at `scale` = (sx, sy) image pixels per screen pixel - (2, 1)
for MODE 2 and 5, where a screen pixel is twice as wide as it is tall, so a
2:1 PNG shows the aspect the Beeb does. Every screen pixel must therefore be
a uniform sx x sy block; a block that is not is an error with coordinates,
never a guess (an artist working in a 1:1 view of a 2:1 sheet produces
half-width pixels without noticing, and a nearest-match would hide it).

Cells are numbered left to right, top to bottom, `cols` a row. read()
returns `count` cells, each `cell_h` rows of `cell_w` logical colours, or
None for a cell painted entirely in the not-drawn-yet key.
"""

import os

from PIL import Image

from .. import modes
from . import palette as _palette


class ArtError(ValueError):
    """Bad art, with the sheet, cell and pixel in the message."""


class Sheet:
    """One sheet's geometry and rules.

    cell_w, cell_h  screen pixels across and rows down one cell
    cols, rows      cells across and down the sheet
    allowed         logical colours this sheet may resolve to (default all)
    scale           image pixels per screen pixel, (x, y)
    transparent     whether the transparency key is legal here (sprites)
    count           cells the game reads (default cols * rows)
    mode            the BBC mode pack_cell() packs for
    key_transparent, key_fallback   the two reserved RGBs
    """

    def __init__(self, cell_w, cell_h, cols, rows, allowed=None, scale=(2, 1),
                 transparent=False, count=None, mode=2, path=None,
                 key_transparent=_palette.KEY_TRANSPARENT,
                 key_fallback=_palette.KEY_FALLBACK):
        self.cell_w, self.cell_h = cell_w, cell_h
        self.cols, self.rows = cols, rows
        self.allowed = None if allowed is None else frozenset(allowed)
        self.scale = tuple(scale)
        self.transparent = transparent
        self.count = cols * rows if count is None else count
        self.mode = mode
        self.path = path
        self.key_transparent = tuple(key_transparent)
        self.key_fallback = tuple(key_fallback)
        if self.count > cols * rows:
            raise ValueError(f"count {self.count} exceeds {cols}x{rows} cells")

    @property
    def size(self):
        sx, sy = self.scale
        return (self.cols * self.cell_w * sx, self.rows * self.cell_h * sy)

    def origin(self, n):
        sx, sy = self.scale
        return ((n % self.cols) * self.cell_w * sx,
                (n // self.cols) * self.cell_h * sy)

    def keys(self):
        return {self.key_transparent: "transparency key",
                self.key_fallback: "not-yet-drawn key"}


def read(sheet, path=None, pal=None, strict=True):
    """The sheet as `count` cells of `cell_h` rows of `cell_w` logical colours.

    A cell drawn entirely in the not-yet-drawn key comes back as None, so the
    caller can fall back to a mechanical conversion for it (partial drops).
    strict=True raises ArtError listing the first errors; strict=False
    returns (cells, errors) with every (path, cell, x, y, message).
    """
    path = path or sheet.path
    pal = _palette.seed(sheet.mode) if pal is None else pal
    lut = _palette.lookup(pal, sheet.allowed)
    full = _palette.lookup(pal)
    with Image.open(path) as src:
        if "A" in src.getbands() and src.getchannel("A").getextrema()[0] < 255:
            raise ArtError(f"{path}: has transparent pixels, so it is a guide layer, "
                           "not a sheet - reading it as RGB would take its black for ink")
        im = src.convert("RGB")
    if im.size != sheet.size:
        raise ArtError(f"{path}: expected {sheet.size[0]}x{sheet.size[1]}, "
                       f"got {im.size[0]}x{im.size[1]}")
    px = im.load()
    sx, sy = sheet.scale
    cells, errors = [], []
    for n in range(sheet.count):
        ox, oy = sheet.origin(n)
        rows, blanks, drawn = [], 0, 0
        for y in range(sheet.cell_h):
            row = []
            for x in range(sheet.cell_w):
                block = {px[ox + x * sx + dx, oy + y * sy + dy]
                         for dx in range(sx) for dy in range(sy)}
                if len(block) != 1:
                    errors.append((path, n, x, y,
                                   f"fat pixel is not one colour: {sorted(block)}"))
                    rgb = sorted(block)[0]
                else:
                    rgb = block.pop()
                if rgb == sheet.key_fallback:
                    blanks += 1
                    row.append(0)
                    continue
                drawn += 1
                if rgb == sheet.key_transparent:
                    if not sheet.transparent:
                        errors.append((path, n, x, y,
                                       "the transparency key is not legal on this sheet"))
                    row.append(0)
                elif rgb in lut:
                    row.append(lut[rgb])
                elif rgb in full:
                    errors.append((path, n, x, y,
                                   f"{rgb} is palette entry {full[rgb]}, which this "
                                   f"sheet may not use; it is restricted to "
                                   f"entries {sorted(sheet.allowed)}"))
                    row.append(0)
                else:
                    errors.append((path, n, x, y, f"{rgb} is not in the palette"))
                    row.append(0)
            rows.append(row)
        if drawn == 0:
            cells.append(None)                    # not drawn yet
        else:
            if blanks:
                errors.append((path, n, -1, -1,
                               f"{blanks} pixels of the not-yet-drawn key in a cell "
                               "that is otherwise painted: a fallback cell must be "
                               "the key and nothing else"))
            cells.append(rows)
    if errors and strict:
        lines = []
        for p, n, x, y, msg in errors[:40]:
            where = f"cell {n}" + (f" pixel ({x},{y})" if x >= 0 else "")
            lines.append(f"{p}: {where}: {msg}")
        raise ArtError(f"{path}: {len(errors)} error(s)\n" + "\n".join(lines))
    return (cells, errors) if not strict else cells


def write(sheet, cells, pal=None, path=None):
    """Cells of logical colours out to a PNG in the sheet's own format.
    A None cell is written in the not-yet-drawn key; on a transparent sheet
    logical 0 is written as the transparency key."""
    path = path or sheet.path
    pal = _palette.seed(sheet.mode) if pal is None else pal
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)
    sx, sy = sheet.scale
    fill = sheet.key_transparent if sheet.transparent else tuple(pal[0])
    im = Image.new("RGB", sheet.size, fill)
    px = im.load()
    for n, rows in enumerate(cells[:sheet.count]):
        ox, oy = sheet.origin(n)
        for y in range(sheet.cell_h):
            for x in range(sheet.cell_w):
                if rows is None:
                    rgb = sheet.key_fallback
                elif sheet.transparent and rows[y][x] == 0:
                    rgb = sheet.key_transparent
                else:
                    rgb = tuple(pal[rows[y][x]])
                for dy in range(sy):
                    for dx in range(sx):
                        px[ox + x * sx + dx, oy + y * sy + dy] = rgb
    im.save(path)
    return path


def pack_cell(cell, mode=2):
    """A cell (rows of logical colours) as screen bytes in COLUMN order: byte
    column 0's rows top to bottom, then byte column 1's, and so on. For a
    cell 8 rows high that is exactly its screen memory (a MODE 2 character
    is two byte columns of 8 = sixteen contiguous bytes; a MODE 1 one is
    two as well, of four pixels each). Taller cells are the sprite engine's
    business and it unpacks them how it likes."""
    P = modes.pixels_per_byte(mode)
    w = len(cell[0])
    if w % P:
        raise ValueError(f"a {w}-pixel row does not divide into MODE {mode} bytes")
    return bytes(modes.pack_byte(row[bc * P:(bc + 1) * P], mode)
                 for bc in range(w // P) for row in cell)


def unpack_cell(data, cell_w, cell_h, mode=2):
    """The inverse of pack_cell."""
    P = modes.pixels_per_byte(mode)
    cols = cell_w // P
    rows = [[] for _ in range(cell_h)]
    i = 0
    for bc in range(cols):
        for y in range(cell_h):
            rows[y] += modes.unpack_byte(data[i], mode)
            i += 1
    return rows


def merge(cells, fallback, what="cell", log=print):
    """Cells read from a sheet with the None ones taken from `fallback`
    (the mechanical conversion of the same thing), so a partial drop
    still builds a complete game."""
    out, missing = [], 0
    for n, c in enumerate(cells):
        if c is None:
            missing += 1
            if fallback is None:
                raise ArtError(f"{what} {n} is not drawn and there is no fallback")
            out.append(fallback[n])
        else:
            out.append(c)
    if missing and log:
        log(f"  {missing}/{len(cells)} {what}s not drawn yet: fallback used for those")
    return out
