"""
dfs.py - Acorn DFS single-sided disc images (.ssd): read the catalogue, lay
files out in a chosen order, write the image, pad it, and the two checks a
compressed disc needs before it is written.

beeb-port-kit: the generic half of tools/make_disc.py in both ports.
  https://github.com/kieranhj/paradroid-beeb/blob/main/tools/make_disc.py
      read_catalogue, build_image, in_place_delta (the overtake margin)
  https://github.com/kieranhj/edge-beeb/blob/master/tools/make_disc.py
      the same reader and writer, plus the stream/output overlap refusal
      and the stream-top check
Proven: both shipping discs are this writer's output. The catalogue format
(descending start-sector order, the 18-bit load/exec/length in byte 6, the
sector count in bytes 6-7 of sector 1) is what beebasm and Baron both write,
and what the
Master's DFS and jsbeeb/b-em read. in_place_delta was measured against the
Paradroid font stream, which unpacks over itself at &3000 from &3700; the
rule "landing address >= dest + delta + 1" is what let it do that.
Fork this into your project's tools/; keep this header.

What the ports' make_disc.py does with this module, in order:

    img = read_image(raw_ssd)                  # the assembler's own SSD
    for name, (stream, dest) in COMPRESSED.items():
        raw = img.files[name].data
        packed = compress(raw, exe)            # the exe, checked by zx02.py
        check_stream(name, stream, packed, dest, raw, top=STREAM_TOP[stream])
        img.files[name].replace(packed, load=stream, exec=stream)
    out = build_image(img.files, LAYOUT, img.title, img.cycle, img.opt)
    write out                                  # pad(out) only to publish

The COMPRESSED, STREAM_TOP and LAYOUT tables are the project's - they say
where main.asm's loader stages each stream and what order !BOOT reads the
files in - and stay in the project's make_disc.py. examples/make_disc_example.py
shows the shape with two files.

WHICH COMPRESSOR. Default ZX02 (py/zx02.py, lib/zx02depack.6502): half the
depacker and twice the speed of ZX0 for +0.11% on the packed size, measured
2026-09-07 over both ports' data - zx02.py's header has the numbers. ZX0 is
still here because the two shipping discs are ZX0 discs: pass codec=zx0 to
compress() and in_place_delta() for one of those, and pair it with
lib/zx0depack.6502. The formats are NOT interchangeable and nothing checks
that the disc and the depacker agree except you.

THE RAW IMAGE IS NOT BOOTABLE once the loader expects compressed streams:
always hand the image this writer produces to an emulator.
"""

import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from . import zx0, zx02

SECTOR = 256
MAX_FILES = 31                  # a DFS catalogue holds 31 entries
TOTAL_SECTORS = 800             # 80 tracks x 10 sectors, a full DFS disc
DISC_200K = 200 * 1024          # a whole 80-track disc; see pad()
FIRST_SECTOR = 2                # sectors 0 and 1 are the catalogue


class DiscError(ValueError):
    """Anything that would make an image the loader and the disc disagree on."""


@dataclass
class Entry:
    """One catalogue entry. load/exec are 18-bit (bits 16-17 from the
    'extra' byte, which is how DFS says 'host memory' with &FFFF above)."""
    name: str
    data: bytes
    load: int = 0
    exec: int = 0
    dir: str = "$"
    locked: bool = False

    def replace(self, data, load=None, exec=None):
        """Swap the contents (a compressed stream for the raw file, in the
        ports) and move the load/exec addresses with it."""
        self.data = bytes(data)
        if load is not None:
            self.load = load
        if exec is not None:
            self.exec = exec

    @property
    def sectors(self):
        return (len(self.data) + SECTOR - 1) // SECTOR


@dataclass
class Image:
    title: bytes = b""
    cycle: int = 0
    opt: int = 0                # *OPT 4 value: 3 = *EXEC !BOOT
    files: dict = field(default_factory=dict)   # name -> Entry, catalogue order


