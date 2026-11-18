"""
music_pack.py - SN fields (tools/music_convert.py) as the stream a 6502 player sends unchanged.

Fork this into your project's tools/; keep this header.

From the phX port (tools/music_pack.py, 2026-11), generalised for the kit: phX's tune split
rows, bank size and silent-build lengths are now the config's "pack" and "tunes" (tools/
music_config_example.json, made-up values).

THE FORMAT, one record a field: a count byte n (0-11), then n bytes for the SN76489 exactly as
they go to the chip - only what changed since the previous field:
  a tone N:        %1cc0nnnn (low 4 bits), %00nnnnnn (high 6), c = SN channel 0-2 (ay2sn.py's
                   state order; channel 2 is the one periodic noise is clocked by). A tone is
                   sent only when it is heard: its channel audible, or tone 2 clocking periodic
                   noise (its own attenuation is then 15).
  an attenuation:  %1cc1aaaa, c = 0-2 tones, 3 noise
  the noise:       %11100fff, only when it changes (a write resets the LFSR)
The player reads n and sends n bytes: no decoding at run time, at most 11 writes a field.
The chip state is tracked across records, so a stream must be played from its start: each
TUNE is packed from a fresh chip (its first record sets every attenuation), and so can start
on its own; chunks of one tune carry the state between them and play as one stream.
Every stream written is decoded back on an SN model and checked against sn_fields.npy before
this exits (decode()).

    python tools/music_pack.py DIR OUT.bin [--from F] [--max N]

One stream, every row from F (default: the first audible one) to the end, cut at a record
boundary to fit N bytes; DIR/sn_bytes.json is the bytes each field sends (for a harness).

    python tools/music_pack.py DIR --tunes [--config C.json]

Each tune (config "tunes", else DIR/tunes.json, else one) on its own from a fresh chip:
DIR/tuneK.bin, DIR/whole.bin (every row, one chip state throughout), and a table of each one's
size raw and as ZX02, unlimited and with the offset limited (-m 4096 / 1024 / 256: the window
a streaming decoder's ring must hold, lib/zx02stream.6502), and the writes a field.

    python tools/music_pack.py DIR --seq OUTDIR [--config C.json]

The streams for a sequence: each tune from a fresh chip, cut into chunks - at the rows in
config "pack": {"cuts": {"1": [1200]}} (rows from the tune's start: phX cut tune 1 where the
original loads its second half), and any chunk bigger than "bank" bytes (default 16384, a
sideways bank) at the last record boundary that fits. OUTDIR/tuneK[a,b,...].bin,
OUTDIR/music_seq.6502 (each chunk's NAME_SIZE / NAME_ROWS, each tune's TUNEK_ROW / TUNEK_LEN,
as Baron constants) and DIR/sn_rows.json (the bytes every row sends, the gaps between tunes
empty).

    python tools/music_pack.py --silent OUTDIR --config C.json

The same files as silence (every record n = 0) at the config's tune lengths and cuts: a build
without the reference run (the music is not the kit's to ship, nor yours to put in git). The
"bank" cut of a silent stream falls elsewhere than the real one's: put the real cut rows in
"cuts" (the --seq run prints them) to have both builds' chunks the same length in rows.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile

import numpy as np

MAX_WRITES = 11
HERE = os.path.dirname(os.path.abspath(__file__))


def _kit():
    """beeb_port_kit: installed, else $BEEB_PORT_KIT, else the kit checkout (../../py)"""
    try:
        import beeb_port_kit  # noqa: F401
        return True
    except ImportError:
        pass
    for root in (os.environ.get('BEEB_PORT_KIT'), os.path.join(HERE, '..', '..')):
        if root and os.path.isdir(os.path.join(root, 'py', 'beeb_port_kit')):
            sys.path.insert(0, os.path.join(root, 'py'))
            return True
    return False


# --- the format -----------------------------------------------------------------------------
def field_bytes(chip, cur):
    """the bytes that bring the chip (a dict of what it holds, updated) to this field's state"""
    out = []
    ctl = int(cur[6])
    periodic = ctl >= 0 and (ctl & 3) == 3
    for c in range(3):
        n, a = int(cur[2 * c]), int(cur[2 * c + 1])
        heard = a < 15 or (c == 2 and periodic and int(cur[7]) < 15)
        if heard and chip.get(('n', c)) != n:
            out += [0x80 | c << 5 | (n & 15), (n >> 4) & 63]
            chip[('n', c)] = n
    for c in range(3):
        a = int(cur[2 * c + 1])
        if chip.get(('a', c)) != a:
            out.append(0x90 | c << 5 | a)
            chip[('a', c)] = a
    if ctl >= 0 and chip.get('ctl') != ctl:
        out.append(0xE0 | ctl)
        chip['ctl'] = ctl
    na = int(cur[7])
    if chip.get(('a', 3)) != na:
        out.append(0xF0 | na)
        chip[('a', 3)] = na
    return out


