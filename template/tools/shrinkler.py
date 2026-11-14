#!/usr/bin/env python3
"""
shrinkler.py - Shrinkler raw-data streams for the crunch (decision 15, docs/crunch.md).

  compress(data, exe)   run the vendored compressor (tools/shrinklersrc/, built into bin/) as
                        `-d -b -p -9`: raw data, no parity context (unShrinkler's
                        unshrinkler_PARITY=0), no progress output, the strongest preset; then
                        round-trip the stream through decompress() and stop if it is not the data
  decompress(stream)    the oracle: upstream's RangeDecoder.h + LZDecoder.h + Decoder.h
                        (askeksa/Shrinkler 17cff11), transcribed line for line

The oracle is what makes the compressor safe to trust, as tools/zx02.py is for ZX02: a stream
reaches the disc only after it decodes to exactly the input.

  python tools/shrinkler.py pack IN OUT [--exe PATH] [--level N]
  python tools/shrinkler.py unpack IN OUT [--parity]
"""
import math
import os
import subprocess
import sys
import tempfile

ADJUST_SHIFT = 4
NUM_SINGLE_CONTEXTS = 1
CONTEXT_KIND = 0
CONTEXT_REPEATED = -1
CONTEXT_GROUP_OFFSET = 2
CONTEXT_GROUP_LENGTH = 3


def decompress(stream, parity=False, costs=None):
    """Decode a raw Shrinkler stream (no header) to bytes. With costs=[] it also fills that list
    with the packed bits each output byte cost: every decoded bit's exact cost, -log2 of the
    probability the coder gave it, charged to the literal or the copy it belongs to (a copy's
    spread evenly over its bytes); the bits of the end marker go to the last byte."""
    contexts = [0x8000] * (NUM_SINGLE_CONTEXTS + 4 * 256)
    nbits = len(stream) * 8
    st = {'bit': 0, 'size': 1, 'value': 0}

    def get_bit():
        i = st['bit']
        st['bit'] = i + 1
        if i >= nbits:
            return 0
        return (stream[i >> 3] >> ((~i) & 7)) & 1

    acc = [0.0]

    def decode(ctx):
        prob = contexts[ctx]
        if costs is not None:
            acc[0] -= math.log2((prob if decode_bit(ctx) else 0x10000 - prob) / 65536)
            return st['last']
        return decode_bit(ctx)

    def decode_bit(ctx):
        prob = contexts[ctx]
        while st['size'] < 0x8000:
            st['size'] <<= 1
            st['value'] = (st['value'] << 1) | get_bit()
        threshold = (st['size'] * prob) >> 16
        if st['value'] >= threshold:
            st['value'] -= threshold
            st['size'] -= threshold
            contexts[ctx] = prob - (prob >> ADJUST_SHIFT)
            st['last'] = 0
            return 0
        st['size'] = threshold
        contexts[ctx] = prob + (0xFFFF >> ADJUST_SHIFT) - (prob >> ADJUST_SHIFT)
        st['last'] = 1
        return 1

    def lz(ctx):
        return decode(NUM_SINGLE_CONTEXTS + ctx)

    def number(group):
        base = NUM_SINGLE_CONTEXTS + (group << 8)
        i = 0
        while decode(base + i * 2 + 2):
            i += 1
        n = 1
        while i >= 0:
            n = (n << 1) | decode(base + i * 2 + 1)
            i -= 1
        return n

    out = bytearray()
    pmask = 1 if parity else 0
    ref = prev_was_ref = False
    offset = 0
    while True:
        if ref:
            repeated = False
            if not prev_was_ref:
                repeated = lz(CONTEXT_REPEATED)
            if not repeated:
                offset = number(CONTEXT_GROUP_OFFSET) - 2
                if offset == 0:
                    break
            length = number(CONTEXT_GROUP_LENGTH)
            if offset > len(out):
                raise ValueError(f'reference {offset} back from {len(out)}')
            for _ in range(length):
                out.append(out[-offset])
            if costs is not None:
                costs.extend([acc[0] / length] * length)
                acc[0] = 0.0
            prev_was_ref = True
        else:
            parity_bit = len(out) & pmask
            ctx = 1
            for _ in range(8):
                ctx = (ctx << 1) | lz((parity_bit << 8) | ctx)
            out.append(ctx & 0xFF)
            if costs is not None:
                costs.append(acc[0])
                acc[0] = 0.0
            prev_was_ref = False
        ref = lz(CONTEXT_KIND + ((len(out) & pmask) << 8))
    if costs is not None and costs:
        costs[-1] += acc[0]
    return bytes(out)


def find_exe(exe=None):
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for c in (exe, os.environ.get('SHRINKLER'), os.path.join(root, 'bin', 'shrinkler.exe'),
              os.path.join(root, 'bin', 'shrinkler')):
        if c and os.path.isfile(c):
            return c
    sys.exit('shrinkler: no compressor (build it from tools/shrinklersrc: build.ps1 or make)')


def compress(data, exe=None, level=9):
    exe = find_exe(exe)
    with tempfile.TemporaryDirectory() as d:
        src, dst = os.path.join(d, 'in.bin'), os.path.join(d, 'out.shr')
        with open(src, 'wb') as f:
            f.write(data)
        r = subprocess.run([exe, '-d', '-b', '-p', f'-{level}', src, dst],
                           capture_output=True, text=True)
        if r.returncode != 0:
            sys.exit(f'shrinkler failed ({r.returncode}):\n{r.stdout}{r.stderr}')
        with open(dst, 'rb') as f:
            stream = f.read()
    if decompress(stream) != bytes(data):
        sys.exit('shrinkler: the stream does not decode to its input (tools/shrinkler.py)')
    return stream


def main(argv):
    if len(argv) >= 3 and argv[0] in ('pack', 'unpack'):
        exe = argv[argv.index('--exe') + 1] if '--exe' in argv else None
        level = int(argv[argv.index('--level') + 1]) if '--level' in argv else 9
        data = open(argv[1], 'rb').read()
        if argv[0] == 'pack':
            out = compress(data, exe, level)
        else:
            out = decompress(data, '--parity' in argv)
        open(argv[2], 'wb').write(out)
        print(f'{argv[1]} {len(data)} -> {argv[2]} {len(out)}')
        return 0
    print(__doc__)
    return 2


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
