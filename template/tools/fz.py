#!/usr/bin/env python3
"""
fz.py - FZ, a byte-aligned LZ for data that must unpack FAST on the 6502 (lib/fzdepack.6502).

Fork this into your project's tools/; keep this header.

From the phX port (tools/fz.py, 2026-11), where two big unpacks had to fit in the background
time left beside a real-time effect. Unchanged but for the names; the codec is the same.

    python tools/fz.py pack IN OUT [--window W] [--max-len L]   # writes OUT, round-trip checked
    python tools/fz.py unpack IN OUT
    python tools/fz.py stat IN...           # packed size, tokens, the estimated 6502 cycles

WHY. ZX02 (lib/zx02depack.6502) packs ~25% smaller but reads its lengths a bit at a time: ~54
cycles a byte. FZ's tokens are whole bytes: ~25-30 cycles a byte (lib/fzdepack.6502, measured
by tools/fz_bench.py on phX's pictures and banks: ~29). Take it where the unpack's TIME is the
budget and ZX02 where the bytes are.

THE FORMAT. A stream of tokens, each one byte t, then:
    t = &00-&7F   a literal run: t + 1 bytes (1-128) follow, copied as they are
    t = &80-&BF   a near match: length (t AND &3F) + 2 (2-65), then one byte v: offset v + 1
                  (1-256) back from the output
    t = &C0-&FE   a far match: length (t AND &3F) + 3 (3-65), then lo, hi: offset hi.lo + 1
    t = &FF       the end
A match may overlap its own output (offset < length: a run), byte by byte forwards.

IN PLACE. The 6502 decoder runs forwards, so a stream may share memory with its output only if it
sits at the END: in_place_gap() is the number of bytes the stream must extend past the output's
end (0 or more) so that the writer never passes the reader. in_place_check() decodes it so,
byte by byte, and is the proof.

compress(window=): no match further back than window bytes (a stream decoded into a ring of that
size); compress(max_len=): no token longer than max_len bytes (a depacker that must reach a token
boundary every few hundred cycles, to be interrupted or time-sliced there).

The parse is optimal for this format's costs (a backward pass over every position, the longest
near and far match at each with every shorter length), the matches from hash chains.
"""
import sys

MAX_LIT = 128
NEAR_MIN, NEAR_MAX = 2, 65
FAR_MIN, FAR_MAX = 3, 65
END = 0xFF


def _matches(d, depth=1024, window=None):
    """for each position: (best near length, its offset), (best far length, its offset); offsets
    up to `window` only if given (a stream decoded into a ring of that size)"""
    n = len(d)
    heads = {}
    near = [(0, 0)] * n
    far = [(0, 0)] * n
    for i in range(n - 1):
        key = d[i] | (d[i + 1] << 8)
        lst = heads.get(key)
        bn = (0, 0)
        bf = (0, 0)
        if lst:
            for j in reversed(lst[-depth:]):
                o = i - j
                if window is not None and o > window:
                    break
                lim = min(FAR_MAX, n - i)
                l = 2
                while l < lim and d[j + l] == d[i + l]:
                    l += 1
                if o <= 256 and l > bn[0]:
                    bn = (min(l, NEAR_MAX), o)
                if l > bf[0]:
                    bf = (l, o)
                if bf[0] >= FAR_MAX and bn[0] >= NEAR_MAX:
                    break
            lst.append(i)
        else:
            heads[key] = [i]
        near[i] = bn
        far[i] = bf
    return near, far


def compress(d, window=None, max_len=None):
    """window: no match further back (a ring's size); max_len: no token longer (a depacker that
    must reach a token every few hundred cycles)"""
    d = bytes(d)
    n = len(d)
    near, far = _matches(d, window=window)
    if max_len is not None:
        near = [(min(l, max_len), o) for l, o in near]
        far = [(min(l, max_len), o) for l, o in far]
    INF = 1 << 60
    cost = [INF] * (n + 1)
    cost[n] = 0
    ch = [None] * (n + 1)
    for i in range(n - 1, -1, -1):
        best, bc = INF, None
        for L in range(1, min(MAX_LIT if max_len is None else min(MAX_LIT, max_len), n - i) + 1):
            c = 1 + L + cost[i + L]
            if c < best:
                best, bc = c, ('L', L)
        l, o = near[i]
        for L in range(NEAR_MIN, l + 1):
            c = 2 + cost[i + L]
            if c < best:
                best, bc = c, ('N', L, o)
        l, o = far[i]
        if l >= FAR_MIN:
            for L in range(FAR_MIN, l + 1):
                c = 3 + cost[i + L]
                if c < best:
                    best, bc = c, ('F', L, o)
        cost[i], ch[i] = best, bc
    out = bytearray()
    i = 0
    while i < n:
        c = ch[i]
        if c[0] == 'L':
            L = c[1]
            out.append(L - 1)
            out += d[i:i + L]
        elif c[0] == 'N':
            _, L, o = c
            out.append(0x80 | (L - NEAR_MIN))
            out.append(o - 1)
        else:
            _, L, o = c
            out.append(0xC0 | (L - FAR_MIN))
            out += bytes([(o - 1) & 0xFF, (o - 1) >> 8])
        i += c[1]
    out.append(END)
    out = bytes(out)
    assert decompress(out) == d, "fz: the round trip failed"
    return out