def read_image(path_or_bytes):
    """A .ssd as an Image: header and every file, in PHYSICAL order (ascending
    start sector - DFS keeps the catalogue in the reverse of it)."""
    img = Path(path_or_bytes).read_bytes() if isinstance(path_or_bytes, (str, Path)) \
        else bytes(path_or_bytes)
    found = []
    for i in range(img[0x105] // 8):
        e = 8 * (i + 1)
        name = img[e:e + 7].decode("ascii").rstrip()
        dirc = chr(img[e + 7] & 0x7F)
        locked = bool(img[e + 7] & 0x80)
        a = 0x100 + e
        load = img[a] | (img[a + 1] << 8)
        exe = img[a + 2] | (img[a + 3] << 8)
        extra = img[a + 6]
        length = (img[a + 4] | (img[a + 5] << 8)) | (((extra >> 4) & 3) << 16)
        load |= (((extra >> 2) & 3) << 16)
        exe |= (((extra >> 6) & 3) << 16)
        start = (img[a + 7] | ((extra & 3) << 8)) * SECTOR
        found.append((start, Entry(name, bytes(img[start:start + length]), load, exe,
                                   dirc, locked)))
    files = {e.name: e for _, e in sorted(found, key=lambda t: t[0])}
    return Image(title=(img[0:8] + img[0x100:0x104]).rstrip(b"\0"),
                 cycle=img[0x104], opt=(img[0x106] >> 4) & 3, files=files)


def read_catalogue(img):
    """The ports' original shape: name -> {'dir', 'load', 'exec', 'data'}."""
    return {n: {"dir": f.dir, "load": f.load, "exec": f.exec, "data": f.data}
            for n, f in read_image(img).files.items()}


def order_files(files, layout):
    """`layout` first, in that order, then anything it did not name, in
    catalogue order. A name in `layout` that is not on the disc is skipped -
    the caller decides whether that is an error (both ports say it is, for
    any file the loader reads)."""
    order = [n for n in layout if n in files]
    order += [n for n in files if n not in order]
    return order


def build_image(files, layout=(), title=b"", cycle=0, opt=3,
                total_sectors=TOTAL_SECTORS):
    """A complete .ssd, the files laid out contiguously from sector 2 in
    `layout` order (boot ACCESS order, so the head never seeks backwards
    during a load - the assembler's own order is source order and put
    !BOOT at the far end of the disc). Every file is padded to a sector.

    `files` is name -> Entry, or the read_catalogue() dict shape."""
    files = {n: (f if isinstance(f, Entry) else
                 Entry(n, f["data"], f["load"], f["exec"], f.get("dir", "$")))
             for n, f in files.items()}
    order = order_files(files, layout)
    if len(order) > MAX_FILES:
        raise DiscError(f"{len(order)} files - a DFS catalogue holds {MAX_FILES}")
    for n in order:
        if len(n) > 7 or not n.isascii():
            raise DiscError(f"{n!r}: a DFS filename is at most 7 ASCII characters")

    sector = FIRST_SECTOR
    placed = []                                     # (name, start_sector)
    data = bytearray()
    for name in order:
        f = files[name]
        placed.append((name, sector))
        data += f.data
        data += bytes(-len(f.data) % SECTOR)
        sector += f.sectors
    if sector > total_sectors:
        raise DiscError(f"{sector} sectors of {total_sectors} - the disc is full")

    title = bytes(title)[:12]
    img = bytearray(2 * SECTOR + len(data))
    img[0:8] = title[:8].ljust(8, b"\0")
    img[0x100:0x104] = title[8:12].ljust(4, b"\0")
    img[0x104] = cycle & 0xFF
    img[0x105] = len(placed) * 8
    img[0x106] = (opt & 3) << 4 | (total_sectors >> 8)
    img[0x107] = total_sectors & 0xFF

    # catalogue entries in descending start-sector order, as DFS keeps them
    for i, (name, start) in enumerate(reversed(placed)):
        f = files[name]
        e = 8 * (i + 1)
        img[e:e + 7] = name.encode("ascii").ljust(7)
        img[e + 7] = ord(f.dir) | (0x80 if f.locked else 0)
        a = 0x100 + e
        length = len(f.data)
        img[a + 0] = f.load & 0xFF
        img[a + 1] = (f.load >> 8) & 0xFF
        img[a + 2] = f.exec & 0xFF
        img[a + 3] = (f.exec >> 8) & 0xFF
        img[a + 4] = length & 0xFF
        img[a + 5] = (length >> 8) & 0xFF
        img[a + 6] = (((f.exec >> 16) & 3) << 6 | ((length >> 16) & 3) << 4
                      | ((f.load >> 16) & 3) << 2 | (start >> 8) & 3)
        img[a + 7] = start & 0xFF

    img[2 * SECTOR:] = data
    return bytes(img)


HOST = 0x30000                  # bits 16-17 of an 18-bit DFS address


def to_host(files):
    """Mark every file's load and exec address as the HOST's (&FFFFxxxx;
    DFS keeps two of the high bits). The assemblers write 16-bit addresses,
    and with a second processor attached 0 in those bits means the
    PARASITE: Paradroid's detector loaded and ran over the Tube, probed the
    parasite's RAM and refused to start ("FOUND 1"). Without a Tube the
    bits are ignored. Measured, Paradroid on jsbeeb 2026-09-10: B + 65C02
    and Master + 65C102 went from refused to playing. `files` is
    name -> Entry, changed in place."""
    for f in files.values():
        f.load |= HOST
        f.exec |= HOST


def pad(img, size=DISC_200K):
    """The image zero-filled to a whole disc.

    NOT needed to boot: jsbeeb stopped complaining in 1.9.0 and jsbeeb-mcp
    3.0.0 is the first release whose dependency guarantees that fix, and DFS
    itself never cared - the kit's own 2,304-byte image boots on both models
    (docs/hardware-facts.md, measured 2026-09-07). This is for PUBLISHING: a
    released size that differs from the last release says the wrong file went
    out. Build scripts do not need to call it."""
    if len(img) > size:
        raise DiscError(f"image is {len(img)} bytes, more than {size}")
    return bytes(img).ljust(size, b"\0")


# --- compressed streams -------------------------------------------------

def find_exe(candidates):
    """The first existing path in `candidates`, or None. The ports look in
    the project's bin/ and then a shared BEEB/Bin/."""
    for c in candidates:
        c = Path(c)
        if c.exists():
            return c
    return None


find_zx0_exe = find_exe          # the name the two shipping ports call it by


def compress(raw, exe=None, name="stream", codec=zx02):
    """`raw` as a default-mode stream of `codec` (zx02, or zx0 for one of the
    shipping discs). With `exe`, that compressor is run and its output
    verified by codec.decompress(); without, codec.compress() does it in
    Python (much slower on 16K, and never worse - see below).

    The released zx02.exe (v2) writes a trailing 0 on some inputs where
    zx02.py stops one byte earlier (1 file in 29 measured, 2026-09-11). Both
    decode identically and the round-trip below is the correctness check -
    but a BUILD must use one of them, always: choosing whichever is installed
    makes the disc depend on the machine. The template builds the reference
    from vendored source and passes it as `exe` (docs/build-portability.md
    rule 14)."""
    raw = bytes(raw)
    if exe is None:
        packed = codec.compress(raw)
    else:
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "in.bin"
            dst = Path(td) / "out.packed"
            src.write_bytes(raw)
            subprocess.run([str(exe), "-f", str(src), str(dst)],
                           check=True, capture_output=True)
            packed = dst.read_bytes()
    if codec.decompress(packed) != raw:
        raise DiscError(f"{name}: stream fails the {codec.__name__} round-trip")
    return packed


def in_place_delta(packed, raw=None, codec=zx02):
    """max(write_index - input bytes consumed) over the whole decode, plus 1.

    Both formats unpack forwards, so a stream that shares memory with its own
    output is safe only while the writer stays behind the reader. The margin
    is a property of THIS stream, not of the compression ratio: a literal run
    copies 1:1 plus its flag bits, so the gap can grow locally however good
    the average is. Walk the decode and measure it. The stream's landing
    address must be >= dest + in_place_delta.

    (ZX02's own compressor prints a "delta" too, but counted from the END of
    the output buffer. This is the kit's convention - from the start - and is
    what check_stream compares against.)

    With `raw` given, the decode is checked against it as well.
    """
    walk = _DELTA_WALKS[codec.__name__.rsplit(".", 1)[-1]]
    out, worst = walk(packed)
    if raw is not None and bytes(out) != bytes(raw):
        raise DiscError("in_place_delta: decode disagrees with the source")
    return worst + 1


def _reader(packed):
    """The bit reader both walks share: MSB first, with the backtrack slot
    that holds the offset-LSB byte whose bit 0 is the next control bit."""
    state = {"pos": 0, "mask": 0, "byte": 0, "backtrack": None}

    def bit():
        if state["backtrack"] is not None:
            b = state["backtrack"] & 1
            state["backtrack"] = None
            return b
        if not state["mask"]:
            state["byte"] = packed[state["pos"]]
            state["pos"] += 1
            state["mask"] = 128
        b = 1 if (state["byte"] & state["mask"]) else 0
        state["mask"] >>= 1
        return b

    return state, bit


def _delta_zx0(packed):
    """The ZX0 decode, instrumented. Measured against the Paradroid font
    stream, which unpacks over itself at &3000 from &3700."""
    out = bytearray()
    st, bit = _reader(packed)
    worst = -1 << 30

    def note():
        nonlocal worst
        g = (len(out) - 1) - st["pos"]
        if g > worst:
            worst = g

    def gamma(invert):
        v = 1
        while not bit():
            d = bit()
            if invert:
                d ^= 1
            v = (v << 1) | d
        return v

    last_offset = zx0.INITIAL_OFFSET
    state = "literals"
    while True:
        if state == "literals":
            for _ in range(gamma(False)):
                out.append(packed[st["pos"]]); st["pos"] += 1; note()
            state = "new" if bit() else "copy"
        elif state == "copy":
            for _ in range(gamma(False)):
                out.append(out[-last_offset]); note()
            state = "new" if bit() else "literals"
        else:
            msb = gamma(True)
            if msb == 256:
                return out, worst
            lsb = packed[st["pos"]]; st["pos"] += 1
            last_offset = msb * 128 - (lsb >> 1)
            st["backtrack"] = lsb
            for _ in range(gamma(False) + 1):
                out.append(out[-last_offset]); note()
            state = "new" if bit() else "literals"


def _delta_zx02(packed):
    """The ZX02 decode, instrumented. Same shape as _delta_zx0 with the
    format's three differences: gamma ends on a 0, offsets are positive, and
    the gamma value is 8-bit (0 meaning 256, and END in the offset MSB)."""
    out = bytearray()
    st, bit = _reader(packed)
    worst = -1 << 30

    def note():
        nonlocal worst
        g = (len(out) - 1) - st["pos"]
        if g > worst:
            worst = g

    def gamma():
        v = 1
        while bit():
            v = ((v << 1) | bit()) & 0xFF
        return v

    def count(v):
        return v if v else 256

    last_offset = zx02.INITIAL_OFFSET
    state = "literals"
    while True:
        if state == "literals":
            for _ in range(count(gamma())):
                out.append(packed[st["pos"]]); st["pos"] += 1; note()
            state = "new" if bit() else "copy"
        elif state == "copy":
            for _ in range(count(gamma())):
                out.append(out[-last_offset]); note()
            state = "new" if bit() else "literals"
        else:
            msb = gamma()
            if msb == 0:
                return out, worst
            lsb = packed[st["pos"]]; st["pos"] += 1
            last_offset = (msb - 1) * 128 + (lsb >> 1) + 1
            st["backtrack"] = lsb
            for _ in range(count((gamma() + 1) & 0xFF)):
                out.append(out[-last_offset]); note()
            state = "new" if bit() else "literals"


_DELTA_WALKS = {"zx0": _delta_zx0, "zx02": _delta_zx02}


def check_stream(name, stream, packed, dest, raw, top=None, in_place=False,
                 codec=zx02):
    """Refuse a stream placement the depacker would wreck.

    `stream` is where the loader *LOADs the packed bytes, `dest` where it
    unpacks them, `top` the address the stream may not reach (the screen it
    stages under, or &8000). Returns the headroom to `top` (or None).

    in_place=False (Edge): the stream and its output may not overlap at all.
    in_place=True (Paradroid's font): they may, provided the stream lands at
    or above dest + in_place_delta(); the returned dict says by how much.
    """
    n, m = len(packed), len(raw)
    if top is not None and stream + n > top:
        raise DiscError(
            f"{name}: {n} bytes at {stream:#06x} runs past {top:#06x}. Split "
            f"the file, or move its staging address in main.asm AND here.")
    overlaps = not (stream + n <= dest or dest + m <= stream)
    if overlaps and not in_place:
        raise DiscError(
            f"{name}: the stream at {stream:#06x} overlaps its own output at "
            f"{dest:#06x} - it unpacks forwards and would eat itself.")
    margin = None
    if in_place:
        need = dest + in_place_delta(packed, raw, codec)
        if stream < need:
            raise DiscError(
                f"{name}: stream at {stream:#06x} would be overtaken by its "
                f"own output at {dest:#06x} - needs {need:#06x} or higher.")
        margin = stream - need
    return {"headroom": None if top is None else top - stream - n,
            "in_place_margin": margin}


# --- comparing two images -------------------------------------------------

def compare(a, b, ignore=()):
    """How two images differ, file by file: a list of lines, empty when they
    hold the same files. A file on one side only, different contents, a
    different load or exec address, a different title or boot option are
    all reported; files named in `ignore` are skipped (a !BOOT stamped with
    the wall clock, when the two builds did not share a stamp).

    Per file, because two images holding the same files can still differ as
    bytes - another layout order, another sector count - and the files are
    what the machine loads."""
    ia, ib = read_image(a), read_image(b)
    out = []
    if ia.title != ib.title:
        out.append(f"title: {ia.title!r} vs {ib.title!r}")
    if ia.opt != ib.opt:
        out.append(f"boot option: {ia.opt} vs {ib.opt}")
    for name in list(ia.files) + [n for n in ib.files if n not in ia.files]:
        if name in ignore:
            continue
        fa, fb = ia.files.get(name), ib.files.get(name)
        if fa is None or fb is None:
            out.append(f"{name}: only in the {'second' if fa is None else 'first'} image")
            continue
        if fa.data != fb.data:
            at = next((i for i, (x, y) in enumerate(zip(fa.data, fb.data)) if x != y),
                      min(len(fa.data), len(fb.data)))
            out.append(f"{name}: contents differ ({len(fa.data)} vs "
                       f"{len(fb.data)} bytes, first at +{at:#x})")
        if (fa.load, fa.exec) != (fb.load, fb.exec):
            out.append(f"{name}: load/exec {fa.load:#x}/{fa.exec:#x} vs "
                       f"{fb.load:#x}/{fb.exec:#x}")
    return out


def _main(argv):
    """python -m beeb_port_kit.dfs compare A.ssd B.ssd [--ignore NAME]...

    Prints each image's SHA256, then either "identical images" or every
    per-file difference. Exit status 0 when every file not ignored matches."""
    import hashlib
    if len(argv) < 3 or argv[0] != "compare":
        raise SystemExit(_main.__doc__)
    a, b, rest = Path(argv[1]), Path(argv[2]), argv[3:]
    ignore = [rest[i + 1] for i in range(len(rest) - 1) if rest[i] == "--ignore"]
    for p in (a, b):
        print(f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p}")
    if a.read_bytes() == b.read_bytes():
        print("identical images")
        return 0
    diffs = compare(a, b, ignore)
    print("\n".join(diffs) if diffs else
          "the images differ as bytes, but every file"
          + (" not ignored" if ignore else "") + " matches")
    return 1 if diffs else 0


if __name__ == "__main__":
    import sys
    raise SystemExit(_main(sys.argv[1:]))
