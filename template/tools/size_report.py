#!/usr/bin/env python3
"""
size_report.py - where the crunch's packed bytes go (decision 15, docs/crunch.md).

Packs the payload with Shrinkler (tools/shrinkler.py, `-d -b -9`), decodes it with the oracle
charging every bit's exact cost to the output byte it produced, and totals the cost by section,
by source file and by label (a label owns the bytes from it to the next label in its section,
as in the symbol dump). The number to aim at is a span's PACKED cost, not its raw size: a
table of zeros costs nothing, a page of hand code costs most of its length.

The payload is the files of Baron's raw image named by --files (default: Game LOW BANK PLOT,
master's multi-file boot), concatenated in that order - the round-0 measure. Once the build
makes the single executable it writes build/<stem>.stream.json (the stream's segments) and
this reads that instead with --stream.

  python tools/size_report.py RAW.ssd SYMBOLS.json [--files A,B,..] [--top N] [--json OUT]
  python tools/size_report.py --stream build/iso.stream.json SYMBOLS.json [--top N]

KIT NOTE (2026-11-14): from Isometrikum's crunch as it stood. SECTION_OF and --files' default
name that project's files and sections; change them. Needs shrinkler.py beside it.
"""
import json
import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import shrinkler  # noqa: E402

SECTION_OF = {'Game': 'Game', 'LOW': 'Low', 'BANK': 'Bank', 'PLOT': 'Plot',
              'BANKN': 'Bank', 'PLOTN': 'Plot', 'LOWN': 'Low'}


def raw_files(ssd):
    d = open(ssd, 'rb').read()
    out = {}
    for i in range(d[0x105] // 8):
        name = d[8 + i * 8:15 + i * 8].decode('latin1').rstrip()
        e = d[0x108 + i * 8:0x110 + i * 8]
        load = e[0] | e[1] << 8
        ln = e[4] | e[5] << 8 | ((e[6] >> 4) & 3) << 16
        sec = e[7] | ((e[6] & 3) << 8)
        out[name] = (load, d[sec * 256:sec * 256 + ln])
    return out


def label_owner(symbols):
    """section name -> sorted [(address, label, source file)]"""
    a = json.load(open(symbols))['assemblies'][0]
    srcs = a['sources']
    own = {}
    for s in a['sections']:
        if not s.get('name') or 'labels' not in s:
            continue
        labs = sorted((v['value'], k, os.path.basename(srcs[v['source']].replace('\\', '/')))
                      for k, v in s['labels'].items() if isinstance(v['value'], int))
        own[s['name']] = labs
    return own


def main(argv):
    top = int(argv[argv.index('--top') + 1]) if '--top' in argv else 25
    jout = argv[argv.index('--json') + 1] if '--json' in argv else None
    if '--stream' in argv:
        spec = json.load(open(argv[argv.index('--stream') + 1]))
        symbols = [a for a in argv if a.endswith('.json') and a != argv[argv.index('--stream') + 1]][0]
        segs = [(g['name'], g['section'], g['org'], bytes.fromhex(g['hex']), g['pack'])
                for g in spec['segments']]
    else:
        ssd, symbols = argv[0], argv[1]
        names = (argv[argv.index('--files') + 1] if '--files' in argv else 'Game,LOW,BANK,PLOT').split(',')
        files = raw_files(ssd)
        segs = [(n, SECTION_OF[n], files[n][0] if n not in ('BANK', 'PLOT', 'BANKN', 'PLOTN') else 0x8000,
                 files[n][1], True) for n in names]
        segs = [('ALL', None, 0, b''.join(x[3] for x in segs), True)] and segs
    # each packed segment is its own stream (the executable's layout); with --files the files
    # are packed as one stream, the round-0 measure
    costs, total = [], 0
    if '--stream' in argv:
        for name, sec, org, data, packed in segs:
            if packed:
                stream = shrinkler.compress(data)
                c = []
                shrinkler.decompress(stream, costs=c)
                costs += c
                total += len(stream)
            else:
                costs += [8.0] * len(data)
                total += len(data)
        payload = b''.join(x[3] for x in segs)
        print(f'executable {spec["length"]:,} bytes; segments {len(payload):,} raw -> {total:,}')
    else:
        payload = b''.join(x[3] for x in segs)
        stream = shrinkler.compress(payload)
        shrinkler.decompress(stream, costs=costs)
        total = len(stream)
        print(f'payload {len(payload):,} raw -> {total:,} packed (cost map {sum(costs) / 8:,.0f} bytes)')

    owners = label_owner(symbols)
    by_sec, by_src, by_lab = defaultdict(float), defaultdict(float), defaultdict(lambda: [0.0, 0])
    pos = 0
    for name, sec, org, data, _ in segs:
        labs = owners.get(sec, [])
        li = 0
        for i in range(len(data)):
            addr = org + i
            while li + 1 < len(labs) and labs[li + 1][0] <= addr:
                li += 1
            c = costs[pos + i] / 8
            by_sec[name] += c
            if labs and labs[li][0] <= addr:
                _, lab, src = labs[li]
            else:
                lab, src = f'{name}:?', '?'
            by_src[(name, src)] += c
            by_lab[(name, lab)][0] += c
            by_lab[(name, lab)][1] += 1
        pos += len(data)

    print('\nby file:')
    for name, _, _, data, packed in segs:
        print(f'  {name:6} {len(data):7,} raw  {by_sec[name]:7,.0f} {"packed" if packed else "as is"}')
    print('\nby source:')
    for (name, src), c in sorted(by_src.items(), key=lambda x: -x[1]):
        if c >= 1:
            print(f'  {c:7,.0f}  {name:6} {src}')
    print(f'\nlabels by packed cost (top {top}):')
    for (name, lab), (c, n) in sorted(by_lab.items(), key=lambda x: -x[1][0])[:top]:
        print(f'  {c:7,.0f} packed  {n:6,} raw  {name:6} {lab}')
    if jout:
        json.dump({'raw': len(payload), 'packed': total,
                   'labels': [{'file': n, 'label': l, 'packed': round(c, 1), 'raw': r}
                              for (n, l), (c, r) in sorted(by_lab.items(), key=lambda x: -x[1][0])]},
                  open(jout, 'w'), indent=1)
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
