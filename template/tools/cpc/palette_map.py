"""Decision 3's stock palette: each colourway's three faces re-dithered to BBC 2-colour checkers.

The original's cube is one 8 x 16 template (&2000, 4 pens) recoloured per colourway (&2AF9: the
template's pens 1-4 -> real pens). Its three faces are checkers of two template pens:
  top = 2 on even (x + y), 4 on odd;  left = 2 even, 3 odd (x < 4);  right = 1 even, 3 odd
Every CPC colour has a BBC checker: RTW's dither chart (KC, 2026-11-07; RTW below, by firmware
colour). A face of one pen is that pen's checker. A face of two pens (A on even pixels, B on odd)
takes one colour of A's pair on its even pixels and one of B's on its odd ones: of the (up to)
four, the pair whose average is nearest the face's (the CPC's levels 0, 1/2, 1; plain RGB),
ties to the nearer in CIELAB (linear light, the CPC's middle level 0.22), then to RTW's order.

Logical colours (MODE 2, 16):
  0      black, pen 0: transparent, as the original's pen 0
  1-7    red green yellow blue magenta cyan white (physical = logical)
  8      opaque black (the CPC's pen 4 is black and opaque)
  9-14   the faces with pen 8, 2 each (even, odd): the flash (&32B2, colours &2AEF) sets them
  15     unused (black)
Pen 5 is mauve (&5D) in the colourways drawn up to the logo's end and pastel cyan (&5B) in the
ones after: no colourway is drawn on both sides, and both screen pages are all pen 0 when the
original switches it (record 6,659), so the cache carries it and nothing is written then.

  python tools/palette_map.py MEM.bin       prints the faces and their checkers
"""
import itertools
import sys

HW = [(1, 1, 1), (1, 1, 1), (0, 2, 1), (2, 2, 1), (0, 0, 1), (2, 0, 1), (0, 1, 1), (2, 1, 1),
      (2, 0, 1), (2, 2, 1), (2, 2, 0), (2, 2, 2), (2, 0, 0), (2, 0, 2), (2, 1, 0), (2, 1, 2),
      (0, 0, 1), (0, 2, 1), (0, 2, 0), (0, 2, 2), (0, 0, 0), (0, 0, 2), (0, 1, 0), (0, 1, 2),
      (1, 0, 1), (1, 2, 1), (1, 2, 0), (1, 2, 2), (1, 0, 0), (1, 0, 2), (1, 1, 0), (1, 1, 2)]
BBC = ['black', 'red', 'green', 'yellow', 'blue', 'magenta', 'cyan', 'white']
K, R, G, Y, B, M, C, W = range(8)
# RTW's chart, by firmware colour 9G + 3R + B (black, blue, bright blue, red, magenta, ...)
RTW = [(K, K), (K, B), (B, B), (K, R), (R, B), (B, M), (R, R), (M, R), (M, M),
       (K, G), (G, B), (B, C), (G, R), (M, G), (C, M), (R, Y), (M, Y), (M, W),
       (G, G), (C, G), (C, C), (G, Y), (Y, C), (C, W), (Y, Y), (W, Y), (W, W)]
FW_NAMES = ['black', 'blue', 'bright blue', 'red', 'magenta', 'mauve', 'bright red', 'purple',
            'bright magenta', 'green', 'cyan', 'sky blue', 'yellow', 'grey', 'pastel blue',
            'orange', 'pink', 'pastel magenta', 'bright green', 'sea green', 'bright cyan', 'lime',
            'pastel green', 'pastel cyan', 'bright yellow', 'pastel yellow', 'bright white']
FLASH = [0x5F, 0x5B, 0x4B]           # &2AEF: 5F 5B 4B 5B 5F; 5F is the boot's
PEN5_BEFORE, PEN5_AFTER = 0x5D, 0x5B
LATE_FROM = 36                       # colourways 36 on are drawn only after the logo (measured)
OPAQUE_BLACK = 8
COLOURWAYS = 103


def fw(h):
    r, g, b = HW[h & 0x1F]
    return 9 * g + 3 * r + b


def name(h):
    return FW_NAMES[fw(h)]


def nominal(h):
    return tuple(c / 2 for c in HW[h & 0x1F])


def rgb_bbc(i):
    return (i & 1, (i >> 1) & 1, (i >> 2) & 1)


def lin(v):
    return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4


def lab(c):
    r, g, b = c
    x = (0.4124 * r + 0.3576 * g + 0.1805 * b) / 0.95047
    y = 0.2126 * r + 0.7152 * g + 0.0722 * b
    z = (0.0193 * r + 0.1192 * g + 0.9505 * b) / 1.08883
    f = [t ** (1 / 3) if t > 0.008856 else 7.787 * t + 16 / 116 for t in (x, y, z)]
    return (116 * f[1] - 16, 500 * (f[0] - f[1]), 200 * (f[1] - f[2]))


