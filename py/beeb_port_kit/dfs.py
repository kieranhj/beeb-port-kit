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

model_stub() builds a !BOOT that runs the game on a Master (or whatever
OSBYTE 0 answers you accept) and prints a message and returns to BASIC on
anything else - from the 1942 port's make_disc.py, byte-identical to what
it shipped (py/tests/test_model_stub.py), and booted on jsbeeb's B, B1770
and Master by lib/test/model_stub_test.mjs.

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


def file_key(name, dirc="$"):
    """The key a file has in Image.files: its name in $, "D.NAME" in any other
    directory. A disc may hold the same name in two directories (a release
    disc's O.GAME and R.GAME); keyed by name alone, one hid the other. From
    Stryker's Run's release disc, 2026-10-25."""
    return name if dirc == "$" else f"{dirc}.{name}"


def read_image(path_or_bytes):
    """A .ssd as an Image: header and every file, in PHYSICAL order (ascending
    start sector - DFS keeps the catalogue in the reverse of it). Keyed by
    file_key(): "NAME" in $, "D.NAME" in directory D."""
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
    files = {file_key(e.name, e.dir): e for _, e in sorted(found, key=lambda t: t[0])}
    return Image(title=(img[0:8] + img[0x100:0x104]).rstrip(b"\0"),
                 cycle=img[0x104], opt=(img[0x106] >> 4) & 3, files=files)


