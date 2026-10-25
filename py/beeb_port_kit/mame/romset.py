"""romset.py - an arcade ROM set read straight out of MAME's zip: checked, regioned,
banked, and its graphics and palette decoded the way MAME's driver says.

Fork this into your project's tools/; keep this header.

From 1942-beeb's `tools/arcade.py` (`Roms`: the ROM-list check, the three gfx_layout
decoders, the resistor-ladder palette and the three colour lookup PROMs) and
`tools/export_waves.py`'s `Rom` (the main CPU's address space with a banked
$8000-$BFFF window). What was measured with them there:

  * The decoders were transcribed from the driver's gfx_layout structs and checked by
    rendering - which confirmed the bit layouts and completely missed that every cell
    is stored rotated (1942-beeb BUGS.md #1; see orient.py). Then by diffing a
    rebuild of captured tilemap RAM against a same-frame MAME screenshot: 97.74%
    pixel-identical, the residue the HUD and sprites the rebuild did not draw.
  * gfx_layout PLANES ARE LISTED MOST SIGNIFICANT FIRST. Getting that backwards
    bit-reverses every pen, which permutes a tile's colours without changing its
    shape - and the sea tiles' pens were fixed points of the reversal, so sea
    frames passed a broken decoder (BUGS.md #2). Verify on the busiest frame, not
    the first one.
  * The bank-select register was FOUND BY CAUSE (template/tools/mame/find_reg.lua),
    not recalled: $C806, and one bank was an 8K ROM in a 16K window that reads $FF
    above it - which is why Banked has a fill byte (arcade-facts s7).
  * A sprite code in an object record was 8 of its 10 bits; the other two came from
    the attribute byte (BUGS.md #16). Nothing here can know that: transcribe the
    driver's SPRITE DRAWER as carefully as its gfx_layout.

No ROM data is copied anywhere: everything is read from the zip on the machine.

    machine = parse_listxml(open("1942.xml").read(), "1942")     # mame -listxml 1942
    rs = RomSet(["roms/1942.zip"], machine.roms)                 # checks names, sizes, CRCs
    cpu = rs.region("maincpu")                                   # bytes, by -listxml offsets
    tiles = GfxLayout(16, 16, planes=[rgn_frac(0, 3, n), ...], xoffs=..., yoffs=..., inc=256)
"""

import re
import subprocess
import xml.etree.ElementTree as ET
import zipfile
import zlib


class RomError(Exception):
    pass


# --- what MAME says the machine is ---------------------------------------------------

class RomInfo:
    def __init__(self, name, size, crc=None, region=None, offset=0, merge=None):
        self.name, self.size, self.crc = name, size, crc
        self.region, self.offset, self.merge = region, offset, merge

    def __repr__(self):
        return "RomInfo(%r, %d, crc=%s, region=%r, offset=0x%X)" % (
            self.name, self.size, self.crc, self.region, self.offset)


class Machine:
    """What `mame -listxml <game>` says: ROMs, CPUs and sound chips with their clocks,
    the display (WITH ITS ROTATION - a lead for orient.py, which still has to be
    measured), and the DIP switches with their settings and defaults."""

    def __init__(self, name):
        self.name = name
        self.cloneof = self.romof = None
        self.roms, self.chips, self.displays, self.dipswitches = [], [], [], []

    def cpu(self, tag):
        return next(c for c in self.chips if c["tag"] == tag)


def parse_listxml(text, game):
    """Parse -listxml output (all machines, or just one) and return `game`'s Machine.
    Accepts <machine> (MAME 0.162+) and <game> (older)."""
    root = ET.fromstring(text)
    node = None
    for el in root.iter():
        if el.tag in ("machine", "game") and el.get("name") == game:
            node = el
            break
    if node is None:
        raise RomError("%s is not in this -listxml output" % game)
    m = Machine(game)
    m.cloneof, m.romof = node.get("cloneof"), node.get("romof")
    for r in node.findall("rom"):
        if r.get("status") == "nodump":
            continue
        m.roms.append(RomInfo(r.get("name"), int(r.get("size")), r.get("crc"),
                              r.get("region"), int(r.get("offset", "0"), 16),
                              r.get("merge")))
    for c in node.findall("chip"):
        m.chips.append({"type": c.get("type"), "tag": c.get("tag"), "name": c.get("name"),
                        "clock": int(c.get("clock")) if c.get("clock") else None})
    for d in node.findall("display"):
        m.displays.append({k: d.get(k) for k in ("tag", "type", "rotate", "width",
                                                 "height", "refresh")})
    for d in node.findall("dipswitch"):
        vals, default = {}, None
        for v in d.findall("dipvalue"):
            vals[int(v.get("value"))] = v.get("name")
            if v.get("default") == "yes":
                default = int(v.get("value"))
        m.dipswitches.append({"name": d.get("name"), "tag": d.get("tag"),
                              "mask": int(d.get("mask")), "values": vals,
                              "default": default})
    return m


