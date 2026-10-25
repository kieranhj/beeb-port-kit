"""records.py - per-frame binary records, described by ONE spec that the Lua writer and
the Python reader both parse.

Fork this into your project's tools/; keep this header.

From 1942-beeb's `tools/fullgame.py` (`frames()`, the reader of `tools/mame/fullgame.lua`'s
242,100-frame whole-game capture) and `tools/enemy_cap.py` (the reader of `enemy.lua`'s
436-byte records, "kept in one place because three probes read it and a field list
copied twice is a field list that will be wrong once"). In 1942 the layout lived twice -
a G list in the Lua and a G list in the Python - and the two had to be kept in step by
hand. Here the layout is a string, the Lua harness writes it beside the data as
schema.txt, and the reader takes it from there, so a capture cannot be read with a
layout other than the one it was written with.

THE SPEC, items separated by ';', every number HEX (addresses are hex everywhere in
this kit; a decimal address measures the wrong location and answers anyway):

    name:frame                      u32 little-endian frame number (1 = first frame)
    name:bytes@A,B,C-D,...          one byte per address; C-D is inclusive
    name:slots@BASE,N,STRIDE,LEN[,OFF[,MASK]]
                                    an object table: u8 count, then for each of the N
                                    slots whose byte BASE+i*STRIDE+OFF AND MASK is
                                    non-zero (OFF 0, MASK FF by default): u8 slot index
                                    and LEN bytes from BASE+i*STRIDE. Live slots only,
                                    which is what keeps a whole-game capture small

1942's whole-game record, as a spec (the G list shortened):

    f:frame;g:bytes@e103,e102,e101,e099,e0a5,e0d2,e0d3;spr:bytes@cc00-cc7f;obj:slots@e400,10,30,30

    sch = Schema.parse(spec)            or   sch, path = load_capture(dir, "ram.bin")
    for rec in sch.read(path):
        rec["f"], rec["g"].at(0xe103), rec["spr"], rec["obj"]   # {slot: 48 bytes}

`Schema.pack(frame, read)` is the Python model of the Lua writer (`read(addr)` -> byte),
used by the tests and by anything that synthesises a capture.
"""

import os
import struct


class SpecError(ValueError):
    pass


def _hex(s):
    s = s.strip().lower()
    for p in ("0x", "$", "&"):
        if s.startswith(p):
            s = s[len(p):]
    if not s:
        raise SpecError("empty number")
    try:
        return int(s, 16)
    except ValueError:
        raise SpecError("not a hex number: %r (every number in a spec is hex)" % s)


class Field:
    def __init__(self, name, kind, addrs=None, base=0, n=0, stride=0, length=0,
                 off=0, mask=0xFF):
        self.name, self.kind = name, kind
        self.addrs = addrs or []
        self.base, self.n, self.stride, self.length = base, n, stride, length
        self.off, self.mask = off, mask

    @property
    def size(self):
        """Bytes in a record, or None if it varies (slots)."""
        if self.kind == "frame":
            return 4
        if self.kind == "bytes":
            return len(self.addrs)
        return None


class Bytes(bytes):
    """A bytes field that knows the address each byte came from."""

    def __new__(cls, data, addrs):
        b = super().__new__(cls, data)
        b._index = {a: i for i, a in enumerate(addrs)}
        return b

    def at(self, addr):
        return self[self._index[addr]]

    def word(self, lo):
        """Little-endian 16-bit value from addr lo and lo+1."""
        return self.at(lo) | (self.at(lo + 1) << 8)