def pack(sn, f0, f1, chip=None):
    """the stream for rows f0..f1-1 (from a fresh chip unless one is given): bytes, counts"""
    stream, counts = bytearray(), []
    chip = {} if chip is None else chip
    for f in range(f0, f1):
        b = field_bytes(chip, sn[f])
        assert len(b) <= MAX_WRITES, (f, b)
        stream.append(len(b))
        stream += bytes(b)
        counts.append(len(b))
    return bytes(stream), counts


def records(data):
    """the records of a stream: [bytes sent]"""
    out, i = [], 0
    while i < len(data):
        n = data[i]
        assert n <= MAX_WRITES, f'record at {i}: count {n}'
        out.append(list(data[i + 1:i + 1 + n]))
        i += 1 + n
    assert i == len(data), 'the stream ends inside a record'
    return out


class SN:
    """the SN76489's registers as the bytes leave them (None = never written)"""

    def __init__(self):
        self.n, self.a, self.ctl, self.latch = [None] * 3, [None] * 4, None, None

    def write(self, b):
        if b & 0x80:
            c, typ, d = (b >> 5) & 3, (b >> 4) & 1, b & 15
            self.latch = (c, typ)
            if typ:
                self.a[c] = d
            elif c == 3:
                self.ctl = d & 7
            else:
                self.n[c] = ((self.n[c] or 0) & ~15) | d
        else:
            c, typ = self.latch
            assert not typ and c < 3, 'a data byte after a non-tone latch'
            self.n[c] = (self.n[c] & 15) | ((b & 63) << 4)


def decode(data, sn, f0, chip=None):
    """play data on an SN model from row f0 of sn_fields and check every field: each
    attenuation, each heard tone, the noise control. Returns (rows checked, the model)."""
    chip = SN() if chip is None else chip
    for k, rec in enumerate(records(data)):
        for b in rec:
            chip.write(b)
        want = [int(x) for x in sn[f0 + k]]
        periodic = want[6] >= 0 and (want[6] & 3) == 3
        for c in range(3):
            assert chip.a[c] == want[2 * c + 1], (f0 + k, 'atten', c, chip.a, want)
            heard = want[2 * c + 1] < 15 or (c == 2 and periodic and want[7] < 15)
            if heard:
                assert chip.n[c] == want[2 * c], (f0 + k, 'tone', c, chip.n, want)
        assert chip.a[3] == want[7], (f0 + k, 'noise atten', chip.a, want)
        if want[6] >= 0:
            assert chip.ctl == want[6], (f0 + k, 'noise ctl', chip.ctl, want)
    return len(records(data)), chip


# --- sizes ----------------------------------------------------------------------------------
def _zx02_exe():
    for p in (os.environ.get('ZX02_EXE'), os.path.join(HERE, '..', 'bin', 'zx02.exe'),
              os.path.join(HERE, '..', 'bin', 'zx02'), shutil.which('zx02')):
        if p and os.path.isfile(p):
            return p
    return None


def zx02_size(data, limit=None):
    """ZX02 size of data (-m limit: the offset window), by zx02.exe if found, else the kit's
    beeb_port_kit/zx02.py (exact, slow), else None"""
    exe = _zx02_exe()
    if exe:
        with tempfile.TemporaryDirectory() as d:
            i, o = os.path.join(d, 'i.bin'), os.path.join(d, 'o.zx02')
            open(i, 'wb').write(data)
            subprocess.run([exe, '-f'] + (['-m', str(limit)] if limit else []) + [i, o],
                           check=True, capture_output=True)
            return os.path.getsize(o)
    if not _kit():
        return None
    from beeb_port_kit import zx02
    return len(zx02.compress(data, offset_limit=limit or zx02.MAX_OFFSET_ZX02))


