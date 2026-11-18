"""
rtw.py - a CPC mode-0 picture as BBC MODE 2 by RTW's fixed (x + y) & 1 checker. From the phX
port, 2026-11 (its tools/rtw.py, its decision 2; unchanged but for this docstring).

Each of the CPC's 27 colours is a two-colour BBC checker (RTW's chart, by firmware colour
9G + 3R + B, the same chart as palette_map.py's). A CPC mode-0 pixel is a MODE 2 pixel (the
same width and pixel clock), so pixel (x, y) of CPC colour c becomes BBC physical colour
RTW[c][(x + y) & 1]: the checker alternates along the line and from line to line. Logical colours
0-7 are the physical ones (a static picture needs no palette tricks), so 8-15 stay free for
rasters.

    python rtw.py FRAME.png OUT [--x0 N --width W --y0 N --height H]
        FRAME.png: a cpcboot.py frame (RGB, 2 png pixels a mode-0 pixel, levels 0/128/255)
        writes OUT.bin (MODE 2 bytes in the BBC's character-cell order: cell row r, column c,
        scanline l at r * W/2 * 8 + c * 8 + l; the height cut to a multiple of 8) and
        OUT_preview.png (CPC | BBC, side by side, 4 x 2)

As a library: dither(fw_rows) -> physical rows; mode2_bytes(phys_rows) -> bytes.

Known limits: the input must be exactly the 0/128/255 levels (a WinAPE capture, 0/99/247, or a
scaled PNG fails in LEVEL); a mode-1 or mode-2 region is sampled every other pixel as if mode 0;
the checker's phase is fixed to the picture's (x0, y0), so a scrolling picture's dither crawls
unless the port moves the phase with it.
"""
import argparse
import os

import numpy as np

K, R, G, Y, B, M, C, W = range(8)            # BBC physical colours (bit 0 red, 1 green, 2 blue)
RTW = [(K, K), (K, B), (B, B), (K, R), (R, B), (B, M), (R, R), (M, R), (M, M),
       (K, G), (G, B), (B, C), (G, R), (M, G), (C, M), (R, Y), (M, Y), (M, W),
       (G, G), (C, G), (C, C), (G, Y), (Y, C), (C, W), (Y, Y), (W, Y), (W, W)]
BBC_RGB = np.array([[(i & 1) * 255, (i >> 1 & 1) * 255, (i >> 2 & 1) * 255] for i in range(8)], np.uint8)
LEVEL = {0: 0, 128: 1, 255: 2}


def firmware_rows(png, x0, width, y0, height):
    """the PNG's mode-0 pixels as firmware colour numbers, [height, width]"""
    from PIL import Image
    img = np.asarray(Image.open(png).convert('RGB'))[y0:y0 + height, 2 * x0:2 * (x0 + width):2]
    lv = np.vectorize(LEVEL.get)(img)
    return 9 * lv[..., 1] + 3 * lv[..., 0] + lv[..., 2]


def dither(fw):
    pair = np.array(RTW, np.uint8)
    h, w = fw.shape
    phase = (np.arange(w)[None, :] + np.arange(h)[:, None]) & 1
    return pair[fw, phase]


def mode2_byte(left, right):
    """MODE 2: the left pixel's colour bits 3..0 in bits 7,5,3,1, the right's in 6,4,2,0"""
    b = 0
    for bit, (lb, rb) in enumerate(((1, 0), (3, 2), (5, 4), (7, 6))):
        b |= ((left >> bit) & 1) << lb | ((right >> bit) & 1) << rb
    return b


def mode2_bytes(phys):
    """rows of physical colours (even width) -> MODE 2 screen bytes in character-cell order:
    cell row r, column c, scanline l at r * (w / 2) * 8 + c * 8 + l"""
    h, w = phys.shape
    assert w % 2 == 0 and h % 8 == 0
    lut = np.array([[mode2_byte(a, b) for b in range(16)] for a in range(16)], np.uint8)
    pairs = lut[phys[:, 0::2], phys[:, 1::2]]                  # [h, w/2] bytes
    cols = w // 2
    return pairs.reshape(h // 8, 8, cols).transpose(0, 2, 1).reshape(-1).tobytes()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('png')
    ap.add_argument('out')
    ap.add_argument('--x0', type=int, default=0)
    ap.add_argument('--width', type=int, default=256)
    ap.add_argument('--y0', type=int, default=0)
    ap.add_argument('--height', type=int, default=312)
    a = ap.parse_args()
    fw = firmware_rows(a.png, a.x0, a.width, a.y0, a.height)
    phys = dither(fw)
    h8 = (phys.shape[0] // 8) * 8
    open(a.out + '.bin', 'wb').write(mode2_bytes(phys[:h8, :phys.shape[1] // 2 * 2]))
    from PIL import Image
    lvl = np.array([0, 128, 255], np.uint8)
    cpc = np.stack([lvl[(fw // 3) % 3], lvl[fw // 9], lvl[fw % 3]], -1)
    bbc = BBC_RGB[phys]
    side = np.concatenate([cpc, np.zeros((cpc.shape[0], 8, 3), np.uint8), bbc], 1)
    Image.fromarray(side).resize((side.shape[1] * 4, side.shape[0] * 2), Image.NEAREST).save(a.out + '_preview.png')
    used = sorted(set(fw.ravel().tolist()))
    print(f'{fw.shape[1]} x {fw.shape[0]} pixels, CPC colours used (firmware): {used}; '
          f'{len(open(a.out + ".bin", "rb").read())} MODE 2 bytes')


if __name__ == '__main__':
    main()