class Schema:
    def __init__(self, fields, spec):
        self.fields, self.spec = fields, spec
        names = [f.name for f in fields]
        if len(set(names)) != len(names):
            raise SpecError("duplicate field name in %r" % spec)

    @classmethod
    def parse(cls, spec):
        fields = []
        for item in [s.strip() for s in spec.split(";") if s.strip()]:
            head, _, args = item.partition("@")
            name, _, kind = head.partition(":")
            name, kind = name.strip(), kind.strip()
            if not name or not kind:
                raise SpecError("item %r is not name:kind[@args]" % item)
            if kind == "frame":
                fields.append(Field(name, kind))
            elif kind == "bytes":
                addrs = []
                for part in [p for p in args.split(",") if p.strip()]:
                    if "-" in part:
                        lo, hi = (_hex(x) for x in part.split("-", 1))
                        if hi < lo:
                            raise SpecError("range %r runs backwards" % part)
                        addrs.extend(range(lo, hi + 1))
                    else:
                        addrs.append(_hex(part))
                if not addrs:
                    raise SpecError("bytes field %r has no addresses" % name)
                fields.append(Field(name, kind, addrs=addrs))
            elif kind == "slots":
                v = [_hex(x) for x in args.split(",") if x.strip()]
                if len(v) < 4 or len(v) > 6:
                    raise SpecError("slots wants BASE,N,STRIDE,LEN[,OFF[,MASK]]: %r" % item)
                base, n, stride, length = v[:4]
                off = v[4] if len(v) > 4 else 0
                mask = v[5] if len(v) > 5 else 0xFF
                if n > 255 or length < 1 or off >= stride:
                    raise SpecError("slots %r: N <= FF, LEN >= 1, OFF < STRIDE" % item)
                fields.append(Field(name, kind, base=base, n=n, stride=stride,
                                    length=length, off=off, mask=mask))
            else:
                raise SpecError("unknown kind %r in %r (frame, bytes, slots)" % (kind, item))
        if not fields:
            raise SpecError("empty spec")
        return cls(fields, spec)

    @property
    def fixed_size(self):
        """Bytes per record, or None if any field is variable (slots)."""
        sizes = [f.size for f in self.fields]
        return None if None in sizes else sum(sizes)

    # --- the writer model ----------------------------------------------------
    def pack(self, frame, read):
        out = bytearray()
        for f in self.fields:
            if f.kind == "frame":
                out += struct.pack("<I", frame & 0xFFFFFFFF)
            elif f.kind == "bytes":
                out += bytes(read(a) & 0xFF for a in f.addrs)
            else:
                live = []
                for i in range(f.n):
                    b = f.base + i * f.stride
                    if read(b + f.off) & f.mask:
                        live.append(bytes([i]) + bytes(read(b + k) & 0xFF
                                                       for k in range(f.length)))
                out.append(len(live))
                out += b"".join(live)
        return bytes(out)

    # --- the reader -----------------------------------------------------------
    def records(self, data):
        """Yield one dict per record. Raises on a truncated or misaligned file:
        a capture that does not end on a record boundary was cut short, and a
        reader that silently drops the tail has hidden that."""
        p, n = 0, len(data)
        fixed = self.fixed_size
        if fixed is not None and n % fixed:
            raise SpecError("%d bytes is not a whole number of %d-byte records"
                            % (n, fixed))
        while p < n:
            rec = {}
            for f in self.fields:
                if f.kind == "frame":
                    if p + 4 > n:
                        raise SpecError("truncated record at byte %d" % p)
                    rec[f.name] = struct.unpack_from("<I", data, p)[0]
                    p += 4
                elif f.kind == "bytes":
                    k = len(f.addrs)
                    if p + k > n:
                        raise SpecError("truncated record at byte %d" % p)
                    rec[f.name] = Bytes(data[p:p + k], f.addrs)
                    p += k
                else:
                    if p >= n:
                        raise SpecError("truncated record at byte %d" % p)
                    cnt = data[p]
                    p += 1
                    slots = {}
                    for _ in range(cnt):
                        if p + 1 + f.length > n:
                            raise SpecError("truncated slot at byte %d" % p)
                        s = data[p]
                        if s >= f.n:
                            raise SpecError("slot index %d >= %d at byte %d: the file "
                                            "was not written with this spec" % (s, f.n, p))
                        slots[s] = data[p + 1:p + 1 + f.length]
                        p += 1 + f.length
                    rec[f.name] = slots
            yield rec

    def read(self, path):
        with open(path, "rb") as fh:
            data = fh.read()
        return self.records(data)


def load_capture(directory, data_file, schema_file="schema.txt"):
    """(Schema, path) for a capture the template Lua wrote: the spec is the first
    non-comment line of schema.txt beside the data."""
    with open(os.path.join(directory, schema_file), encoding="utf-8") as f:
        lines = [l.strip() for l in f if l.strip() and not l.startswith("#")]
    if not lines:
        raise SpecError("%s holds no spec" % schema_file)
    return Schema.parse(lines[0]), os.path.join(directory, data_file)


def runs(values):
    """[(first, last, value)] for each run of equal values - the shape a state byte's
    history is read in (enemy_cap.runs)."""
    out, s = [], 0
    for i in range(1, len(values) + 1):
        if i == len(values) or values[i] != values[s]:
            out.append((s, i - 1, values[s]))
            s = i
    return out
