#!/usr/bin/env python3
"""
winape_match.py - WinAPE's captures (winape_shot.ps1) against the reference (cpcboot.py), field
by field: the Layer 1 gate for a cycle-exact CPC reference. From the phX port, 2026-11 (its
tools/winape_match.py): the part table, the geometry, the thresholds and phX's outro special case
moved into a JSON config (example_winape_parts.json documents every key).

    python winape_match.py CAPDIR REFDIR OUT [--config CFG.json] [--t0 MS] [--window N]
                           [--override FILE:FIRST_FIELD ...]

CAPDIR  a winape_shot.ps1 run: t<ms>.png (ms since WinAPE was launched). The capture box in the
        config must match how it was taken: phX's was -Size 820,720 with __COMPAT_LAYER=
        HighDpiAware, the picture at x 3..771, y 58..596 of the window, 2 x 2 window pixels a
        mode-1 pixel and a scanline (WinAPE 2.0b2, its default window chrome). Check one capture
        by eye before trusting the box: another WinAPE version, theme or DPI moves it.
REFDIR  cpcboot.py --every 1 output covering the captured span (fNNNNN.png anywhere below it).
        A long demo runs in parallel chunks from checkpoints:
          cpcboot.py DSK REFDIR/c0 END0 --run NAME --every 1 --save-state S1,S2,...   (once)
          cpcboot.py DSK REFDIR/cK ENDK --run NAME --every 1 --load-state .../state_SK.pkl
OUT     match.csv    one line a capture: ms, field, part, score (downsampled), diff (full-res
                     pixels that differ), the differing box (y0 y1 x0 x1, picture pixels)
        frames/      every matched capture as the picture (W x H), named by its field:
                     <part>_f<field>.png - WinAPE's picture of that field, to check the BBC by
        sheet_<part>.png  WinAPE | reference | WinAPE dimmed with the differing pixels red, for
                     the part's worst capture
        and a summary a part on stdout.

Both pictures are quantised to the CPC's three levels a gun (WinAPE 2.0b2's are 0/99/247, the
reference's 0/128/255: hence a separate upper threshold for each). The reference's picture is
taken at (ref_dy, ref_dx) of its 312 x 512. A capture is matched downsampled (every 3rd line, 4th
pixel) to every field within --window of (ms - t0) / field_ms, then at full resolution to the
best field +-2. Disc loads move WinAPE against the reference by seconds (two drive models), so
the window is wide; the field each capture lands on shows the lag.

An override replaces the reference's pictures for a span of fields with another source's:
a raw file of uint8 hardware colours, [n, lines, cols] (phX: its outro, made by the part's
converter from the demo's source because the reference's CRTC has a scanline-order error there,
cpcvideo.py defect 3). Each override's `row0` (default 1) is the picture row its first line goes
to, `xrep` (2) how many picture pixels a column is, `lines` (height - row0) and `cols`
(width / xrep) the shape of one field.

Known defects: WinAPE's top picture line is black in every part, so row 0 differs wherever the
reference has a picture there; a capture taken during a fade or a load (score < min_score) is
listed without a diff; the 0.5 s capture interval cannot see a one-field event (a missed VSYNC):
those need WinAPE's debugger.
"""

import argparse
import glob
import json
import os
import re
import sys

import numpy as np
from PIL import Image

DEFAULTS = {
    'parts': [[0, 'all']],              # [first field, name], ascending
    'capture_box': [3, 58, 771, 596],   # x0, y0, x1, y1 in the window capture
    'capture_scale': 2,                 # window pixels a picture pixel (each way)
    'ref_dy': 31, 'ref_dx': 0,          # the picture's place in a reference fNNNNN.png
    'height': 269, 'width': 384,        # the compared picture (mode-1 pixels, scanlines)
    'level_lo': 40, 'capture_hi': 170, 'ref_hi': 190,
    't0_ms': 3700,                      # ms (since launch) of the reference's field 0, roughly
    'field_ms': 19.968,
    'window': 1200,                     # fields either side of the estimate
    'min_score': 0.9,
    'overrides': [],                    # [{file, first_field, row0, xrep}]
}


def load_config(path):
    cfg = dict(DEFAULTS)
    if path:
        with open(path) as f:
            user = json.load(f)
        unknown = set(user) - set(DEFAULTS) - {'comment', '_comment'}
        if unknown:
            raise SystemExit(f'{path}: unknown keys {sorted(unknown)}')
        cfg.update(user)
        base = os.path.dirname(os.path.abspath(path))
        cfg['overrides'] = [dict(o, file=os.path.join(base, o['file'])) for o in cfg['overrides']]
    return cfg