def tokens(z):
    """[(kind, length, src_bytes)] of a stream"""
    p, res = 0, []
    while True:
        t = z[p]
        if t == END:
            return res
        if t < 0x80:
            res.append(('L', t + 1, t + 2))
            p += t + 2
        elif t < 0xC0:
            res.append(('N', (t & 0x3F) + NEAR_MIN, 2))
            p += 2
        else:
            res.append(('F', (t & 0x3F) + FAR_MIN, 3))
            p += 3


def decompress(z):
    out = bytearray()
    p = 0
    while True:
        t = z[p]
        p += 1
        if t == END:
            return bytes(out)
        if t < 0x80:
            out += z[p:p + t + 1]
            p += t + 1
            continue
        if t < 0xC0:
            L = (t & 0x3F) + NEAR_MIN
            o = z[p] + 1
            p += 1
        else:
            L = (t & 0x3F) + FAR_MIN
            o = (z[p] | (z[p + 1] << 8)) + 1
            p += 2
        assert o <= len(out), "fz: offset before the start"
        for _ in range(L):
            out.append(out[-o])


def in_place_gap(z, outlen):
    """bytes the stream must reach past the output's end for an in-place forwards decode: placed
    so that it ends at out_end + gap, the reader is never behind the writer"""
    # the reader's position relative to the stream's start (r) and the writer's (w) when each
    # token is about to write: the stream starts at out_start + outlen + gap - len(z); a token's
    # source bytes must all be read before the writer passes them: w <= r_start + r at each byte
    p, w, worst = 0, 0, 0
    while True:
        t = z[p]
        if t == END:
            break
        if t < 0x80:
            L = t + 1
            # literal byte k (0..L-1) is read at p+1+k and written at w+k: need w+k < pos(p+1+k)
            worst = max(worst, w - (p + 1))
            p += 1 + L
            w += L
        else:
            L = (t & 0x3F) + (NEAR_MIN if t < 0xC0 else FAR_MIN)
            p += 2 if t < 0xC0 else 3
            # the writer may overrun the reader's next token during the copy: w + L - 1 < pos(p)
            worst = max(worst, w + L - p)
            w += L
    # position of stream byte q in memory = out_start + outlen + gap - len(z) + q; writer at
    # out_start + w; need out_start + w < out_start + outlen + gap - len(z) + q for every read q
    # that is still to come, i.e. gap > w - q - outlen + len(z) at the worst point
    assert w == outlen
    return max(1, worst - outlen + len(z) + 1)      # (1: the end marker is read after the last write)


def est_cycles(z, outlen):
    """the 6502 decoder's cycles (lib/fzdepack.6502's loop costs: tools/fz_bench.py measures)"""
    t = tokens(z)
    lit = sum(1 for k in t if k[0] == 'L')
    return lit * 45 + (len(t) - lit) * 72 + outlen * 18


def in_place_check(z, data, gap):
    """decode z placed to end gap bytes past the output's end, in ONE buffer, byte by byte in the
    6502 decoder's order (token, then each literal read and written, or each match byte): True if
    the output is data, i.e. the writer never overwrote a stream byte still to be read"""
    n = len(data)
    mem = bytearray(n + gap)
    base = n + gap - len(z)
    assert base >= 0, 'the stream is longer than the output plus the gap'
    mem[base:] = z
    p, w = base, 0
    while True:
        t = mem[p]
        p += 1
        if t == END:
            return bytes(mem[:n]) == data and w == n
        if t < 0x80:
            for _ in range(t + 1):
                mem[w] = mem[p]
                w += 1
                p += 1
            continue
        if t < 0xC0:
            L, o = (t & 0x3F) + NEAR_MIN, mem[p] + 1
            p += 1
        else:
            L, o = (t & 0x3F) + FAR_MIN, (mem[p] | (mem[p + 1] << 8)) + 1
            p += 2
        for _ in range(L):
            mem[w] = mem[w - o]
            w += 1


def main():
    import argparse
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[2])
    ap.add_argument('cmd', choices=['pack', 'unpack', 'stat'])
    ap.add_argument('files', nargs='+')
    ap.add_argument('--window', type=int, default=None)
    ap.add_argument('--max-len', type=int, default=None)
    a = ap.parse_args()
    if a.cmd == 'pack':
        d = open(a.files[0], 'rb').read()
        z = compress(d, window=a.window, max_len=a.max_len)
        open(a.files[1], 'wb').write(z)
        g = in_place_gap(z, len(d))
        assert in_place_check(z, d, g), 'fz: the in-place gap is too small'
        print(f'fz: {a.files[0]} {len(d)} -> {a.files[1]} {len(z)} (in-place gap {g})')
    elif a.cmd == 'unpack':
        open(a.files[1], 'wb').write(decompress(open(a.files[0], 'rb').read()))
    else:
        for f in a.files:
            d = open(f, 'rb').read()
            z = compress(d, window=a.window, max_len=a.max_len)
            print(f'{f}: {len(d)} -> {len(z)}, {len(tokens(z))} tokens, ~{est_cycles(z, len(d))} '
                  f'cycles, in-place gap {in_place_gap(z, len(d))}')


if __name__ == '__main__':
    main()
