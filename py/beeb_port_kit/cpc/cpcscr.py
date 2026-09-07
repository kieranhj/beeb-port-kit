"""
cpcscr.py - Amstrad CPC screens: the Gate Array's 27 colours, the mode 0/1/2
pixel packing, the 16K screen's scanline interleave, and OCP Art Studio
.PAL files, rendered to a PIL image.

beeb-port-kit: from
  https://github.com/kieranhj/edge-beeb/blob/master/tools/cpc/cpcscr.py
less the one Edge-specific table (the CPC port's in-game palette read from
its source, which lives in that project). Proven: Axelay's loading screen
and work-disc art render through this to what the emulator shows, and the
27-colour FIRMWARE_RGB is what dither_pair was proved against
(modes.py). Fork this into your project's tools/; keep this header.

Mode 0: 160 x 200, 16 pens, two pixels a byte with the bits scattered
(pixel 0's pen bits 0-3 are at bits 7,3,5,1; pixel 1's at 6,2,4,0). Mode 1:
320 x 200, 4 pens, four a byte: pixel i's LOW pen bit at bit (7-i), its high
bit at (3-i) - the opposite way round from the BBC's MODE 1. Mode 2: 640 x
200, 2 pens, bit 7 leftmost.
A screen is 16K at 80 bytes a line, line y at (y % 8) * &800 + (y // 8) * 80.
"""

import os

from PIL import Image

from .dsk import strip_amsdos

# Firmware colour index -> RGB. The 27 CPC colours; each component is 0,
# 128 or 255.
FIRMWARE_RGB = [
    (0, 0, 0), (0, 0, 128), (0, 0, 255), (128, 0, 0), (128, 0, 128), (128, 0, 255), (255, 0, 0),
    (255, 0, 128), (255, 0, 255), (0, 128, 0), (0, 128, 128), (0, 128, 255), (128, 128, 0),
    (128, 128, 128), (128, 128, 255), (255, 128, 0), (255, 128, 128), (255, 128, 255),
    (0, 255, 0), (0, 255, 128), (0, 255, 255), (128, 255, 0), (128, 255, 128), (128, 255, 255),
    (255, 255, 0), (255, 255, 128), (255, 255, 255),
]
# Gate Array value (&40-&5F) -> firmware colour index (the standard hardware table).
GA_TO_FW = [
    13, 13, 19, 25, 1, 7, 10, 16, 7, 25, 24, 26, 6, 8, 15, 17,
    1, 19, 18, 20, 0, 2, 9, 11, 2, 20, 21, 23, 3, 5, 12, 14,
]

PIXELS_PER_BYTE = (2, 4, 8)


def ga_rgb(v):
    """A Gate Array hardware colour (&40-&5F, or its low 5 bits) as RGB."""
    return FIRMWARE_RGB[GA_TO_FW[v & 0x1F]]


def read_pal(path_or_bytes):
    """An OCP Art Studio .PAL: (mode, sixteen pens as GA values, border)."""
    if isinstance(path_or_bytes, (str, os.PathLike)):
        with open(path_or_bytes, "rb") as f:
            b = f.read()
    else:
        b = bytes(path_or_bytes)
    b = strip_amsdos(b)
    mode = b[0]
    pens = [b[3 + i * 12] for i in range(16)]
    border = b[3 + 16 * 12]
    return mode, pens, border


def decode_byte(byte, mode):
    """One screen byte as its pen indices, left to right."""
    b = byte
    if mode == 0:
        p0 = ((b >> 7) & 1) | ((b >> 2) & 2) | ((b >> 3) & 4) | ((b << 2) & 8)
        p1 = ((b >> 6) & 1) | ((b >> 1) & 2) | ((b >> 2) & 4) | ((b << 3) & 8)
        return [p0, p1]
    if mode == 1:
        return [((b >> (7 - i)) & 1) | (((b >> (3 - i)) & 1) << 1) for i in range(4)]
    return [(b >> (7 - i)) & 1 for i in range(8)]


def encode_byte(pens, mode):
    """The inverse of decode_byte."""
    b = 0
    if mode == 0:
        p0, p1 = pens
        b |= ((p0 & 1) << 7) | ((p0 & 2) << 2) | ((p0 & 4) << 3) | ((p0 & 8) >> 2)
        b |= ((p1 & 1) << 6) | ((p1 & 2) << 1) | ((p1 & 4) << 2) | ((p1 & 8) >> 3)
    elif mode == 1:
        for i, p in enumerate(pens):
            b |= (p & 1) << (7 - i)
            b |= ((p >> 1) & 1) << (3 - i)
    else:
        for i, p in enumerate(pens):
            b |= (p & 1) << (7 - i)
    return b


def screen_pixels(scr, mode, width_bytes=80, lines=200):
    """`lines` rows of pen indices, the CPC interleave undone."""
    d = strip_amsdos(scr)
    rows = []
    for y in range(lines):
        off = (y % 8) * 0x800 + (y // 8) * width_bytes
        row = []
        for x in range(width_bytes):
            row += decode_byte(d[off + x], mode)
        rows.append(row)
    return rows


def render(scr_path, pal_path, scale=1):
    """A .SCR + .PAL as (PIL image, mode, pens, rows of pen indices)."""
    mode, pens, _ = read_pal(pal_path)
    with open(scr_path, "rb") as f:
        rows = screen_pixels(f.read(), mode)
    ppb = PIXELS_PER_BYTE[mode]
    w, h = 80 * ppb, len(rows)
    im = Image.new("RGB", (w, h))
    px = im.load()
    for y, row in enumerate(rows):
        for x, p in enumerate(row):
            px[x, y] = ga_rgb(pens[p])
    if scale != 1:
        im = im.resize((w * scale, h * scale), Image.NEAREST)
    return im, mode, pens, rows
