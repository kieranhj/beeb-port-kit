"""
music_extract.py - an AY-3-891x register file per field (or per music frame), from a log of the
reference's AY writes. The first step of the offline AY -> SN76489 pipeline:

    music_extract.py  (AY writes -> ay_fields.npy, tunes.json)
    music_convert.py  (-> sn_fields.npy, AY / SN WAVs; the bass-section report)
    music_pack.py     (-> the stream the 6502 player sends: count byte + SN bytes)

Fork this into your project's tools/; keep this header.

From the phX port (tools/music_extract.py, 2026-11), generalised for the kit: there the input
was phX's own reference run (the CPC's PPI OUTs, decoded); here it is any of the logs below.

INPUT (--format; every number decimal unless said, `#` starts a comment, blank lines skipped):

  ay5    FIELD LINE T REG VALUE    one AY register write a line: the field (VSync count) it
                                   happens in, the scanline and T state within the field (only
                                   used for the "where in the field" report). The kit's
                                   tools/cpc/cpcrun.py writes ay.log in exactly this form.
  ay3    FIELD REG VALUE           the same with no position (tools/cpc/cpcref_units.py's ay.log,
                                   where FIELD is the music tick).
  out    FIELD LINE T PORT VALUE   every Z80 OUT, PORT and VALUE in hex (cpcrun.py's out.log).
                                   The CPC drives the AY through the 8255 PPI (A11 low): an OUT
                                   to port A (&F4xx) puts a byte on the AY's bus; an OUT to port
                                   C (&F6xx) with bits 7-6 = 11 latches it as the register
                                   number, 10 writes it into that register, 00 releases the
                                   bus. (A player using &F7 bit set/reset on port C is not
                                   decoded: check the writes-by-register line.)
  auto   (default) ay5 or ay3 by the first data line's column count.

Registers start at 0. A Spectrum, ST or arcade source is the same once its writes are in ay3 /
ay5 form: write them out from whatever runs the original.

    python tools/music_extract.py LOG OUTDIR [--format F] [--music-time [--frame-end R]
                                  [--gap-end N]]

Writes OUTDIR/ay_fields.npy: uint8 [fields, 14], R0-R13 as they stand after each field's last
write, OUTDIR/ay_writes.npy (every write: field, pos, reg, value), and prints what the pipeline
needs to know: writes per field, the registers used, the hardware envelope (R11-R13 and the
volumes' bit 4: music_convert.py plays it as a timbre), the noise, and where in the field the
writes fall (one slot a field, or several).

--music-time: ONE ROW PER MUSIC FRAME, not per field. A frame closes at each write to register
--frame-end (default 12: phX's player sends R0-R12 every frame, R13 only when it changes). Use
it when the original's music is not one frame a field - phX's played one frame a disc sector
while loading, so its fields carried 0 or 2 frames there and the parts after a load waited on
the music's own frame counter; the BBC plays one frame a field, so the rows are the frames in
order. A TUNE is a run of frames ended by a silencing frame (R0..R(frame-end) all zero,
included; phX's player wrote one at each tune's end); between tunes, as many silent rows as
the original's fields between the silencing frame and the next tune's first frame. A silence
longer than --gap-end fields (default 500) ends the run's first pass; a second pass after it
is checked frame for frame against the first, not taken. Writes ay_fields.npy (the music-time
rows), ay_fields_field.npy (the per-field file) and tunes.json ([{tune, row, rows, src_first,
src_last}]): music_convert.py and music_pack.py read the tunes from it unless the config gives
them. Edit it, or put "tunes" in the config, when the detection is wrong for your player.
"""
import argparse
import json
import os
import sys

import numpy as np

WRITE = [('field', 'u4'), ('pos', 'u4'), ('reg', 'u1'), ('value', 'u1')]


def _lines(path):
    for line in open(path):
        line = line.split('#', 1)[0].split()
        if line:
            yield line