def main():
    ap = argparse.ArgumentParser(description="WinAPE's captures against the reference, field by field.")
    ap.add_argument('capdir'); ap.add_argument('refdir'); ap.add_argument('out')
    ap.add_argument('--config', help='JSON: parts, geometry, thresholds (example_winape_parts.json)')
    ap.add_argument('--t0', type=float, help='ms of field 0 (overrides the config)')
    ap.add_argument('--window', type=int, help='fields either side (overrides the config)')
    ap.add_argument('--override', action='append', default=[],
                    help='FILE:FIRST_FIELD - raw [n, lines, cols] hardware colours replacing the '
                         'reference from FIRST_FIELD on (row0 1, xrep 2; the config can say more)')
    a = ap.parse_args()
    cfg = load_config(a.config)
    if a.t0 is not None:
        cfg['t0_ms'] = a.t0
    if a.window is not None:
        cfg['window'] = a.window
    for o in a.override:
        fn, _, f0 = o.rpartition(':')
        cfg['overrides'].append(dict(file=fn, first_field=int(f0), row0=1, xrep=2))
    parts = sorted((int(f), n) for f, n in cfg['parts'])
    H, WD = cfg['height'], cfg['width']
    DY, DX = cfg['ref_dy'], cfg['ref_dx']
    x0, y0, x1, y1 = cfg['capture_box']
    sc = cfg['capture_scale']
    if (x1 - x0) != WD * sc or (y1 - y0) != H * sc:
        raise SystemExit(f'capture_box {x1 - x0} x {y1 - y0} is not width x height x scale '
                         f'({WD * sc} x {H * sc})')

    def part(f):
        return ([n for s, n in parts if f >= s] or [parts[0][1]])[-1]

    def quant(img, hi):
        img = img.astype(np.int16)
        b = (img > cfg['level_lo']).astype(np.uint8) + (img > hi).astype(np.uint8)
        return b[..., 0] * 9 + b[..., 1] * 3 + b[..., 2]

    def cap_rgb(path):
        img = np.asarray(Image.open(path).convert('RGB'))[y0:y1, x0:x1]
        return img.reshape(H, sc, WD, sc, 3)[:, 0, :, 0, :]

    refs = {int(re.search(r'f(\d+)\.png$', p).group(1)): p
            for p in glob.glob(os.path.join(a.refdir, '**', 'f*.png'), recursive=True)
            if re.search(r'f(\d+)\.png$', p)}
    over = {}
    if cfg['overrides']:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from cpcvideo import RGB
        for o in cfg['overrides']:
            row0, xrep = int(o.get('row0', 1)), int(o.get('xrep', 2))
            rows = int(o.get('lines', H - row0))
            cols = int(o.get('cols', WD // xrep))
            pics = np.fromfile(o['file'], np.uint8).reshape(-1, rows, cols)
            for j in range(len(pics)):
                over[int(o['first_field']) + j] = (pics[j], row0, xrep)
    if not refs and not over:
        raise SystemExit(f'no reference frames f*.png under {a.refdir}')

    def ref_rgb(f):
        if f in over:
            hw, row0, xrep = over[f]
            pic = np.zeros((H, WD, 3), np.uint8)
            seg = np.repeat(RGB[hw], xrep, axis=1)[:H - row0, :WD]
            pic[row0:row0 + seg.shape[0], :seg.shape[1]] = seg
            return pic
        return np.asarray(Image.open(refs[f]).convert('RGB'))[DY:DY + H, DX:DX + WD]

    nf = max(set(refs) | set(over)) + 1
    ssz = len(range(0, H, 3)) * len(range(0, WD, 4))
    small = np.full((nf, ssz), 255, np.uint8)       # 255: no reference for that field
    for f in set(refs) | set(over):
        small[f] = quant(ref_rgb(f)[::3, ::4], cfg['ref_hi']).reshape(-1)
    have = set(refs) | set(over)
    os.makedirs(os.path.join(a.out, 'frames'), exist_ok=True)
    caps = sorted(glob.glob(os.path.join(a.capdir, 't*.png')))
    worst, lines = {}, []
    for c in caps:
        ms = int(re.search(r't(\d+)\.png$', c).group(1))
        rgb = cap_rgb(c)
        w = quant(rgb, cfg['capture_hi'])
        f0 = int((ms - cfg['t0_ms']) / cfg['field_ms'])
        lo, hi = max(0, f0 - cfg['window']), min(nf, f0 + cfg['window'])
        if hi <= lo:
            continue
        s = (small[lo:hi] == w[::3, ::4].reshape(-1)).mean(1)
        j = lo + int(s.argmax())
        if s.max() < cfg['min_score']:          # loading, a fade, or past the reference's end
            lines.append(f'{ms},{j},{part(j)},{s.max():.3f},,')
            continue
        best = None
        for g in range(max(0, j - 2), min(nf, j + 3)):
            if g not in have:
                continue
            d = quant(ref_rgb(g), cfg['ref_hi']) != w
            if best is None or d.sum() < best[0]:
                best = (int(d.sum()), g, d)
        n, g, d = best
        p = part(g)
        ys, xs = np.nonzero(d)
        box = f'{ys.min()} {ys.max()} {xs.min()} {xs.max()}' if n else ''
        lines.append(f'{ms},{g},{p},{s.max():.3f},{n},{box}')
        Image.fromarray(rgb).save(os.path.join(a.out, 'frames', f'{p}_f{g:05d}.png'))
        if p not in worst or n > worst[p][0]:
            worst[p] = (n, g, rgb, d)
    with open(os.path.join(a.out, 'match.csv'), 'w') as fh:
        fh.write('ms,field,part,score,diff,box\n' + '\n'.join(lines) + '\n')
    bar = np.full((H, 4, 3), 255, np.uint8)
    for p, (n, g, rgb, d) in worst.items():
        ov = rgb // 3
        ov[d] = (255, 0, 0)
        Image.fromarray(np.concatenate([rgb, bar, ref_rgb(g), bar, ov], 1)).save(
            os.path.join(a.out, f'sheet_{p}.png'))
    print(f'{len(caps)} captures, {sum(1 for l in lines if l.split(",")[4])} matched')
    for _, p in parts:
        ns = [int(l.split(',')[4]) for l in lines if l.split(',')[2] == p and l.split(',')[4]]
        if ns:
            print(f'{p:12s} {len(ns):3d} captures, {sum(x == 0 for x in ns):3d} identical, '
                  f'median {int(np.median(ns))} max {max(ns)} pixels differ')


if __name__ == '__main__':
    main()