def mean(a, b):
    return tuple((x + y) / 2 for x, y in zip(a, b))


def dist(a, b):
    return sum((x - y) ** 2 for x, y in zip(a, b)) ** 0.5


def linear(h):
    return tuple(lin(128 / 255) if v == 1 else v / 2 for v in HW[h & 0x1F])


def face(he, ho):
    """BBC (even, odd) for a face of Gate Array colours he (even pixels) and ho (odd)"""
    if he == ho:
        return RTW[fw(he)]
    target = mean(nominal(he), nominal(ho))
    tl = lab(mean(linear(he), linear(ho)))
    best = None
    for n, (a, b) in enumerate(itertools.product(RTW[fw(he)], RTW[fw(ho)])):
        A, Bc = rgb_bbc(a), rgb_bbc(b)
        key = (round(dist(mean(A, Bc), target), 6), round(dist(lab(mean(A, Bc)), tl), 6), n)
        if best is None or key < best[0]:
            best = (key, (a, b))
    return best[1]


def lp(b):
    return ((b >> 7) & 1) | ((b >> 3) & 1) << 1 | ((b >> 5) & 1) << 2 | ((b >> 1) & 1) << 3


def template(mem):
    """(pen, face) for each of the 8 x 16 pixels; face None for pen 0"""
    t = mem[0x2000:0x2040]
    pens = [[0] * 8 for _ in range(16)]
    for y in range(16):
        for x in range(4):
            b = t[y * 4 + x]
            pens[y][2 * x] = lp(b)
            pens[y][2 * x + 1] = lp((b << 1) & 0xFF)

    def nb(x, y):
        return {pens[j][i] for i, j in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1))
                if 0 <= i < 8 and 0 <= j < 16}
    out = [[None] * 8 for _ in range(16)]
    for y in range(16):
        for x in range(8):
            p = pens[y][x]
            f = {4: 'top', 1: 'right', 0: None}.get(p)
            if p == 2:
                f = 'top' if 4 in nb(x, y) else 'left'     # the top's lower-left edge
            elif p == 3:
                f = 'left' if x < 4 else 'right'           # the vertical edge
            out[y][x] = (p, f)
    return out


def colourways(mem):
    return [[lp(b) for b in mem[0x2AF9 + 4 * i:0x2AF9 + 4 * i + 4]] for i in range(COLOURWAYS)]


def palette(mem):
    return list(mem[0x2CE6 + 1:0x2CE6 + 32:2])        # pens 0-15 as the boot sets them


def face_pens(cw):
    t1, t2, t3, t4 = cw
    return {'top': (t2, t4), 'left': (t2, t3), 'right': (t1, t3)}


def pen_hw(pal, p, i):
    if p == 8:
        return FLASH[0]
    if p == 5:
        return PEN5_AFTER if i >= LATE_FROM else PEN5_BEFORE
    return pal[p]


def logical(c):
    return OPAQUE_BLACK if c == K else c


def mapping(mem):
    """per colourway {face: (logical even, logical odd)}; dyn {first logical: (key, [(a, b) per
    flash state])}; the static faces {(hw even, hw odd): (a, b)}"""
    pal = palette(mem)
    dyn_keys = {}
    out, rows = [], {}
    for i, cw in enumerate(colourways(mem)):
        faces = {}
        for f, (pe, po) in face_pens(cw).items():
            if 8 in (pe, po):
                # (8, 2) is (2, 8) with even and odd swapped: one logical pair, swapped
                key = (min(pe, po), max(pe, po), pen_hw(pal, 5, i) if 5 in (pe, po) else None)
                if key not in dyn_keys:
                    dyn_keys[key] = 9 + 2 * len(dyn_keys)
                    assert dyn_keys[key] + 1 <= 14, 'more than 3 flash faces'
                lo = dyn_keys[key]
                faces[f] = (lo + 1, lo) if pe > po else (lo, lo + 1)
                continue
            he, ho = pen_hw(pal, pe, i), pen_hw(pal, po, i)
            a, b = face(he, ho)
            faces[f] = (logical(a), logical(b))
            rows[(he, ho)] = (a, b)
        out.append(faces)
    dyn = {}
    for (pe, po, p5), lo in dyn_keys.items():
        def hw(p, s):
            return FLASH[s] if p == 8 else (p5 if p == 5 else pal[p])
        dyn[lo] = ((pe, po, p5), [face(hw(pe, s), hw(po, s)) for s in range(3)])
    return out, dyn, rows


def ula_palette(dyn, state=0):
    """the 16 logical -> physical colours for a flash state"""
    p = [0, 1, 2, 3, 4, 5, 6, 7, 0, 0, 0, 0, 0, 0, 0, 0]
    for lo, (_, states) in dyn.items():
        p[lo], p[lo + 1] = states[state]
    return p


