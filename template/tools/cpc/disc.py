"""
disc.py - an EXTENDED (or standard) CPC DSK as tracks of sectors, for the FDC model (fdc.py).
From the phX port, 2026-11 (its tools/disc.py). Changed here: amsdos_file takes NAME.EXT as
well as NAME, takes a file's extents in extent order, and returns a headerless file whole (with
hdr None) instead of reading garbage as a header; the CLI lists the catalogue.

A demo disc is often mixed: phX's had tracks 0-1 in AMSDOS DATA format (9 x 512, IDs &C1-&C9)
and every other track-side in a loader's own 10 x 512 (IDs &01-&0A). The tracks are kept as
the DSK has them; only amsdos_file assumes the DATA format.

    d = Disc(open('game.dsk', 'rb').read())
    d.track(cyl, side)            -> list of Sector, in the track's physical order
    d.find(cyl, side, c, h, r, n) -> the Sector whose ID matches, or None
    d.gap3(cyl, side)             -> the Track-Info GAP3 byte (&4E if the track is absent)
    d.catalogue()                 -> [(user, 'NAME.EXT', extents)] from the AMSDOS directory
    d.amsdos_file('NAME[.EXT]')   -> (header dict or None, data) from the catalogue (side 0)

    python disc.py DSK            prints the layout and the AMSDOS catalogue

Known limits: amsdos_file reads side 0 in DATA format only (blocks of 1K from &C1 on track 0;
not SYSTEM/VENDOR format, whose directory starts on track 2 at &41); any user number matches;
the header is taken as AMSDOS's only if its checksum (bytes 0-66, at 67-68) holds. Weak and
multiple-copy sectors (an EXTENDED DSK's longer data fields) are kept as one blob.
"""
import sys


class Sector:
    __slots__ = ('c', 'h', 'r', 'n', 'st1', 'st2', 'data')

    def __init__(self, c, h, r, n, st1, st2, data):
        self.c, self.h, self.r, self.n, self.st1, self.st2, self.data = c, h, r, n, st1, st2, data

    def __repr__(self):
        return f'Sector(C={self.c} H={self.h} R={self.r:#04x} N={self.n} {len(self.data)} B)'


class Disc:
    def __init__(self, raw):
        if raw[:8] == b'EXTENDED':
            ext = True
        elif raw[:8] == b'MV - CPC':
            ext = False
        else:
            raise ValueError('not a CPC DSK')
        self.ntracks, self.nsides = raw[48], raw[49]
        n = self.ntracks * self.nsides
        sizes = [raw[52 + i] * 256 for i in range(n)] if ext else [raw[50] | raw[51] << 8] * n
        self.tracks = {}
        self.gaps = {}                  # (cyl, side) -> the track's GAP3 (Track-Info byte 22)
        off = 256
        for i in range(n):
            sz = sizes[i]
            if not sz:
                continue
            tb = raw[off:off + sz]
            off += sz
            assert tb[:10] == b'Track-Info', f'track {i}'
            cyl, side, nsec = tb[16], tb[17], tb[21]
            secs, p = [], 256
            for k in range(nsec):
                e = tb[24 + 8 * k:32 + 8 * k]
                ln = (e[6] | e[7] << 8) if ext else 128 << tb[20]
                secs.append(Sector(e[0], e[1], e[2], e[3], e[4], e[5], bytes(tb[p:p + ln])))
                p += ln
            self.tracks[(cyl, side)] = secs
            self.gaps[(cyl, side)] = tb[22]

    def track(self, cyl, side):
        return self.tracks.get((cyl, side), [])

    def gap3(self, cyl, side):
        return self.gaps.get((cyl, side), 0x4E)

    def find(self, cyl, side, c, h, r, n):
        for s in self.track(cyl, side):
            if s.c == c and s.h == h and s.r == r and s.n == n:
                return s
        return None

    # ------------------------------------------------------------------ AMSDOS (DATA format)
    def _sec(self, i):
        """the i-th 512-byte sector of side 0 in DATA format order (&C1-&C9 a track)"""
        t, sid = divmod(i, 9)
        s = self.find(t, 0, t, 0, 0xC1 + sid, 2)
        if s is None:
            raise KeyError(f'no DATA-format sector &{0xC1 + sid:02X} on track {t}')
        return s.data

    def _entries(self):
        cat = b''.join(self._sec(i) for i in range(4))
        for i in range(64):
            e = cat[32 * i:32 * i + 32]
            if e[0] == 0xE5:
                continue
            name = bytes(x & 0x7F for x in e[1:9]).decode('latin1').rstrip()
            ext = bytes(x & 0x7F for x in e[9:12]).decode('latin1').rstrip()
            yield e[0], name, ext, e[12], [b for b in e[16:32] if b]

    def catalogue(self):
        files = {}
        for user, name, ext, extent, _ in self._entries():
            k = (user, f'{name}.{ext}' if ext else name)
            files[k] = files.get(k, 0) + 1
        return [(u, n, x) for (u, n), x in sorted(files.items())]

    def amsdos_file(self, name):
        """an AMSDOS file on side 0 by NAME or NAME.EXT (a bare NAME matches any extension)"""
        want_n, _, want_x = name.upper().partition('.')
        exts = []
        for user, n, x, extent, blocks in self._entries():
            if n.upper() == want_n and (not want_x or x.upper() == want_x):
                exts.append((extent, blocks))
        if not exts:
            raise KeyError(name)
        blocks = [b for _, bl in sorted(exts) for b in bl]
        data = b''.join(self._sec(2 * b) + self._sec(2 * b + 1) for b in blocks)
        h = data[:128]
        if len(h) == 128 and sum(h[:67]) & 0xFFFF == (h[67] | h[68] << 8):
            hdr = dict(type=h[18], load=h[21] | h[22] << 8, length=h[24] | h[25] << 8,
                       exec=h[26] | h[27] << 8)
            return hdr, data[128:128 + hdr['length']]
        return None, data                   # no AMSDOS header: the blocks as they are


if __name__ == '__main__':
    if len(sys.argv) != 2 or sys.argv[1] in ('-h', '--help'):
        print(__doc__)
        sys.exit(0)
    d = Disc(open(sys.argv[1], 'rb').read())
    print(f'{d.ntracks} tracks, {d.nsides} sides')
    kinds = {}
    for (c, s), secs in sorted(d.tracks.items()):
        if not secs:
            continue
        key = (len(secs), tuple(sorted({x.n for x in secs})), min(x.r for x in secs))
        kinds.setdefault(key, []).append((c, s))
    for k, v in kinds.items():
        print(f'  {k[0]} sectors, N={k[1]}, first ID &{k[2]:02X}: {len(v)} track-sides, '
              f'{v[0]}..{v[-1]}')
    try:
        cat = d.catalogue()
    except KeyError as e:
        print(f'no AMSDOS DATA-format catalogue ({e})')
        sys.exit(0)
    for user, name, extents in cat:
        hdr, data = d.amsdos_file(name)
        what = (f'load &{hdr["load"]:04X} exec &{hdr["exec"]:04X} {hdr["length"]} B' if hdr
                else f'no header, {len(data)} B')
        print(f'  user {user} {name:12s} {extents} extent(s): {what}')
