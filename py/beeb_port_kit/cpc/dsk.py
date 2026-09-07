"""
dsk.py - Amstrad CPC disc images (.dsk, standard and Extended) and their
AMSDOS catalogue, so a CPC port's work discs can be read for their art.

beeb-port-kit: from
  https://github.com/kieranhj/edge-beeb/blob/master/tools/cpc/dsk.py
Proven: Axelay's Edge Grinder CPC work discs (sprites, screens, palettes)
were all pulled through Dsk.catalogue(), and the compiled sprites read from
the game's own binary matched the SPRITES.BIN copies frame for frame.
Fork this into your project's tools/; keep this header.

Data-format discs only (sectors &C1-&C9, 9 a track, 1K blocks, the catalogue
in the first four sectors of track 0). A system-format disc (&41-&49, two
reserved tracks) needs the two constants below changed; nothing else.
"""

import os
import struct
import sys

FIRST_SECTOR = 0xC1         # data format; system format is &41
CATALOGUE_TRACK = 0         # data format; system format is 2
SECTORS_PER_TRACK = 9


class Dsk:
    def __init__(self, path_or_bytes):
        if isinstance(path_or_bytes, (str, os.PathLike)):
            with open(path_or_bytes, "rb") as f:
                d = f.read()
        else:
            d = bytes(path_or_bytes)
        self.ext = d[:16] == b"EXTENDED CPC DSK"
        ntrk, nsid = d[0x30], d[0x31]
        self.sectors = {}          # (track, side, sectorid) -> bytes
        off = 0x100
        if self.ext:
            sizes = [d[0x34 + i] * 256 for i in range(ntrk * nsid)]
        else:
            tlen = struct.unpack("<H", d[0x32:0x34])[0]
            sizes = [tlen] * (ntrk * nsid)
        for i, sz in enumerate(sizes):
            if sz == 0:
                continue
            t = d[off:off + sz]
            assert t[:10] == b"Track-Info", t[:16]
            trk, side = t[0x10], t[0x11]
            nsec = t[0x15]
            p = 0x100
            for s in range(nsec):
                e = t[0x18 + s * 8: 0x20 + s * 8]
                slen = struct.unpack("<H", e[6:8])[0] or (128 << e[3])
                self.sectors[(trk, side, e[2])] = t[p:p + slen]
                p += slen
            off += sz

    def catalogue(self):
        """(user, name, ext) -> file contents, AMSDOS header included if the
        file has one (see amsdos_header())."""
        cat = b"".join(self.sectors[(CATALOGUE_TRACK, 0, FIRST_SECTOR + s)]
                       for s in range(4))
        extents = {}
        for i in range(0, len(cat), 32):
            e = cat[i:i + 32]
            if e[0] == 0xE5:                       # deleted
                continue
            name = e[1:9].decode("latin1").rstrip()
            ext = bytes(b & 0x7F for b in e[9:12]).decode("latin1").rstrip()
            data = b""
            for block in e[16:32]:
                if not block:
                    continue
                for half in range(2):              # a 1K block is two sectors
                    trk, sec = divmod(block * 2 + half, SECTORS_PER_TRACK)
                    data += self.sectors[(CATALOGUE_TRACK + trk, 0, FIRST_SECTOR + sec)]
            key = (e[0], name, ext)
            extents.setdefault(key, {})[e[12] + e[14] * 32] = data[:e[15] * 128]
        return {k: b"".join(v[n] for n in sorted(v)) for k, v in extents.items()}


def amsdos_header(data):
    """The AMSDOS header's (type, load, length, exec) if `data` starts with a
    valid one (checksum over the first 67 bytes, and a non-zero length -
    without that test a block of zeros passes, and a blank screen loses its
    first 128 bytes), else None."""
    if len(data) >= 128 and sum(data[:67]) & 0xFFFF == data[67] | (data[68] << 8):
        length = struct.unpack("<H", data[24:26])[0]
        if length:
            return (data[18], struct.unpack("<H", data[21:23])[0], length,
                    struct.unpack("<H", data[26:28])[0])
    return None


def strip_amsdos(data):
    """`data` without its AMSDOS header, if it has one."""
    return data[128:] if amsdos_header(data) else data


if __name__ == "__main__":
    dsk = Dsk(sys.argv[1])
    outdir = sys.argv[2] if len(sys.argv) > 2 else None
    for (user, name, ext), data in sorted(dsk.catalogue().items()):
        hdr = amsdos_header(data)
        note = (f"  AMSDOS type={hdr[0]} load=&{hdr[1]:04X} len={hdr[2]} exec=&{hdr[3]:04X}"
                if hdr else "")
        print(f"{user}:{name}.{ext}  {len(data)} bytes{note}")
        if outdir:
            os.makedirs(outdir, exist_ok=True)
            with open(os.path.join(outdir, f"{name}.{ext}".strip(".")), "wb") as f:
                f.write(data)
