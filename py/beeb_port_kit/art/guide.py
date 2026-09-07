"""
guide.py - the guide layer: a transparent overlay the same size as a piece
of art, carrying the grid the artist cannot see and the numbers he needs.

beeb-port-kit: from
  https://github.com/kieranhj/edge-beeb/blob/master/tools/art/guide.py
      the glyphs, the rules and the haloed text
  https://github.com/kieranhj/edge-beeb/blob/master/tools/art_grid.py
      grid(): the fat-pixel, cell and every-fourth rules and the numbering
      test, here taking any Sheet
Proven: Edge's five sheet guides and its level guide (paint_map.py --grid)
are this module's. Fork this into your project's tools/; keep this header.

It is always a SEPARATE FILE and never drawn into the picture. The picture is
read back as art, so a line drawn into it becomes art; a layer is turned off to
paint and turned on to look. sheets.read() refuses a file with any
transparency in it for exactly that reason (Image.convert("RGB") on an RGBA
guide would read its black as black - keep the guide beside the sheet).

Three things learned by building it wrong and looking at it:

  * solid against dotted separates two grids at one pixel where two alphas do
    not. The heavier grid is solid;
  * a number on artwork needs its own dark halo. The first ruler was white
    numerals on the top of the level, which is as often bright scenery as it is
    sky, and they were invisible;
  * and a number only belongs where the cell has room to spare for it. A
    character cell is 8 image pixels across; `FF` is 7 of them. Every fourth
    grid line brighter is a ruler that costs no pixels at all, and counting
    four at a time to the cell you want is quicker than reading a numeral that
    has buried the art underneath it.
"""

# A 3 x 5 digit. The tool's own, deliberately not the game's HUD font, which is
# the artist's to repaint and may stop being legible at any time.
GLYPHS = {
    "0": "###/#.#/#.#/#.#/###", "1": "..#/..#/..#/..#/..#",
    "2": "###/..#/###/#../###", "3": "###/..#/###/..#/###",
    "4": "#.#/#.#/###/..#/..#", "5": "###/#../###/..#/###",
    "6": "###/#../###/#.#/###", "7": "###/..#/..#/..#/..#",
    "8": "###/#.#/###/#.#/###", "9": "###/#.#/###/..#/###",
    "A": "###/#.#/###/#.#/#.#", "B": "##./#.#/##./#.#/##.",
    "C": "###/#../#../#../###", "D": "##./#.#/#.#/#.#/##.",
    "E": "###/#../###/#../###", "F": "###/#../###/#../#..",
    "$": ".#./###/##./.##/###",
}
GLYPH_W, GLYPH_H = 3, 5

MINOR = (255, 255, 255, 44)      # dotted: the finer grid
MAJOR = (255, 255, 255, 120)     # solid: the coarser one
EVERY4 = (255, 255, 255, 225)    # solid and bright: every fourth of those
LABEL = (255, 255, 255, 230)
HALO = (0, 0, 0, 230)


def text_width(text, scale_x):
    return (len(text) * (GLYPH_W + 1) - 1) * scale_x


def text(px, size, x0, y0, s, scale_x=1):
    """`s` at (x0, y0), each pixel `scale_x` wide so the label is in proportion
    with a 2:1 picture, haloed so it reads on anything."""
    w, h = size
    ink = set()
    x = x0
    for ch in s:
        for r, line in enumerate(GLYPHS[ch].split("/")):
            for c, v in enumerate(line):
                if v == "#":
                    ink |= {(x + c * scale_x + dx, y0 + r)
                            for dx in range(scale_x)}
        x += (GLYPH_W + 1) * scale_x
    halo = {(x + dx, y + dy) for x, y in ink
            for dx in (-1, 0, 1) for dy in (-1, 0, 1)} - ink
    for x, y in halo:
        if 0 <= x < w and 0 <= y < h:
            px[x, y] = HALO
    for x, y in ink:
        if 0 <= x < w and 0 <= y < h:
            px[x, y] = LABEL


def vrule(px, size, x, colour, dotted=False):
    w, h = size
    x = min(x, w - 1)
    for y in range(0, h, 2 if dotted else 1):
        px[x, y] = colour


def hrule(px, size, y, colour, dotted=False):
    w, h = size
    y = min(y, h - 1)
    for x in range(0, w, 2 if dotted else 1):
        px[x, y] = colour


def new(width, height):
    from PIL import Image
    im = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    return im, im.load(), (width, height)


def numbered(sheet):
    """Whether this sheet's cells get their index written in them.

    The test is HALF the cell's width, not all of it. Two earlier versions got
    this wrong in opposite directions: `$FF` overran an 8-pixel character cell
    and made every row of the charset one stripe, and `FF` fitted it exactly
    and buried the character underneath. A number belongs on a cell with room
    to spare for it - a sprite sheet, at 24 across - and nowhere else. What
    the small sheets get instead is the every-fourth rule in grid(), which is
    a ruler that costs no pixels."""
    sx, _ = sheet.scale
    return text_width(str(sheet.count - 1), 1) * 2 <= sheet.cell_w * sx


def grid(sheet):
    """The guide layer for a Sheet: (RGBA image, whether it was numbered).
    Save it beside the sheet under its own name - it is never read back."""
    w, h = sheet.size
    sx, sy = sheet.scale
    im, px, size = new(w, h)

    # The fat pixel grid: dotted, and the reason it is here is that a fat pixel
    # is sx image pixels wide and a half-pixel is an error the artist can only
    # avoid by seeing where the pairs begin.
    if sx > 1:
        for x in range(0, w + 1, sx):
            vrule(px, size, x, MINOR, dotted=True)
    if sy > 1:
        for y in range(0, h + 1, sy):
            hrule(px, size, y, MINOR, dotted=True)

    # Cell boundaries, and every fourth one brighter. That is the ruler on a
    # sheet too small to carry numerals: count four at a time.
    for cx in range(sheet.cols + 1):
        vrule(px, size, cx * sheet.cell_w * sx, EVERY4 if cx % 4 == 0 else MAJOR)
    for cy in range(sheet.rows + 1):
        hrule(px, size, cy * sheet.cell_h * sy, EVERY4 if cy % 4 == 0 else MAJOR)

    nums = numbered(sheet)
    if nums:
        for n in range(sheet.count):
            ox, oy = sheet.origin(n)
            text(px, size, ox + 1, oy + 1, str(n))
    return im, nums