# --- the config -----------------------------------------------------------------------------
def load(d, config):
    cfg = json.load(open(config)) if config else {}
    sn = np.load(os.path.join(d, 'sn_fields.npy')) if d else None
    tunes = cfg.get('tunes')
    if not tunes and d and os.path.exists(os.path.join(d, 'tunes.json')):
        tunes = json.load(open(os.path.join(d, 'tunes.json')))
    if not tunes:
        if sn is None:
            sys.exit('no tunes: give the config\'s "tunes"')
        tunes = [{'tune': 1, 'row': 0, 'rows': len(sn)}]
    p = cfg.get('pack', {})
    cuts = {int(k): sorted(int(x) for x in v) for k, v in p.get('cuts', {}).items()}
    return sn, tunes, cuts, int(p.get('bank', 16384))


def chunk(counts, cuts, bank):
    """[(first record, records)] of one tune: at the cut rows, then to fit bank bytes"""
    edges = [0] + [c for c in cuts if 0 < c < len(counts)] + [len(counts)]
    out = []
    for a, b in zip(edges, edges[1:]):
        k = a
        while k < b:
            size, j = 0, k
            while j < b and size + 1 + counts[j] <= bank:
                size += 1 + counts[j]
                j += 1
            assert j > k, 'a record bigger than the bank'
            out.append((k, j - k))
            k = j
    return out


def write_seq_header(path, chunks, tunes, note):
    with open(path, 'w', newline='\n') as f:
        f.write(f'\\ tools/music_pack.py {note}. Generated.\n')
        for name, size, nrows in chunks:
            f.write(f'{name.upper()}_SIZE = {size}\n{name.upper()}_ROWS = {nrows}\n')
        for t in tunes:
            f.write(f"TUNE{t['tune']}_ROW = {t['row']}\nTUNE{t['tune']}_LEN = {t['rows']}\n")


def seq(d, out, config):
    sn, tunes, cuts, bank = load(d, config)
    os.makedirs(out, exist_ok=True)
    chunks, rows = [], []
    for t in tunes:
        data, counts = pack(sn, t['row'], t['row'] + t['rows'])
        assert len(rows) <= t['row'], 'tunes overlap'
        rows += [[] for _ in range(t['row'] - len(rows))]       # the gap before it: silence
        rows += records(data)
        parts = chunk(counts, cuts.get(t['tune'], []), bank)
        model, i = None, 0
        for idx, (k, n) in enumerate(parts):
            size = sum(1 + c for c in counts[k:k + n])
            part = data[i:i + size]
            i += size
            name = f"tune{t['tune']}" + (chr(ord('a') + idx) if len(parts) > 1 else '')
            # the chunks play as one stream: the SN model carries over
            _, model = decode(part, sn, t['row'] + k, model)
            open(os.path.join(out, name + '.bin'), 'wb').write(part)
            chunks.append((name, len(part), n))
            print(f'{name}: rows {k}-{k + n - 1} of tune {t["tune"]}, {len(part)} bytes')
        assert i == len(data)
    write_seq_header(os.path.join(out, 'music_seq.6502'), chunks, tunes, '--seq: the music chunks')
    json.dump({'row0': 0, 'tunes': tunes, 'chunks': [list(c) for c in chunks], 'rows': rows},
              open(os.path.join(d, 'sn_rows.json'), 'w'))
    print(f'the whole sequence: {len(rows)} rows (silence after); every chunk decodes back to '
          f'sn_fields.npy')
    return chunks


def silent(out, config):
    _, tunes, cuts, bank = load(None, config)
    os.makedirs(out, exist_ok=True)
    chunks = []
    for t in tunes:
        parts = chunk([0] * t['rows'], cuts.get(t['tune'], []), bank)
        for idx, (k, n) in enumerate(parts):
            name = f"tune{t['tune']}" + (chr(ord('a') + idx) if len(parts) > 1 else '')
            open(os.path.join(out, name + '.bin'), 'wb').write(bytes(n))
            chunks.append((name, n, n))
    write_seq_header(os.path.join(out, 'music_seq.6502'), chunks, tunes,
                     '--silent: no reference run, the music is silence')
    print('NOTE: the music is silence (music_pack.py DIR --seq OUTDIR makes the real one)')
    return chunks


