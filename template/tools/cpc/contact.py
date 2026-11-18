"""
contact.py - a contact sheet of a cpcboot.py run's frames, labelled by field. From the phX
port, 2026-11 (its tools/contact.py; an empty selection is now an error, not a crash).

    python contact.py RUNDIR OUT.png [--from F] [--to F] [--step N] [--cols C] [--scale S]

Takes every frame fNNNNN.png in RUNDIR with F <= NNNNN <= T and NNNNN a multiple of N, shrinks
each by S (default 4) and lays them out C to a row, each with its field number. Also prints
where the picture stops changing (the last frame that differs from the one before it: by file
hash, so it only means "changes" for PNGs written by the same tool). Any fNNNNN.png works (e.g.
winape_match.py's frames renamed), but all are taken at the first one's size.
"""
import argparse
import glob
import hashlib
import os
import re

from PIL import Image, ImageDraw


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('run')
    ap.add_argument('out')
    ap.add_argument('--from', dest='f0', type=int, default=0)
    ap.add_argument('--to', dest='f1', type=int, default=10 ** 9)
    ap.add_argument('--step', type=int, default=100)
    ap.add_argument('--cols', type=int, default=10)
    ap.add_argument('--scale', type=int, default=4)
    a = ap.parse_args()
    frames = []
    for p in glob.glob(os.path.join(a.run, 'f*.png')):
        m = re.match(r'f(\d+)\.png$', os.path.basename(p))
        if m:
            frames.append((int(m.group(1)), p))
    frames.sort()
    if not frames:
        ap.error(f'no fNNNNN.png in {a.run}')
    last_change, prev = None, None
    for f, p in frames:
        h = hashlib.md5(open(p, 'rb').read()).hexdigest()
        if prev is not None and h != prev:
            last_change = f
        prev = h
    print(f'{len(frames)} frames, {frames[0][0]}-{frames[-1][0]}; the picture last changes at field {last_change}')
    pick = [(f, p) for f, p in frames if a.f0 <= f <= a.f1 and f % a.step == 0]
    if not pick:
        ap.error(f'no frame in {a.f0}..{a.f1} is a multiple of --step {a.step}')
    w0, h0 = Image.open(pick[0][1]).size
    w, h = w0 // a.scale, h0 // a.scale
    rows = (len(pick) + a.cols - 1) // a.cols
    sheet = Image.new('RGB', (a.cols * (w + 4), rows * (h + 16)), (40, 40, 40))
    d = ImageDraw.Draw(sheet)
    for i, (f, p) in enumerate(pick):
        x, y = (i % a.cols) * (w + 4), (i // a.cols) * (h + 16)
        sheet.paste(Image.open(p).convert('RGB').resize((w, h), Image.BILINEAR), (x, y + 14))
        d.text((x + 2, y + 1), str(f), fill=(255, 255, 255))
    sheet.save(a.out)
    print(f'{len(pick)} frames -> {a.out} ({sheet.size[0]} x {sheet.size[1]})')


if __name__ == '__main__':
    main()
