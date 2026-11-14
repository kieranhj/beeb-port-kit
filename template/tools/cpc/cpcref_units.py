"""The reference capture for the Square Roots port: the original's LOGICAL sequence.

Square Roots' main loop is not once a field (Isometrikum's was): it free-runs, drawing the
Pythagoras trees square by square, and counts fields only while it waits between trees (&16FF).
Six Gate Array interrupts a field do the rest; the fifth, &1CD9 (line ~210), is the "world work":
the scroll (&1748), the root line (&1F2C), the row copy (&18CD). What the screen shows therefore
depends on how far the main loop has got when each field's world work runs - on the CPC's speed.

This machine is tools/cpcrun.py's CPC at CPC timing (tools/cpctime.py, decision 16) with one
change (decision 15, PROVISIONAL): the world work's interrupt is never taken inside a span fill
(&1A97-&1B1E) or between a wait pass's decrement and a tree's latch of &1115 (&171F-&1732): it
waits for the next instruction outside them, at most ~13 lines. So every world work falls
between two main-loop UNITS - each arrival at &1A95 (a span of a square), &171E (a pass of the
wait loop: its decrement, after the VSync wait), &19C4 (a square's start), &1B48 (an edge's
start) or &1978 (a side's move) - and the port can be paced to the same unit. The last two cut a square's setup into
pieces: it commutes with the world work, and a port that had to finish it whole before the
world work the CPC did in the middle of it fell behind.

Writes OUTDIR/
  world.log    field units ticks pc hl de bc   (each world work: the units started before it -
               the port's schedule - the music calls started before it, and the main loop's
               PC and registers when it came: in the boot, how far its clears had got)
  passes.bin   one record at the first unit point after one or more world works: u32 field,
               u32 units (started before this point), u32 ticks, u32 world works so far, u32 len,
               zlib(64K XOR the previous record's 64K). The 64K is the Z80's view (config &C0).
               There the main loop is at &1A95 or &171E, so its own state is canonical; the
               square setup it may have been in when the world work came commutes with it.
               Read with load_passes()
  ticks.npy    uint8 [ticks, &2400-&2000]: &2000-&23FF after each music call (&204B, from &1C88)
  ay.log       tick reg value   (every AY write; tick = music calls started so far)
  trees.log    field units script_ptr latch   (each tree start, &172D: the table base &1115 it latches)
  crtc.log     field line T port value  (every OUT, as cpcrun's out.log)
  deferred.log field lines   (each world work held back, and by how many lines)
  boot.bin     the 64K at the first unit (the wait loop's first decrement): where the models start
  boot.txt     its field, the world works before it, the music calls before it
Usage: python tools/cpcref.py MEM.bin OUTDIR FIELDS     (NODEFER=1: no holding back)
"""
import os
import struct
import sys
import zlib

import numpy as np

sys.path.insert(0, os.path.dirname(__file__))
import cpcrun  # noqa: E402

WORLD = 0x1CD9                  # the world work's handler (the &0039 vector)
SPAN_LO, SPAN_HI = 0x1A97, 0x1B1E   # inside one span's fill
LATCH_LO, LATCH_HI = 0x171F, 0x1732   # a wait pass's decrement to the tree's latch of &1115
UNIT_SPAN, UNIT_WAIT = 0x1A95, 0x171E
UNIT_SQUARE, UNIT_EDGE = 0x19C4, 0x1B48   # a square's start, an edge's: the setup in pieces
UNIT_SIDE = 0x1978              # a side's move (16 a square: the corners and the children)
MUSIC_DONE = 0x1CAB             # after CALL &204B in &1C88
TREE = 0x172D