def tunes_report(d, config):
    sn, tunes, _, _ = load(d, config)
    whole, wc = pack(sn, 0, len(sn))
    decode(whole, sn, 0)
    open(os.path.join(d, 'whole.bin'), 'wb').write(whole)
    print(f'{"":8} {"fields":>6} {"s":>6} {"raw":>6} {"/field":>6} {"max n":>5} '
          f'{"ZX02":>6} {"m4096":>6} {"m1024":>6} {"m256":>6}')

    def line(name, data, c):
        z = [zx02_size(data, m) for m in (None, 4096, 1024, 256)]
        print(f'{name:8} {len(c):6} {len(c) / 50:6.1f} {len(data):6} '
              f'{len(data) / max(1, len(c)):6.2f} {max(c) if c else 0:5} '
              + ' '.join(f'{x if x is not None else "-":>6}' for x in z))
    line('whole', whole, wc)
    for t in tunes:
        data, c = pack(sn, t['row'], t['row'] + t['rows'])
        decode(data, sn, t['row'])
        open(os.path.join(d, f"tune{t['tune']}.bin"), 'wb').write(data)
        line(f"tune {t['tune']}", data, c)
    hist = np.bincount(wc, minlength=MAX_WRITES + 1)
    print('writes a field (whole):', {i: int(x) for i, x in enumerate(hist) if x})


def single(d, out, f0, cap):
    sn = np.load(os.path.join(d, 'sn_fields.npy'))
    if f0 is None:
        ay = os.path.join(d, 'ay_fields.npy')
        f0 = int(np.argmax(((np.load(ay)[:, 8:11] & 0x1F) != 0).any(1))) if os.path.exists(ay) \
            else 0
    stream, chip, per = bytearray(), {}, []
    for f in range(f0, len(sn)):
        b = field_bytes(chip, sn[f])
        assert len(b) <= MAX_WRITES, (f, b)
        if cap and len(stream) + 1 + len(b) > cap:
            break
        stream.append(len(b))
        stream += bytes(b)
        per.append(b)
    decode(bytes(stream), sn, f0)
    if os.path.dirname(out):
        os.makedirs(os.path.dirname(out), exist_ok=True)
    open(out, 'wb').write(bytes(stream))
    json.dump({'from_field': f0, 'fields': per}, open(os.path.join(d, 'sn_bytes.json'), 'w'))
    c = np.array([len(b) for b in per])
    z = zx02_size(bytes(stream)) if len(stream) <= 65536 or _zx02_exe() else None
    print(f'rows {f0}-{f0 + len(c) - 1} ({len(c)}, {len(c) / 50:.1f} s): {len(stream)} bytes raw '
          f'({len(stream) / max(1, len(c)):.2f} a field), writes a field: max {c.max()}, mean '
          f'{c.mean():.2f}' + (f'; ZX02 {z} bytes' if z is not None else '') + '; decodes back')


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[1])
    ap.add_argument('dir', nargs='?')
    ap.add_argument('out', nargs='?')
    ap.add_argument('--config', default=None)
    ap.add_argument('--from', dest='f0', type=int, default=None)
    ap.add_argument('--max', type=int, default=0, help='cut at a record to fit this many bytes')
    ap.add_argument('--tunes', action='store_true')
    ap.add_argument('--seq', metavar='OUTDIR')
    ap.add_argument('--silent', metavar='OUTDIR')
    a = ap.parse_args()
    if a.silent:
        silent(a.silent, a.config)
    elif a.seq:
        seq(a.dir, a.seq, a.config)
    elif a.tunes:
        tunes_report(a.dir, a.config)
    elif a.dir and a.out:
        single(a.dir, a.out, a.f0, a.max)
    else:
        ap.error('DIR OUT.bin, or DIR --tunes, DIR --seq OUTDIR, --silent OUTDIR')


if __name__ == '__main__':
    main()