def swap03(v):
    return (v & 6) | (v & 1) << 3 | (v & 8) >> 3


def enc_left(p):
    """a CPC mode 0 byte with pen p as its left pixel"""
    return (p & 1) << 7 | (p >> 1 & 1) << 3 | (p >> 2 & 1) << 5 | (p >> 3 & 1) << 1


def stock_cache(mem):
    """the 103 x 64-byte cache, the original's layout (row-major, as &3363 builds it at &4000),
    every pixel a BBC logical colour (stored as the CPC pen whose bits show it: bits 0, 3 swapped)"""
    faces, _, _ = mapping(mem)
    tpl = template(mem)
    out = bytearray()
    for i in range(COLOURWAYS):
        for y in range(16):
            for xb in range(4):
                b = 0
                for k in (0, 1):
                    x = 2 * xb + k
                    p, f = tpl[y][x]
                    if p:
                        b |= enc_left(swap03(faces[i][f][(x + y) & 1])) >> k
                out.append(b)
    return bytes(out)


def cache_gen_data(mem):
    """decision 15: what src/gen.6502's gen_cache builds the caches from at runtime.
    pos_stock, per cache byte (column order): ((y AND 1) 4 + left face) | ((y AND 1) 4 + right
    face) << 4, faces 0 none, 1 top, 2 left, 3 right; faces, per colourway the three faces' BBC
    logical pairs, even << 4 | odd; pos_cpc: left pen | right pen << 4 (the template's)."""
    faces, _, _ = mapping(mem)
    tpl = template(mem)
    fi = {None: 0, 'top': 1, 'left': 2, 'right': 3}
    pos_stock = bytes(((y & 1) * 4 + fi[tpl[y][2 * k][1]]) |
                      (((y & 1) * 4 + fi[tpl[y][2 * k + 1][1]]) << 4)
                      for k in range(4) for y in range(16))
    ftab = bytes(faces[c][f][0] << 4 | faces[c][f][1]
                 for c in range(COLOURWAYS) for f in ('top', 'left', 'right'))
    pos_cpc = bytes(tpl[y][2 * k][0] | tpl[y][2 * k + 1][0] << 4 for k in range(4) for y in range(16))
    return pos_stock, ftab, pos_cpc


def install(m, mem):
    """put the stock cache in a model's memory (after its boot built the original's)"""
    m[0x4000:0x4000 + 64 * COLOURWAYS] = stock_cache(mem)


def ula_byte(logical_, physical):
    return logical_ << 4 | (physical ^ 7)


# ---- the VideoNuLA build (decision 3): the original's cache and its exact colours
NULA_LEVEL = (0x0, 0x8, 0xF)         # the CPC's three levels as 4 bits (sRGB 0, 136, 255)


def cpc_cache(mem):
    """the original's own cache, as &3363 builds it (tools/fx_world.py's tables)"""
    import fx_world
    w = fx_world.World(mem, [])
    w.tables()
    return bytes(w.m[0x4000:0x4000 + 64 * COLOURWAYS])


def nula_rgb(h):
    """NuLA's two bytes for Gate Array colour h, less the index: R; G << 4 | B"""
    r, g, b = (NULA_LEVEL[c] for c in HW[h & 0x1F])
    return r, g << 4 | b


def nula_palette(mem):
    """the boot's 32 bytes to &FE23 (palette mode 1): logical L = CPC pen swap(L)"""
    pal = palette(mem)
    out = bytearray()
    for L in range(16):
        r, gb = nula_rgb(pal[swap03(L)])
        out += bytes((L << 4 | r, gb))
    return bytes(out)


def main(memfile):
    mem = open(memfile, 'rb').read()
    tpl = template(mem)
    print('the template, faces (T top, L left, R right):')
    for row in tpl:
        print('  ' + ''.join('.' if f is None else f[0].upper() for _, f in row) + '   ' +
              ''.join('.' if not p else str(p) for p, _ in row))
    _, dyn, rows = mapping(mem)
    print(f'\n{len(rows)} static faces, CPC (even + odd) -> BBC (even + odd):')
    for (he, ho), (a, b) in sorted(rows.items(), key=lambda kv: (fw(kv[0][0]), fw(kv[0][1]))):
        print(f'  {name(he):>14} + {name(ho):<14} -> {BBC[a]:>7} + {BBC[b]}')
    print('\nflash faces (logicals: per pen 8 state 5F / 5B / 4B):')
    for lo, ((pe, po, p5), states) in dyn.items():
        print(f'  {lo},{lo + 1} pens {pe}+{po}' + (f' (pen 5 {p5:02X})' if p5 else '') + ': ' +
              ' / '.join(f'{BBC[a]}+{BBC[b]}' for a, b in states))


if __name__ == '__main__':
    main(*sys.argv[1:])
