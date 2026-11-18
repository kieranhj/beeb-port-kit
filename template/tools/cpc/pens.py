"""
pens.py - a demo's colour budget per line, from a cpcboot.py run, under RTW's chart (rtw.py).
From the phX port, 2026-11 (its tools/pens.py; the tables now come from cpcvideo.py and rtw.py).

The Gate Array's pen writes (io.npy) rebuild the CPC's 16 pens and border at every line of every
field. Under RTW's chart each CPC colour is a BBC checker of two physical colours; a solid one
(both the same) needs one MODE 2 logical colour, a dithered one two (its even and odd pixels).
A line's NEED is the sum over the distinct colours in its 16 pens: MODE 2 has 16 logical
colours, so a need above 16 is a line the stock BBC cannot show by palette alone. Also counted:
pen writes per line (each a BBC palette write or two, inside the line).

By pens (the default) it is an upper bound: every pen counts, shown or not - a demo that keeps
nearly every pen a different colour (phX) gets 28 everywhere. --frames counts what the picture
SHOWS: the distinct colours in each line of the run's rendered frames (fNNNNN.png), the border
included.

    python pens.py RUNDIR [--from F] [--to F] [--bucket N]  -> RUNDIR/pens.txt (per field range)
    python pens.py RUNDIR --frames                          -> RUNDIR/pens_frames.txt (per frame)

Known limits: a line is a fixed 64 us from VSYNC (a field that is not 312 x 64 us is cut at the
same places); a pen written mid-line counts for the line it ends in, its old colour forgotten;
the need ignores that two CPC colours may share a BBC physical colour (it counts logical colours
as if none were shared: an upper bound again); --frames needs the 0/128/255 levels.
"""
import argparse
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cpcvideo import HW   # noqa: E402  hardware colour -> (r, g, b) levels
from rtw import RTW       # noqa: E402  firmware colour -> (even, odd) BBC physical colours

LINE_US = 64
LINES = 312


def fw(h):
    r, g, b = HW[h & 31]
    return 9 * g + 3 * r + b


def need_of(colours):
    return sum(1 if RTW[fw(c)][0] == RTW[fw(c)][1] else 2 for c in set(colours))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('run')
    ap.add_argument('--from', dest='f0', type=int, default=0)
    ap.add_argument('--to', dest='f1', type=int, default=10 ** 9)
    ap.add_argument('--bucket', type=int, default=50)
    ap.add_argument('--frames', action='store_true')
    a = ap.parse_args()
    if a.frames:
        return frames(a.run)
    io = np.load(os.path.join(a.run, 'io.npy'))
    ga = io[(io['kind'] == 0) & ((io['port'] & 0xC000) == 0x4000)]
    pens = [0x14] * 17
    sel = 0
    i = 0
    n = len(ga)
    last_field = int(io['field'].max()) if len(io) else 0
    fl = os.path.join(a.run, 'fields.npy')          # the run's length, past the last pen write
    if os.path.exists(fl):
        last_field = max(last_field, len(np.load(fl)) - 1)
    rows = []
    for f in range(0, min(last_field, a.f1) + 1):
        writes_line = [0] * LINES
        need_line = [0] * LINES
        for line in range(LINES):
            end_us = (line + 1) * LINE_US
            while i < n and (ga['field'][i] < f or (ga['field'][i] == f and ga['us'][i] < end_us)):
                v = int(ga['value'][i])
                if v >> 6 == 0:
                    sel = 16 if v & 0x10 else v & 15
                elif v >> 6 == 1:
                    pens[sel] = v & 31
                    if ga['field'][i] == f:
                        writes_line[line] += 1
                i += 1
            need_line[line] = need_of(pens[:16])
        if f >= a.f0:
            rows.append((f, max(need_line), sum(1 for x in need_line if x > 16), max(writes_line),
                         sum(writes_line)))
    out = ['bucket of fields: worst need (logical colours), lines over 16 in the worst field, '
           'most pen writes in one line, pen writes a field (max)']
    for b0 in range(0, len(rows), a.bucket):
        chunk = rows[b0:b0 + a.bucket]
        out.append(f'{chunk[0][0]:6d}-{chunk[-1][0]:6d}: need {max(r[1] for r in chunk):2d}, '
                   f'over16 {max(r[2] for r in chunk):3d} lines, writes/line {max(r[3] for r in chunk):2d}, '
                   f'writes/field {max(r[4] for r in chunk):4d}')
    text = '\n'.join(out)
    open(os.path.join(a.run, 'pens.txt'), 'w').write(text + '\n')
    print(text)


def frames(run):
    import glob
    from PIL import Image
    lv = {0: 0, 128: 1, 255: 2}
    out = ['frame: worst line need (logical colours), lines needing more than 16, most colours in a line']
    for path in sorted(glob.glob(os.path.join(run, 'f*.png'))):
        img = np.asarray(Image.open(path).convert('RGB'))
        worst = over = most = 0
        for row in img:
            cols = {tuple(c) for c in np.unique(row.reshape(-1, 3), axis=0).tolist()}
            fws = {9 * lv[g] + 3 * lv[r] + lv[b] for r, g, b in cols}
            need = sum(1 if RTW[c][0] == RTW[c][1] else 2 for c in fws)
            worst = max(worst, need)
            most = max(most, len(fws))
            over += need > 16
        out.append(f'{os.path.basename(path)[1:6]}: need {worst:2d}, over16 {over:3d} lines, colours {most:2d}')
    text = '\n'.join(out)
    open(os.path.join(run, 'pens_frames.txt'), 'w').write(text + '\n')
    print(text)


if __name__ == '__main__':
    main()