class Ref(cpcrun.CPC):
    def __init__(self, mem, defer=True):
        super().__init__(mem, entry=0x164B)
        self.every = 10 ** 9
        self.timed = True
        self.defer = defer
        self.units = 0
        self.tick = 0
        self.works = 0
        self.since = 0
        self.world = []
        self.passes = []
        self.ticks = []
        self.ay_ref = []
        self.trees = []
        self.deferred = []
        self.held = None
        self.boot = None
        self.prev = np.zeros(65536, np.uint8)

    def out(self, port, v):
        super().out(port, v)
        if port & 0x0800 == 0 and (port >> 8) & 3 == 2 and v >> 6 == 2:
            self.ay_ref.append((self.tick, self.ay_sel, self.ppi[0]))

    def vector(self):
        mem = self.m.memory
        return mem[0x39] | mem[0x3A] << 8

    def take_int(self):
        if self.vector() == WORLD:
            m = self.m
            self.world.append((self.frame, self.units, self.tick, m.pc, m.hl, m.de, m.bc))
            self.works += 1
            self.since += 1
        super().take_int()

    def unit(self):
        if self.since and self.boot:
            mem = np.frombuffer(bytes(self.m.memory), np.uint8)
            self.passes.append((self.frame, self.units, self.tick, self.works,
                                zlib.compress((mem ^ self.prev).tobytes(), 6)))
            self.prev = mem.copy()
        self.since = 0
        if self.units == 0:
            self.boot = (self.frame, self.works, bytes(self.m.memory), self.tick)
        self.units += 1

    def run_line_timed(self):
        m = self.m
        end = self.tline + cpcrun.LINE
        mem = m.memory
        while m.frame_tick < end:
            pc = m.pc
            if self.int_pending and m.iff1:
                if self.defer and (SPAN_LO <= pc <= SPAN_HI or LATCH_LO <= pc <= LATCH_HI) \
                        and self.vector() == WORLD:
                    if self.held is None:
                        self.held = (self.frame, self.mline)
                else:
                    if self.held is not None:
                        self.deferred.append((self.held[0], self.mline - self.held[1]))
                        self.held = None
                    self.take_int()
                    self.set_tick(m.frame_tick + 4 * cpcrun.cpctime.INT_NOPS)
                    continue
            if pc in (UNIT_SPAN, UNIT_WAIT, UNIT_SQUARE, UNIT_EDGE, UNIT_SIDE):
                self.unit()
            elif pc == TREE:
                self.trees.append((self.frame, self.units, mem[0x1D52] | mem[0x1D53] << 8,
                                   mem[0x1115] | mem[0x1116] << 8))
            elif pc == MUSIC_DONE:
                self.ticks.append(bytes(mem[0x2000:0x2400]))
            elif pc == 0x204B:
                self.tick += 1
            self.step()
        self.set_tick(m.frame_tick - end)
        self.tline = 0


def load_passes(path):
    """yield (field, units, ticks, works, mem64k) for each record"""
    prev = np.zeros(65536, np.uint8)
    with open(path, 'rb') as f:
        while True:
            h = f.read(20)
            if len(h) < 20:
                return
            field, units, ticks, works, n = struct.unpack('<IIIII', h)
            prev = prev ^ np.frombuffer(zlib.decompress(f.read(n)), np.uint8)
            yield field, units, ticks, works, prev


def load_world(path):
    """[(field, units, ticks, pc, hl, de, bc)]: the main loop's registers when it came"""
    out = []
    for line in open(path):
        v = line.split()
        out.append(tuple(map(int, v[:3])) + tuple(int(x, 16) for x in v[3:]))
    return out


def main(memfile, outdir, fields, defer=True):
    os.makedirs(outdir, exist_ok=True)
    c = Ref(open(memfile, 'rb').read(), defer)
    c.tline = c.m.frame_tick
    while c.frame < fields:
        c.run_line()
        c.end_line()
    with open(os.path.join(outdir, 'passes.bin'), 'wb') as f:
        for field, units, ticks, works, z in c.passes:
            f.write(struct.pack('<IIIII', field, units, ticks, works, len(z)) + z)
    with open(os.path.join(outdir, 'world.log'), 'w') as f:
        for fr, u, t, pc, hl, de, bc in c.world:
            f.write(f'{fr} {u} {t} {pc:04X} {hl:04X} {de:04X} {bc:04X}\n')
    np.save(os.path.join(outdir, 'ticks.npy'),
            np.frombuffer(b''.join(c.ticks), np.uint8).reshape(len(c.ticks), -1))
    with open(os.path.join(outdir, 'ay.log'), 'w') as f:
        for t, r, v in c.ay_ref:
            f.write(f'{t} {r} {v}\n')
    fr, n, mem, tk = c.boot
    open(os.path.join(outdir, 'boot.txt'), 'w').write(f'{fr} {n} {tk}\n')
    open(os.path.join(outdir, 'boot.bin'), 'wb').write(mem)
    with open(os.path.join(outdir, 'trees.log'), 'w') as f:
        for fr2, u, p, l in c.trees:
            f.write(f'{fr2} {u} {p:04X} {l:04X}\n')
    with open(os.path.join(outdir, 'deferred.log'), 'w') as f:
        for fr2, k in c.deferred:
            f.write(f'{fr2} {k}\n')
    with open(os.path.join(outdir, 'crtc.log'), 'w') as f:
        for fr2, ln, t, p, v in c.out_log:
            f.write(f'{fr2} {ln} {t} {p:04X} {v:02X}\n')
    print(f'{c.frame} fields, {c.works} world works ({n} in the boot, field {fr}), {len(c.passes)} '
          f'records, {c.units} units, {len(c.ticks)} ticks, {len(c.ay_ref)} AY writes, '
          f'{len(c.trees)} trees, {len(c.deferred)} held back '
          f'(max {max((k for _, k in c.deferred), default=0)} lines)')


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2], int(sys.argv[3]), os.environ.get('NODEFER') != '1')