def read_log(path, fmt='auto'):
    """the AY writes as a structured array (field, pos, reg, value); pos = scanline, or 0"""
    if fmt == 'auto':
        first = next(_lines(path), None)
        if first is None:
            return np.zeros(0, WRITE)
        fmt = {3: 'ay3', 5: 'ay5'}.get(len(first))
        if fmt is None:
            sys.exit(f'{path}: {len(first)} columns - give --format')
    out = []
    if fmt == 'ay3':
        for f, r, v in _lines(path):
            out.append((int(f), 0, int(r) & 15, int(v) & 255))
    elif fmt == 'ay5':
        for f, ln, _t, r, v in _lines(path):
            out.append((int(f), int(ln), int(r) & 15, int(v) & 255))
    elif fmt == 'out':
        bus, sel = 0, 0
        for f, ln, _t, port, v in _lines(path):
            port, v = int(port, 16), int(v, 16)
            if port & 0x0800:
                continue                        # not the PPI
            fn = (port >> 8) & 3
            if fn == 0:
                bus = v
            elif fn == 2:
                top = v >> 6
                if top == 3:
                    sel = bus & 15
                elif top == 2:
                    out.append((int(f), int(ln), sel, bus))
    else:
        sys.exit(f'unknown --format {fmt}')
    return np.array(out, WRITE)


def per_field(w, nf=None):
    """uint8 [fields, 14]: the registers after each field's last write"""
    nf = (int(w['field'].max()) + 1 if len(w) else 0) if nf is None else nf
    regs = [0] * 16
    fields = np.zeros((nf, 14), np.uint8)
    cur = 0
    for f, r, v in zip(w['field'].tolist(), w['reg'].tolist(), w['value'].tolist()):
        while cur < f:
            fields[cur] = regs[:14]
            cur += 1
        regs[r] = v
    while cur < nf:
        fields[cur] = regs[:14]
        cur += 1
    return fields


def frames_of(w, frame_end=12):
    """one row per music frame (closed by a write to frame_end): the field of its first write,
    and the registers after its last"""
    regs = [0] * 14
    F, R, start = [], [], None
    for f, r, v in zip(w['field'].tolist(), w['reg'].tolist(), w['value'].tolist()):
        if r < 14:
            regs[r] = v
        if start is None:
            start = f
        if r == frame_end:
            F.append(start)
            R.append(list(regs))
            start = None
    return np.array(F, np.int64), np.array(R, np.uint8).reshape(-1, 14)


def find_tunes(F, R, frame_end=12, gap_end=500):
    """[(first frame, silencing frame)] of the first pass, and the frame the second starts at"""
    zero = (R[:, :frame_end + 1] == 0).all(1)
    tunes, i, second = [], 0, None
    while i < len(R):
        if zero[i]:
            i += 1
            continue
        j = i
        while j < len(R) and not zero[j]:
            j += 1
        last = min(j, len(R) - 1)
        tunes.append((i, last))
        nxt = np.nonzero(~zero[last + 1:])[0]
        if not len(nxt):
            break
        if F[last + 1 + nxt[0]] - F[last] > gap_end:
            second = last + 1 + int(nxt[0])
            break
        i = last + 1
    return tunes, second


