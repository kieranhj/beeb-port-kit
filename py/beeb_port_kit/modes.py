"""
modes.py - BBC Micro bitmap modes: the pixel-to-bit packing of MODE 0, 1, 2,
4 and 5, the eight physical colours, RTW's dither pairs, and a renderer that
turns a block of screen memory into a PIL image and back.

beeb-port-kit: from
  https://github.com/kieranhj/paradroid-beeb/blob/main/tools/export_bbc.py
      mode1_byte (MODE 1 pixel n: high bit at 7-n, low bit at 3-n)
  https://github.com/kieranhj/paradroid-beeb/blob/main/tools/verify_bbc.py
      unpack_mode1, its inverse
  https://github.com/kieranhj/edge-beeb/blob/master/tools/bbc.py
      BBC_RGB, BBC_LUMA, mode2_byte / mode2_unpack (left pixel bits 7,5,3,1,
      right pixel 6,4,2,0) and dither_pair
Proven: every character, sprite and panel cell on both shipping discs went
through mode1_byte or mode2_byte, and both games' verification oracles
(verify_bbc.py, verify_compiled.py) unpack the emulator's buffer with the
inverse and diff byte for byte. dither_pair reproduces every cell of Rich
Talbot-Watkins's chart of the 27 CPC colours
(edge-beeb/reference/cpc-palette-map-to-bbc-mode2.png); tests/test_modes.py
compares it against Edge's bbc.py when that repo is present.
Fork this into your project's tools/; keep this header.

The one rule under all five modes: a byte holds P pixels of B bits each
(P * B = 8), and bit k of pixel n (n = 0 leftmost, k = 0 least significant)
is at bit position P * k + (P - 1 - n). MODE 0/4: P = 8, B = 1. MODE 1/5:
P = 4, B = 2. MODE 2: P = 2, B = 4. MODE 3, 6 and 7 are not bitmap modes.

Screen memory order (what render() and unrender() assume): a character row
is `width_bytes` cells of 8 bytes, one byte per scanline, so the byte at
(cell x, character row r, scanline s) is at r * width_bytes * 8 + x * 8 + s.
That is the linear order the CRTC fetches under the MOS's setup and what
an INCBIN of a screen dump holds. Hardware scrolling wraps it; this
module does not.
"""

# pixels per byte and bits per pixel, by MODE number
MODE_INFO = {0: (8, 1), 1: (4, 2), 2: (2, 4), 4: (8, 1), 5: (4, 2)}

# The physical colours, in hardware order: bit 0 red, bit 1 green, bit 2 blue.
BBC_RGB = [
    (0, 0, 0), (255, 0, 0), (0, 255, 0), (255, 255, 0),
    (0, 0, 255), (255, 0, 255), (0, 255, 255), (255, 255, 255),
]
BLACK, RED, GREEN, YELLOW, BLUE, MAGENTA, CYAN, WHITE = range(8)
BBC_NAMES = ["black", "red", "green", "yellow", "blue", "magenta", "cyan", "white"]

# Rec.601 luma of each, the brightness the dither tie-break uses.
BBC_LUMA = [0.299 * r + 0.587 * g + 0.114 * b for r, g, b in BBC_RGB]


def pixels_per_byte(mode):
    return MODE_INFO[mode][0]


def default_scale(mode):
    """Image pixels per screen pixel, (x, y), at which the mode's pixels are
    square-ish on a monitor: MODE 2 and 5 are 2:1, the others 1:1."""
    return (2, 1) if mode in (2, 5) else (1, 1)


def pack_byte(pixels, mode):
    """`pixels` (P logical colours, left to right) as one screen byte."""
    P, B = MODE_INFO[mode]
    if len(pixels) != P:
        raise ValueError(f"MODE {mode} packs {P} pixels a byte, got {len(pixels)}")
    out = 0
    for n, c in enumerate(pixels):
        if c >> B:
            raise ValueError(f"colour {c} does not fit MODE {mode}'s {B} bits")
        for k in range(B):
            if (c >> k) & 1:
                out |= 1 << (P * k + (P - 1 - n))
    return out


def unpack_byte(b, mode):
    """One screen byte as its P logical colours, left to right."""
    P, B = MODE_INFO[mode]
    return [sum(((b >> (P * k + (P - 1 - n))) & 1) << k for k in range(B))
            for n in range(P)]


# The two ports' own names, kept so forked exporters read unchanged.

def mode1_byte(pixels):
    """Pack four logical colours (0-3) into one MODE 1 byte, left to right.
    MODE 1 pixel n: high colour bit at (7-n), low bit at (3-n)."""
    return pack_byte(pixels, 1)


def unpack_mode1(b):
    """One MODE 1 byte -> its four pixel colours, left to right."""
    return unpack_byte(b, 1)


def mode2_byte(left, right):
    """Pack two 4-bit logical colours into one MODE 2 byte.
    Left pixel takes bits 7,5,3,1; right pixel bits 6,4,2,0."""
    return pack_byte((left, right), 2)


def mode2_unpack(b):
    return tuple(unpack_byte(b, 2))


