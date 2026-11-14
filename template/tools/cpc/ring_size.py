"""How big must the bottom ring be? (decision 11)

The original's page-&8000 writes - the copy &316A (2 lines of the edge row) and &31FF's second
half (rows -1..13 at x = 94) - replayed, pass by pass from work/ref/passes.bin, into a ring of R
cells through the port's window mapping (cell = b + (X - 2S), b moving with 2S); then everything
the bottom displays in that field (rows 0-13, the sliver's lines 0..7-f, from 2S + R3's byte)
compared with page &8000. LO: how far above the window a write may land and still be kept.

  python tools/ring_size.py [RECORDS] [LO] R...        e.g. 1500 100 1440 1446
Measured 2026-11-07 (1,499 fields): R 1440 wrong in 1,218; 1442 in 1,089; 1444 in 170;
1446, 1448, 1456 and 2048 (page &8000 itself) in none. OWN=1 drops writes onto cells the window
shows as something else (1440: still wrong in 1,295 - the dropped bytes are needed later).
"""
import sys
sys.path.insert(0, __import__('os').path.dirname(__import__('os').path.abspath(__file__)))
import numpy as np
import cpcref_fieldlocked as cpcref  # noqa: E402  (the kit: Isometrikum's cpcref.py)

N = int(sys.argv[1]) if len(sys.argv) > 1 else 1300
LO = int(sys.argv[2]) if len(sys.argv) > 2 else 120
recs = []
for i, (f, c, ints, m) in enumerate(cpcref.load_passes('work/ref/passes.bin')):
    if i < 2:
        continue
    if i > N:
        break
    S = int(m[0x3298]) | int(m[0x3299]) << 8
    recs.append((S, int(m[0x3268]), int(m[0x3272]), np.array(m[0x8000:0xC000]).reshape(8, 2048),
                 int(m[0x311F]) | int(m[0x3120]) << 8))

for R in [int(x) for x in sys.argv[3:]] or (1440, 1442, 1444, 1446, 1448):
    ring = np.zeros((8, R), np.uint8)
    prev = np.zeros((8, 2048), np.uint8)
    b = 0
    tw_prev = (2 * (recs[0][0] & 0x3FF)) % 2048
    bad = badf = 0
    for t, (S, f, r3, p8, edge) in enumerate(recs):
        tw = (2 * (S & 0x3FF)) % 2048
        dS = (tw - tw_prev) % 2048
        dS = dS - 2048 if dS >= 1024 else dS
        b = (b + dS) % R
        tw_prev = tw
        writes = []
        if t and r3 == 5:                                  # &31FF's page 8 half
            x0 = (tw - 2) % 2048                    # rows -1..13 at x = 94 (fx_world's clear_column)
            for j in range(15):
                for xx in (0, 1):
                    for l in range(8):
                        writes.append((l, (x0 + 96 * j + xx) % 2048))
        if t:                                              # &316A
            o, l0 = edge & 0x7FF, (edge >> 11) & 7
            for i in range(96):
                for l in (l0, l0 + 1):
                    writes.append((l, (o + i) % 2048))
        for l, X in writes:
            d = (X - tw) % 2048
            d = d - 2048 if d >= 2048 - LO else d
            if -LO <= d < R - LO:
                if __import__('os').environ.get('OWN'):
                    # the cell's displayed k on this line: if it is shown as another offset, drop
                    kd = (d % R)
                    shown = kd < 1344 or (kd <= 1440 and l <= 7 - f) or (kd == 1440 and l <= 7 - f)
                    h_ = 1 if r3 == 6 else 0
                    shown = (h_ <= kd < 1344 + h_) or (1344 + h_ <= kd <= 1439 + h_ and l <= 7 - f)
                    if shown and kd != d:
                        continue
                ring[l, (b + d) % R] = p8[l, X]
            elif __import__('os').environ.get('DROPS'):
                print(f'  t {t} dropped d {d} line {l} (f {f}, edge {edge:04x}, tw {tw})')
        h = 1 if r3 == 6 else 0
        k = (96 * np.arange(15)[:, None] + np.arange(96)[None, :] + h)
        nb = 0
        for l in range(8):
            kk = k if l <= 7 - f else k[:14]
            nb += int((ring[l, (b + kk) % R] != p8[l, (tw + kk) % 2048]).sum())
        bad += nb
        badf += nb > 0
        if nb and badf <= int(__import__('os').environ.get('SHOW', '0')):
            for l in range(8):
                kk = k if l <= 7 - f else k[:14]
                w = np.nonzero(ring[l, (b + kk) % R] != p8[l, (tw + kk) % 2048])
                if len(w[0]): print(f'  t {t} f {f} h {h} b {b} tw {tw} line {l}: rows {sorted(set(w[0].tolist()))[:5]} x {w[1][:6].tolist()}')
    print(f'R {R}: {bad} bytes wrong in {badf} of {len(recs)} fields', flush=True)