def music_time(out, w, nf, frame_end=12, gap_end=500):
    F, R = frames_of(w, frame_end)
    if not len(R):
        sys.exit(f'no frames: nothing writes R{frame_end} (--frame-end)')
    per = np.bincount(F, minlength=nf)
    tunes, second = find_tunes(F, R, frame_end, gap_end)
    rows, table = [], []
    for k, (a, b) in enumerate(tunes):
        if k:
            rows += [np.zeros(14, np.uint8)] * max(0, int(F[a] - F[tunes[k - 1][1]] - 1))
        table.append({'tune': k + 1, 'row': len(rows), 'rows': int(b - a + 1),
                      'src_first': int(F[a]), 'src_last': int(F[b])})
        rows += list(R[a:b + 1])
    rows = np.array(rows, np.uint8).reshape(-1, 14)
    np.save(os.path.join(out, 'ay_fields.npy'), rows)
    json.dump(table, open(os.path.join(out, 'tunes.json'), 'w'), indent=1)
    print(f'music time: {len(R)} frames in the run; {len(rows)} rows ({len(rows) / 50:.1f} s):')
    for t in table:
        a, b = t['src_first'], t['src_last']
        z = int((per[a:b + 1] == 0).sum())
        d = int((per[a:b + 1] >= 2).sum())
        print(f"  tune {t['tune']}: rows {t['row']}-{t['row'] + t['rows'] - 1} ({t['rows']} frames, "
              f"{t['rows'] / 50:.1f} s), fields {a}-{b}: {z} fields with no frame, {d} with two")
    if second is not None and tunes:
        a0, b0 = tunes[0][0], tunes[-1][1]
        first = R[a0:b0 + 1]
        again = R[second:second + len(first)]
        same = int((again == first[:len(again)]).all(1).sum())
        print(f'second pass from field {int(F[second])}: {same} of {len(again)} frames '
              f'identical to the first (not taken)')
    return rows, table


def report(fields, w):
    nf = len(fields)
    per = np.bincount(w['field'], minlength=nf) if len(w) else np.zeros(nf, int)
    print(f'{nf} fields, {len(w)} AY writes; per field: min {per.min()}, max {per.max()}, '
          f'median {int(np.median(per))}')
    regs, cnt = np.unique(w['reg'], return_counts=True)
    print('writes by register:', dict(zip(regs.tolist(), cnt.tolist())))
    env = w[(w['reg'] >= 11) & (w['reg'] <= 13)]
    vb4 = w[(w['reg'] >= 8) & (w['reg'] <= 10) & ((w['value'] & 0x10) != 0)]
    r13 = sorted(set(w[w['reg'] == 13]['value'].tolist()))
    print(f'envelope: {len(env)} writes to R11-R13 (R13 shapes {r13}), {len(vb4)} volumes with '
          f'bit 4 set')
    mix = fields[:, 7]
    noisy = (mix & 0x38) != 0x38
    print(f'noise enabled on some channel in {int(noisy.sum())} of {nf} fields; noise periods '
          f'used: {sorted(set(fields[noisy, 6].tolist()))[:20]}')
    print(f'a tone disabled in {int(((mix & 7) != 0).sum())} fields; mixer values: '
          f'{sorted(set(mix.tolist()))[:20]}')
    if len(w) and w['pos'].any():
        h = np.histogram(w['pos'], bins=[0, 16, 32, 64, 128, 192, 256, 280, 300, 312, 10 ** 6])
        print('writes by scanline:', list(zip(h[1][:-1].tolist(), h[0].tolist())))
        multi = 0
        for f in np.unique(w['field']).tolist():
            p = w['pos'][w['field'] == f]
            if p.max() - p.min() > 32:
                multi += 1
        print(f'fields whose writes span more than 32 lines (more than one slot): {multi}')


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[1])
    ap.add_argument('log')
    ap.add_argument('out')
    ap.add_argument('--format', default='auto', choices=['auto', 'ay3', 'ay5', 'out'])
    ap.add_argument('--music-time', action='store_true')
    ap.add_argument('--frame-end', type=int, default=12)
    ap.add_argument('--gap-end', type=int, default=500)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    w = read_log(a.log, a.format)
    if not len(w):
        sys.exit(f'{a.log}: no AY writes')
    order = np.argsort(w['field'], kind='stable')
    w = w[order]
    fields = per_field(w)
    np.save(os.path.join(a.out, 'ay_writes.npy'), w)
    if a.music_time:
        np.save(os.path.join(a.out, 'ay_fields_field.npy'), fields)
        music_time(a.out, w, len(fields), a.frame_end, a.gap_end)
    else:
        np.save(os.path.join(a.out, 'ay_fields.npy'), fields)
    report(fields, w)


if __name__ == '__main__':
    main()
