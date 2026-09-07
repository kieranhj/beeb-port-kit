#!/usr/bin/env python3
"""
scan_png.py - read a jsbeeb active-area screenshot character by character.

beeb-port-kit template, MIT, Kieran Connell 2026. The other half of
tools/probe_shot.mjs: the PNG is 1280 px across for R1 = 80 characters, so one
character time (one CPU cycle at 2 MHz in MODE 1) is 16 px and one scanline is
4 rows. Each requested row is printed as 80 x 4 letters, one per MODE 1 pixel:
K black, R red, G green, Y yellow, B blue, M magenta, C cyan, W white.

    python tools/scan_png.py out.png            every row of the active area
    python tools/scan_png.py out.png 352 356    the rows named

Row 356 is the panel's last scanline (232 + 31 * 4) when the panel's top edge
is the first non-black row; the script prints where that is. A palette write
that lands in the displayed part of a line shows as the character at which the
colour changes - the phase, to the cycle (docs/layer-0-toolchain.md).
"""
import sys
from PIL import Image

NAMES = {(0, 0, 0): "K", (255, 0, 0): "R", (0, 255, 0): "G", (255, 255, 0): "Y",
         (0, 0, 255): "B", (255, 0, 255): "M", (0, 255, 255): "C", (255, 255, 255): "W"}


def name(p):
    r, g, b = p[:3]
    return NAMES.get((255 if r > 127 else 0, 255 if g > 127 else 0, 255 if b > 127 else 0), "?")


def main():
    im = Image.open(sys.argv[1]).convert("RGB")
    w, h = im.size
    cols = [x for x in range(w) if any(im.getpixel((x, y)) != (0, 0, 0) for y in range(0, h, 4))]
    x0, x1 = cols[0], cols[-1]
    rows = [y for y in range(h) if any(im.getpixel((x, y)) != (0, 0, 0) for x in range(x0, x1, 8))]
    ppc = (x1 - x0 + 1) / 80.0
    print(f"active x {x0}-{x1} ({x1 - x0 + 1} px, {ppc:g} px a character), first row {rows[0]}, last {rows[-1]}")
    wanted = [int(a) for a in sys.argv[2:]] or range(rows[0], rows[-1] + 1)
    for y in wanted:
        line = ""
        for c in range(80):
            line += "".join(name(im.getpixel((int(x0 + ppc * (c + (k + 0.5) / 4)), y))) for k in range(4))
        print(y, line)


if __name__ == "__main__":
    main()