# --- dithering --------------------------------------------------------------
#
# A source palette richer than MODE 2's eight (the CPC's 27, the C64's 16)
# can be approximated by a PAIR of BBC colours checkerboarded a pixel at a
# time. The rule is Rich Talbot-Watkins's (Edge Grinder decision 55):
#
#   of the 36 unordered pairs of the eight MODE 2 colours, take those whose
#   per-channel average is nearest the target, and among those choose the two
#   closest in brightness; then order the pair darkest first.
#
# The two tie-breaks are what stop the flat mapping's damage. Nearest-average
# alone leaves ties everywhere on the middle levels - mid grey is red+cyan as
# readily as magenta+green - and the closest-in-brightness pair is the one that
# reads as a colour rather than as two colours.
#
# The checkerboard should be (x + y) & 1 in the ART's coordinates, baked into
# the bitmaps, so it travels with the scenery as it scrolls instead of
# crawling over it.

def dither_pair(rgb):
    """One RGB triple as (dark, light), two BBC physical colours to checkerboard.
    A colour MODE 2 has exactly returns that colour twice."""
    best = None
    for a in range(8):
        for b in range(a, 8):
            err = sum(((BBC_RGB[a][k] + BBC_RGB[b][k]) / 2 - rgb[k]) ** 2
                      for k in range(3))
            key = (err, abs(BBC_LUMA[a] - BBC_LUMA[b]))
            if best is None or key < best[0]:
                best = (key, (a, b))
    a, b = best[1]
    return (a, b) if BBC_LUMA[a] <= BBC_LUMA[b] else (b, a)


def dithered(rgb, x, y):
    """The BBC colour at art coordinate (x, y) for a dithered `rgb`."""
    pair = dither_pair(rgb)
    return pair[(x + y) & 1]


def nearest(rgb):
    """The single nearest BBC physical colour (no dither)."""
    return min(range(8), key=lambda c: sum((BBC_RGB[c][k] - rgb[k]) ** 2
                                           for k in range(3)))


# --- rendering ----------------------------------------------------------------

def default_palette(mode):
    """Logical -> RGB as the MOS sets the mode up: MODE 2 logical n is
    physical n & 7 (8-15 flash, drawn here as their steady colour); MODE 1/5
    is black, red, yellow, white; MODE 0/4 black and white."""
    if mode == 2:
        return [BBC_RGB[n & 7] for n in range(16)]
    if mode in (1, 5):
        return [BBC_RGB[c] for c in (BLACK, RED, YELLOW, WHITE)]
    return [BBC_RGB[BLACK], BBC_RGB[WHITE]]


def to_pixels(data, mode, width_bytes, rows):
    """Screen memory -> list of scanlines, each a list of logical colours."""
    P = pixels_per_byte(mode)
    need = width_bytes * rows * 8
    if len(data) < need:
        raise ValueError(f"need {need} bytes for {rows} rows of {width_bytes}, "
                         f"got {len(data)}")
    lines = []
    for r in range(rows):
        for s in range(8):
            line = []
            for x in range(width_bytes):
                line += unpack_byte(data[r * width_bytes * 8 + x * 8 + s], mode)
            lines.append(line)
    return lines


def from_pixels(lines, mode, width_bytes, rows):
    """The inverse of to_pixels."""
    P = pixels_per_byte(mode)
    out = bytearray(width_bytes * rows * 8)
    for r in range(rows):
        for s in range(8):
            line = lines[r * 8 + s]
            for x in range(width_bytes):
                out[r * width_bytes * 8 + x * 8 + s] = \
                    pack_byte(line[x * P:(x + 1) * P], mode)
    return bytes(out)


def render(data, mode, width_bytes, rows, palette=None, scale=None):
    """A block of screen memory as a PIL RGB image. `scale` is (x, y) image
    pixels per screen pixel and defaults to the mode's aspect (2:1 for MODE
    2 and 5). `palette` maps logical colour -> RGB."""
    from PIL import Image
    palette = palette or default_palette(mode)
    sx, sy = scale or default_scale(mode)
    lines = to_pixels(data, mode, width_bytes, rows)
    w, h = len(lines[0]), len(lines)
    im = Image.new("RGB", (w * sx, h * sy))
    px = im.load()
    for y, line in enumerate(lines):
        for x, c in enumerate(line):
            rgb = tuple(palette[c])
            for dy in range(sy):
                for dx in range(sx):
                    px[x * sx + dx, y * sy + dy] = rgb
    return im


def unrender(im, mode, width_bytes, rows, palette=None, scale=None):
    """A PIL image (as render() would write it) back to screen memory. Every
    RGB must be in `palette` and every scaled block uniform; anything else
    raises ValueError with the screen coordinate."""
    palette = palette or default_palette(mode)
    sx, sy = scale or default_scale(mode)
    lut = {}
    for n in reversed(range(len(palette))):       # lowest index wins
        lut[tuple(palette[n])] = n
    P = pixels_per_byte(mode)
    w, h = width_bytes * P, rows * 8
    im = im.convert("RGB")
    if im.size != (w * sx, h * sy):
        raise ValueError(f"expected {w * sx}x{h * sy}, got {im.size[0]}x{im.size[1]}")
    px = im.load()
    lines = []
    for y in range(h):
        line = []
        for x in range(w):
            block = {px[x * sx + dx, y * sy + dy]
                     for dx in range(sx) for dy in range(sy)}
            if len(block) != 1:
                raise ValueError(f"pixel ({x},{y}) is not one colour: {sorted(block)}")
            rgb = block.pop()
            if rgb not in lut:
                raise ValueError(f"pixel ({x},{y}): {rgb} is not in the palette")
            line.append(lut[rgb])
        lines.append(line)
    return from_pixels(lines, mode, width_bytes, rows)