def read_catalogue(img):
    """The ports' original shape: name -> {'dir', 'load', 'exec', 'data'}."""
    return {n: {"name": f.name, "dir": f.dir, "load": f.load, "exec": f.exec,
                "data": f.data}
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

    `files` is key -> Entry (read_image's: the catalogue name and directory
    are the Entry's, the key only orders it), or the read_catalogue() dict
    shape."""
    files = {n: (f if isinstance(f, Entry) else
                 Entry(f.get("name", n), f["data"], f["load"], f["exec"], f.get("dir", "$")))
             for n, f in files.items()}
    order = order_files(files, layout)
    if len(order) > MAX_FILES:
        raise DiscError(f"{len(order)} files - a DFS catalogue holds {MAX_FILES}")
    seen = set()
    for n in order:
        f = files[n]
        if len(f.name) > 7 or not f.name.isascii():
            raise DiscError(f"{f.name!r}: a DFS filename is at most 7 ASCII characters")
        if len(f.dir) != 1 or not f.dir.isascii():
            raise DiscError(f"{n!r}: a DFS directory is one ASCII character")
        if (f.dir, f.name) in seen:
            raise DiscError(f"{file_key(f.name, f.dir)!r} is on the disc twice")
        seen.add((f.dir, f.name))

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
        img[e:e + 7] = f.name.encode("ascii").ljust(7)
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


def game_files(path_or_bytes, packed=(), codec=zx02):
    """Every file as the machine has it once the loader has run: read_image()'s
    files (key -> Entry), with each packed one decompressed by `codec` (zx02, or zx0 for the shipping discs).
    `packed` names the keys the loader unpacks, or is a callable
    (key, entry, files) -> bool, for a disc whose files are packed or not by
    build (Stryker's Run's: packed where its loader carries the sign "ZX02").
    Load addresses stay the catalogue's (where the STREAM loads). For tools and
    harnesses that read a game's bytes from its disc: read them through this,
    never raw, or a packed disc reads as noise. From Stryker's Run, 2026-10-25."""
    files = read_image(path_or_bytes).files
    test = packed if callable(packed) else (lambda k, e, fs, s=set(packed): k in s)
    for k, e in files.items():
        if test(k, e, files):
            e.data = bytes(codec.decompress(e.data))
    return files


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


def compress(raw, exe=None, name="stream", codec=zx02, env=None):
    """`raw` as a default-mode stream of `codec` (zx02, or zx0 for one of the
    shipping discs). With `exe`, that compressor is run and its output
    verified by codec.decompress(); without, codec.compress() does it in
    Python (much slower on 16K, and never worse - see below).

    The released zx02.exe (v2) writes EXTRA BYTES on some inputs where
    zx02.py stops earlier (1 file in 29 measured, 2026-09-11; 9 of 31 in a
    wider run 2026-09-23). That was recorded here as "a trailing 0", and it
    was not: compress.c sizes its output buffer from an ESTIMATE of the bit
    length and zx02.c then writes exactly that many bytes, so the slack is
    uninitialised malloc memory. Often 0, sometimes not - Edge's
    tiles.chr.bin gained an ASCII 'e' (0x65) - and it follows the
    environment the compressor ran in, which breaks reproducibility
    (docs/build-portability.md rule 16; puzzle-beeble BUGS.md #2).
    template/tools/zx02src/ carries the one-line fix, after which the exe
    agrees with zx02.py BYTE FOR BYTE on that file - zx02.py was right.

    A BUILD must use one compressor, always: choosing whichever is installed
    makes the disc depend on the machine. The template builds the reference
    from vendored source and passes it as `exe` (docs/build-portability.md
    rule 14), and re-runs it under a changed environment to prove the answer
    does not move."""
    raw = bytes(raw)
    if exe is None:
        packed = codec.compress(raw)
    else:
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "in.bin"
            dst = Path(td) / "out.packed"
            src.write_bytes(raw)
            subprocess.run([str(exe), "-f", str(src), str(dst)],
                           check=True, capture_output=True, env=env)
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


# --- the model check: a !BOOT that refuses the wrong machine politely -------
#
# From the 1942 port's tools/make_disc.py model_stub() (KC 2026-10-19: "the
# loader needs to abort if the model isn't Master"). A game that needs a
# Master cannot check for one INSIDE itself if it loads low: a Model B's DFS
# keeps its workspace at &0E00-&18FF, and a !BOOT built for &0E00 HUNG INSIDE
# ITS OWN LOAD there - MEASURED in jsbeeb on a B with DFS 1.2 and a B with the
# 1770 DFS - so the game never got control to say anything. So !BOOT becomes
# STUB + IMAGE in one file, loaded at `org` (default &5000, free on every
# model in MODE 7: a B's screen is at &7C00, PAGE &1900). The stub asks OSBYTE
# 0 (X = 1) for the OS; on an accepted answer - default 3 (MOS 3.x, Master 128)
# and 5 (MOS 5.x, Master Compact) - it copies the image down to `dest` and
# jumps to `entry`; on anything else it prints `text` through OSASCI and RTSes
# to BASIC with the filing system untouched. It costs no catalogue entry.
# lib/test/model_stub_test.mjs boots one on jsbeeb's B, B1770 and Master.
# OSBYTE 0's X: 0 OS 1.00 / Electron, 1 OS 1.2 (B), 2 OS 2.00 (B+), 3 Master
# 128, 4 Master ET, 5 Master Compact - the AUG; 1 and 3 measured in jsbeeb.

STUB_ORG = 0x5000
STUB_ZP = 0x70                  # src, dst: user zero page, before the game runs


def model_stub(image, dest, entry, text="This game needs a BBC Master",
               org=STUB_ORG, accept=(3, 5), zp=STUB_ZP, top=0x7C00,
               lowest=0x1900):
    """(file bytes, load, exec) for a !BOOT that runs `image` - which belongs
    at `dest` and starts at `entry` - only on a machine whose OSBYTE 0 answer
    is in `accept`, and prints `text` on any other. Load and exec are both
    `org`, 16-bit: pass the Entry through to_host() like any other file, and
    boot the disc with *OPT 4,2 (*RUN).

    Refuses (DiscError) a stub that would not work: below `lowest` (a B's DFS
    workspace ends at &18FF and PAGE is &1900), past `top` (MODE 7's screen),
    an image whose copy would overwrite the stub while it runs, `text` over
    254 bytes or containing a 0, or no accepted model at all. A newline in
    `text` is written as CR (OSASCI turns it into CR LF)."""
    image = bytes(image)
    if isinstance(text, str):
        text = text.replace("\r\n", "\r").replace("\n", "\r").encode("ascii")
    text = bytes(text)
    if not text.endswith(b"\r"):
        text += b"\r"
    if b"\0" in text or len(text) > 254:
        raise DiscError("model_stub: the text is printed by LDA text,X up to a 0: "
                        "at most 254 bytes, none of them 0")
    accept = tuple(accept)
    if not accept or not all(0 <= a <= 255 for a in accept):
        raise DiscError("model_stub: accept names the OSBYTE 0 answers to run on")
    if not 0 <= zp <= 0xFC:
        raise DiscError("model_stub: zp is four bytes of zero page")
    n = len(image)
    full, rem = n // 256, n % 256
    zs, zd = zp, zp + 2
    code, lab, fix = bytearray(), {}, []     # fix: (offset, label, kind)

    def op(*b):
        code.extend(b)

    def br(opc, to):                         # a relative branch to a label
        op(opc, 0)
        fix.append((len(code) - 1, to, "rel"))

    def here(name):
        lab[name] = len(code)
    op(0xA9, 0x00)                      # LDA #0
    op(0xA2, 0x01)                      # LDX #1
    op(0xA0, 0xFF)                      # LDY #&FF
    op(0x20, 0xF4, 0xFF)                # JSR OSBYTE    -> X: the OS
    for a in accept:
        op(0xE0, a)                     # CPX #a
        br(0xF0, "ok")                  # BEQ ok
    op(0xA2, 0x00)                      # LDX #0
    here("msg")
    op(0xBD, 0, 0)                      # LDA text,X
    fix.append((len(code) - 2, "text", "abs"))
    br(0xF0, "bye")                     # BEQ bye
    op(0x20, 0xE3, 0xFF)                # JSR OSASCI
    op(0xE8)                            # INX
    br(0xD0, "msg")                     # BNE msg
    here("bye")
    op(0x60)                            # RTS           back to BASIC, the DFS intact
    here("ok")
    op(0xA9, 0)                         # LDA #LO(image)
    fix.append((len(code) - 1, "image", "lo"))
    op(0x85, zs)                        # STA src
    op(0xA9, 0)                         # LDA #HI(image)
    fix.append((len(code) - 1, "image", "hi"))
    op(0x85, zs + 1)                    # STA src+1
    op(0xA9, dest & 0xFF)               # LDA #LO(dest)
    op(0x85, zd)                        # STA dst
    op(0xA9, (dest >> 8) & 0xFF)        # LDA #HI(dest)
    op(0x85, zd + 1)                    # STA dst+1
    op(0xA0, 0x00)                      # LDY #0
    op(0xA2, full & 0xFF)               # LDX #full pages
    br(0xF0, "rem")                     # BEQ rem
    here("page")
    op(0xB1, zs)                        # LDA (src),Y
    op(0x91, zd)                        # STA (dst),Y
    op(0xC8)                            # INY
    br(0xD0, "page")                    # BNE page
    op(0xE6, zs + 1)                    # INC src+1
    op(0xE6, zd + 1)                    # INC dst+1
    op(0xCA)                            # DEX
    br(0xD0, "page")                    # BNE page
    here("rem")                         # Y = 0 on every way in
    op(0xC0, rem)                       # CPY #rem
    br(0xF0, "go")                      # BEQ go
    op(0xB1, zs)                        # LDA (src),Y
    op(0x91, zd)                        # STA (dst),Y
    op(0xC8)                            # INY
    br(0xD0, "rem")                     # BNE rem       (always: rem < 256)
    here("go")
    op(0x4C, entry & 0xFF, (entry >> 8) & 0xFF)  # JMP entry
    here("text")
    code.extend(text + b"\0")
    lab["image"] = len(code)
    for at, to, kind in fix:
        a = org + lab[to]
        if kind == "rel":
            d = lab[to] - (at + 1)
            if not -128 <= d <= 127:
                raise DiscError(f"model_stub: branch to {to} out of range")
            code[at] = d & 0xFF
        elif kind == "abs":
            code[at], code[at + 1] = a & 0xFF, a >> 8
        elif kind == "lo":
            code[at] = a & 0xFF
        else:
            code[at] = a >> 8
    data = bytes(code) + image
    if full > 255:
        raise DiscError("model_stub: the image is over 64K")
    if org < lowest:
        raise DiscError(f"model_stub: org {org:#06x} is below {lowest:#06x} - a Model B's "
                        "DFS works in &0E00-&18FF and hangs loading a !BOOT there")
    if org + len(data) > top:
        raise DiscError(f"model_stub: the !BOOT reaches {org + len(data):#06x}, past "
                        f"{top:#06x} (MODE 7's screen)")
    if not (dest + n <= org or dest >= org + len(data)):
        # wholly below the stub, or wholly above the file: anything else
        # overwrites the stub's own loop or the bytes it has still to copy
        raise DiscError(f"model_stub: copying {n} bytes to {dest:#06x} would overwrite the "
                        "stub or the image while it runs")
    return data, org, org


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
    python -m beeb_port_kit.dfs host IMAGE.ssd
    python -m beeb_port_kit.dfs layout IMAGE.ssd NAME...
    python -m beeb_port_kit.dfs file IMAGE.ssd NAME [--unpack]

    compare: prints each image's SHA256, then either "identical images" or
    every per-file difference. Exit status 0 when every file not ignored
    matches.
    host: rewrites IMAGE in place with every catalogue load and exec
    address the HOST's (to_host), for a disc built without make_disc.py.
    layout: rewrites IMAGE in place with its files laid out in the NAMEs'
    order (build_image: boot access order, so a load never seeks back - an
    assembler writes source order, and Stryker's Run's head steps went from
    120 to 32), the rest after them; every NAME must be on the disc. The image
    keeps its length.
    file: NAME's bytes as hex on stdout, for a harness in another language to
    read a disc's file without its own DFS reader; --unpack decompresses it
    first (game_files). NAME is a key: "D.NAME" outside $."""
    import hashlib
    if len(argv) == 2 and argv[0] == "host":
        img = read_image(argv[1])
        to_host(img.files)
        Path(argv[1]).write_bytes(build_image(img.files, list(img.files),
                                              img.title, img.cycle, img.opt))
        print(f"{argv[1]}: {len(img.files)} files marked as the host's")
        return 0
    if len(argv) in (3, 4) and argv[0] == "file" and argv[3:] in ([], ["--unpack"]):
        files = game_files(argv[1], [argv[2]] if argv[3:] else ())
        if argv[2] not in files:
            raise SystemExit(f"{argv[1]}: no {argv[2]}")
        print(files[argv[2]].data.hex())
        return 0
    if len(argv) >= 3 and argv[0] == "layout":
        raw = Path(argv[1]).read_bytes()
        img = read_image(raw)
        missing = [n for n in argv[2:] if n not in img.files]
        if missing:
            raise SystemExit(f"{argv[1]}: no {', '.join(missing)}")
        out = build_image(img.files, argv[2:], img.title, img.cycle, img.opt)
        Path(argv[1]).write_bytes(out + bytes(max(0, len(raw) - len(out))))
        print(f"{argv[1]}: laid out {', '.join(argv[2:])} first")
        return 0
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