def listxml(exe, game, cwd=None, timeout=120):
    """Run `exe -listxml game` and return the text. Read the manifest; do not recall
    it (1942's decision 1 reasoned about a "3 MHz Z80" that was the AUDIO cpu)."""
    r = subprocess.run([exe, "-listxml", game], cwd=cwd, capture_output=True,
                       text=True, errors="replace", timeout=timeout)
    if r.returncode != 0:
        raise RomError("-listxml %s exited %d: %s" % (game, r.returncode, r.stderr[-400:]))
    return r.stdout


# --- the ROM set ---------------------------------------------------------------------

class RomSet:
    """ROM files read out of one or more MAME zips (a clone's own, then its parent's)
    and checked against a ROM list: every name present, every size right, and the
    CRC too when the list has one. A wrong dump decodes into plausible garbage."""

    def __init__(self, zips, roms):
        self.roms = list(roms)
        self.files = {}
        found = {}
        for path in zips:
            with zipfile.ZipFile(path) as z:
                for info in z.infolist():
                    found.setdefault(info.filename.lower(), (path, info))
        problems = []
        for r in self.roms:
            hit = found.get(r.name.lower())
            if hit is None:
                problems.append("%s missing" % r.name)
                continue
            path, info = hit
            with zipfile.ZipFile(path) as z:
                data = z.read(info.filename)
            if len(data) != r.size:
                problems.append("%s is %d bytes, not %d" % (r.name, len(data), r.size))
            if r.crc and "%08x" % (zlib.crc32(data) & 0xFFFFFFFF) != r.crc.lower():
                problems.append("%s CRC %08x, want %s" % (r.name, zlib.crc32(data) & 0xFFFFFFFF,
                                                          r.crc))
            self.files[r.name] = data
        if problems:
            raise RomError("ROM set does not match its list: " + "; ".join(problems))

    def __getitem__(self, name):
        return self.files[name]

    def region(self, region, fill=0x00, size=None):
        """A region assembled from its ROMs' -listxml offsets. Gaps are `fill`."""
        parts = [r for r in self.roms if r.region == region]
        if not parts:
            raise RomError("no ROMs in region %r" % region)
        top = max(r.offset + r.size for r in parts)
        out = bytearray([fill]) * (size or top)
        for r in parts:
            out[r.offset:r.offset + r.size] = self.files[r.name]
        return bytes(out)


class Banked:
    """A CPU address space with fixed ROM and ONE banked window.

    fixed: {start_address: bytes}; banks: [bytes], each paged at `window[0]`. A bank
    shorter than the window reads `fill` above its end (1942's 8K srb-06.m6 in a 16K
    window reads $FF - measured, arcade-facts s7). Reads outside everything raise:
    RAM and I/O are not in a ROM image, and returning 0 for them is how a model
    quietly reads a value nobody wrote."""

    def __init__(self, fixed, banks=(), window=(0x8000, 0xC000), fill=0xFF):
        self.fixed = sorted(fixed.items())
        self.banks, self.window, self.fill = list(banks), window, fill

    def read(self, addr, bank=0):
        addr &= 0xFFFF
        lo, hi = self.window
        if self.banks and lo <= addr < hi:
            b = self.banks[bank]
            i = addr - lo
            return b[i] if i < len(b) else self.fill
        for start, data in self.fixed:
            if start <= addr < start + len(data):
                return data[addr - start]
        raise RomError("$%04X is not ROM in this map" % addr)

    def block(self, addr, n, bank=0):
        return bytes(self.read(addr + i, bank) for i in range(n))

    def fetcher(self, bank=0):
        """A read(addr) closure for one bank - what z80sub.disassemble wants."""
        return lambda a: self.read(a, bank)


