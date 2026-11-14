#!/usr/bin/env python3
"""
grind_bytes.py - the crunch's grind (decision 15, docs/crunch.md) is for BYTES: the kit's
beeb-micro-grind weighs windows by measured cycles and measures a pass's work; this weighs them
by Shrinkler cost and measures the executables' lengths. tools/grind_config.py calls both.

    python tools/grind_bytes.py profile STREAM.json OUT.json
        the executable's cost map (tools/size_report.py's: every output byte's -log2 p bits,
        packed segments; 8 bits a byte for the unpacked stub) in tools/pcprof.mjs's --out shape,
        so `grind.py windows --profile OUT.json` orders windows by packed bytes. Keys follow
        grind_config.SEGMENT_BANK: BANK's addresses as 1 << 16 | addr, PLOT's as 2 << 16 | addr
    python tools/grind_bytes.py measure IMAGE.ssd
        the release disc's ISO and ISON lengths, as a JSON line {"iso": n, "ison": n}

KIT NOTE (2026-11-14): from Isometrikum's crunch. BANK_OF and the ISO/ISON names in `measure`
are that project's; grind_config.py's UNIT/SCORE (commented in the template's) switch the grind
to bytes. Needs dfs.py and shrinkler.py beside it.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dfs        # noqa: E402
import shrinkler  # noqa: E402

BANK_OF = {'Bank': 1, 'Plot': 2}      # grind_config.SEGMENT_BANK


def profile(stream_json, out):
    spec = json.load(open(stream_json))
    pc = {}
    total = 0.0
    for g in spec['segments']:
        data = bytes.fromhex(g['hex'])
        if g['pack']:
            c = []
            shrinkler.decompress(shrinkler.compress(data), costs=c)
        else:
            c = [8.0] * len(data)
        bank = BANK_OF.get(g['section'])
        for i, bits in enumerate(c):
            a = g['org'] + i
            key = (bank << 16 | a) if bank is not None else a
            pc[f'run:{key}'] = pc.get(f'run:{key}', 0) + bits / 8
            total += bits / 8
    json.dump({'passes': 1, 'pc': pc, 'what': 'packed bytes, not cycles (tools/grind_bytes.py)'},
              open(out, 'w'))
    print(f'{stream_json}: {total:,.0f} packed bytes mapped -> {out}')


def measure(img):
    d = dfs.read_image(img)
    print(json.dumps({'iso': len(d.files['ISO'].data), 'ison': len(d.files['ISON'].data)}))


if __name__ == '__main__':
    if sys.argv[1:2] == ['profile'] and len(sys.argv) == 4:
        profile(sys.argv[2], sys.argv[3])
    elif sys.argv[1:2] == ['measure'] and len(sys.argv) == 3:
        measure(sys.argv[2])
    else:
        raise SystemExit(__doc__)
