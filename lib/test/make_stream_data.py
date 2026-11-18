#!/usr/bin/env python3
"""make_stream_data.py - the packed test data for fz_test.mjs and zx02stream_test.mjs.

    python lib/test/make_stream_data.py OUTDIR RING_BYTES        (from the kit's root)

Synthetic, deterministic data shaped like what a stream carries (short records from a small
vocabulary, some literal noise, runs): nothing from any original. Writes, in OUTDIR:
  zst_a.zx02, zst_b.zx02   two ZX02 streams packed with -m RING_BYTES (offsets inside the ring)
  zst_raw.bin              what the two decode to, one after the other
  fzt.fz, fzt_raw.bin      an FZ stream and its output
  fzt2.fz, fzt2_raw.bin    a second, decoded IN PLACE (the stream at the output's end + its gap)
  stream_data.6502         the sizes and the in-place gap, as Baron constants
and prints them as JSON. ZX02 by $ZX02_EXE / template/bin/zx02.exe, else the kit's zx02.py.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

KIT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
sys.path.insert(0, os.path.join(KIT, 'py'))
sys.path.insert(0, os.path.join(KIT, 'template', 'tools'))
import fz  # noqa: E402
from beeb_port_kit import zx02  # noqa: E402


def lcg(seed):
    x = seed
    while True:
        x = (x * 1103515245 + 12345) & 0x7FFFFFFF
        yield x >> 8


def synth(n, seed):
    r = lcg(seed)
    vocab = [bytes(next(r) & 255 for _ in range(3 + next(r) % 9)) for _ in range(40)]
    out = bytearray()
    while len(out) < n:
        k = next(r) % 10
        if k < 7:
            out += vocab[next(r) % len(vocab)]
        elif k < 9:
            out += bytes(next(r) & 255 for _ in range(1 + next(r) % 6))
        else:
            out += bytes([next(r) & 255]) * (2 + next(r) % 70)
    return bytes(out[:n])


def zx02_pack(data, limit):
    exe = os.environ.get('ZX02_EXE') or os.path.join(KIT, 'template', 'bin', 'zx02.exe')
    if not os.path.isfile(exe):
        exe = shutil.which('zx02')
    if exe:
        with tempfile.TemporaryDirectory() as d:
            i, o = os.path.join(d, 'i'), os.path.join(d, 'o')
            open(i, 'wb').write(data)
            subprocess.run([exe, '-f', '-m', str(limit), i, o], check=True, capture_output=True)
            z = open(o, 'rb').read()
    else:
        z = zx02.compress(data, offset_limit=limit)
    assert zx02.decompress(z) == data
    return z


def main():
    out, ring = sys.argv[1], int(sys.argv[2])
    os.makedirs(out, exist_ok=True)
    a, b = synth(5500, 1), synth(3500, 2)
    za, zb = zx02_pack(a, ring), zx02_pack(b, ring)
    f1, f2 = synth(6000, 3), synth(4000, 4)
    z1, z2 = fz.compress(f1), fz.compress(f2)
    assert fz.decompress(z1) == f1 and fz.decompress(z2) == f2
    gap = fz.in_place_gap(z2, len(f2))
    assert fz.in_place_check(z2, f2, gap)
    files = {'zst_a.zx02': za, 'zst_b.zx02': zb, 'zst_raw.bin': a + b,
             'fzt.fz': z1, 'fzt_raw.bin': f1, 'fzt2.fz': z2, 'fzt2_raw.bin': f2}
    for k, v in files.items():
        open(os.path.join(out, k), 'wb').write(v)
    info = {'ZST_A_LEN': len(a), 'ZST_B_LEN': len(b), 'ZST_A_PACKED': len(za),
            'ZST_B_PACKED': len(zb), 'FZT_LEN': len(f1), 'FZT_PACKED': len(z1),
            'FZT2_LEN': len(f2), 'FZT2_PACKED': len(z2), 'FZT2_GAP': gap}
    with open(os.path.join(out, 'stream_data.6502'), 'w', newline='\n') as f:
        f.write('\\ lib/test/make_stream_data.py. Generated.\n')
        for k, v in info.items():
            f.write(f'{k} = {v}\n')
    print(json.dumps(info))


if __name__ == '__main__':
    main()