# --- graphics --------------------------------------------------------------------------

def rgn_frac(num, den, region_bytes):
    """MAME's RGN_FRAC(num, den) for a region of this many BYTES, in BITS - the unit
    every gfx_layout offset is in."""
    return region_bytes * 8 * num // den


class GfxLayout:
    """MAME's gfx_layout, transcribed: width, height, plane offsets MOST SIGNIFICANT
    FIRST, x and y bit offsets, and the bit increment between cells. Bits are
    MSB-first within each byte, as MAME reads them.

    decode(data, n) returns rows of pen values in RAW orientation - the space the
    hardware scans. If the cabinet is rotated, rotate with orient.py; nothing about a
    gfx_layout says which way up a cell is meant to look."""

    def __init__(self, width, height, planes, xoffs, yoffs, inc):
        if len(xoffs) != width or len(yoffs) != height:
            raise ValueError("xoffs/yoffs must have width/height entries")
        self.width, self.height = width, height
        self.planes, self.xoffs, self.yoffs, self.inc = list(planes), xoffs, yoffs, inc

    @property
    def bpp(self):
        return len(self.planes)

    def count(self, data):
        """Cells in a region of this many bytes - for a layout whose planes are
        RGN_FRACs of it, the cells in one plane's share."""
        span = max(self.planes) + max(self.xoffs) + max(self.yoffs)
        return (len(data) * 8 - span - 1) // self.inc + 1

    def decode(self, data, n):
        base = n * self.inc
        np_ = len(self.planes)
        rows = []
        for y in range(self.height):
            yo = base + self.yoffs[y]
            row = []
            for x in range(self.width):
                o = yo + self.xoffs[x]
                pen = 0
                for p, po in enumerate(self.planes):
                    b = o + po
                    pen |= ((data[b >> 3] >> (7 - (b & 7))) & 1) << (np_ - 1 - p)
                row.append(pen)
            rows.append(row)
        return rows


# --- palette ---------------------------------------------------------------------------

def weighted(v, weights):
    """One gun of a resistor-ladder DAC: sum of weights[i] for each set bit i of v.
    1942's (MAME's create_palette) are (0x0E, 0x1F, 0x43, 0x8F) for bits 0-3; take
    your driver's own - they are in its palette init, not in any manual."""
    return min(255, sum(w for i, w in enumerate(weights) if (v >> i) & 1))


def prom_palette(r, g, b, weights, n=None):
    """[(r, g, b)] from three colour PROMs, one 4-bit entry per byte (the low nibble
    of each, as MAME reads a 4-bit PROM stored in bytes)."""
    n = n or min(len(r), len(g), len(b))
    return [(weighted(r[i] & 15, weights), weighted(g[i] & 15, weights),
             weighted(b[i] & 15, weights)) for i in range(n)]


def lookup(prom, colour_set, pen, pens, base=0, set_mask=None, entry_mask=0x0F):
    """Palette index through a colour lookup PROM: base | prom[set * pens + pen].

    `pens` is the pens per colour set (4 for 2bpp, 8 for 3bpp, 16 for 4bpp); `base`
    is the layer's palette block, ORed in after the lookup (1942: chars 0x80, sprites
    0x40, tiles (bank << 4)). Read all three from the driver's palette init."""
    if set_mask is not None:
        colour_set &= set_mask
    return base | (prom[colour_set * pens + pen] & entry_mask)


_CRC = re.compile(r"^[0-9a-f]{8}$")


def rom_list(pairs):
    """[RomInfo] from (name, size[, crc]) tuples, for a project that writes its
    list from the driver's ROM_START by hand rather than from -listxml."""
    out = []
    for p in pairs:
        crc = p[2] if len(p) > 2 else None
        if crc is not None and not _CRC.match(crc.lower()):
            raise ValueError("%s: CRC %r is not 8 hex digits" % (p[0], crc))
        out.append(RomInfo(p[0], p[1], crc))
    return out
