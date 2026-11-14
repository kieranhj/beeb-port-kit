"""The reference capture for the port: the original's LOGICAL field sequence (decision 6).

Runs the unpacked original on tools/cpcrun.py's CPC with two changes that make it the
"ideal 50 Hz" machine the port is held to:

  * the Z80 runs 4x fast (1,024 T a scanline), so no main-loop pass ever overruns a field;
  * the VSYNC input (PPI port B bit 0) reads 1 once per field, on the first read after
    VSYNC starts, so every call of the wait at &3614 waits for a NEW field - what the
    original's 7-field delays in the logo (&3633) do on a real CPC, where the DJNZ after the
    wait outlasts VSYNC.

  * interrupts are queued and taken only while the CPU waits in &3616-&361B (after the snapshot at &3614), so a pass
    always sees the music as it stood at the start of its field (decision 8). On a real CPC
    the main loop reads channel 1 about two lines before the tick (a race the original wins
    by ~128 us) and channels 2-3 after drawing the first object, either side of it.

So the music player runs once per field and the main loop once per field, and the result
does not depend on the CPC's timing (except LD A,R, recorded for the models; decision 7).
The CRTC writes in crtc.log are therefore late in the field: use tools/cpcrun.py for the
displayed picture.

Writes OUTDIR/
  passes.bin   one record per call of &3614 (the logic's "field done"): u32 field, u16 caller,
               u32 interrupts taken so far, u32 len, then zlib(64K XOR the previous record's
               64K). Read with load_passes()
  ticks.npy    uint8 [ticks, &2369-&2000]: &2000-&2368 (player state and self-modified
               operands) after each call of the player from the first interrupt (&32AF)
  ay.log       tick reg value   (every AY write, tick = player calls started so far)
  r.log        pass value       (A after each LD A,R at &35F2)
  songs.log    tick hl          (each tune start, &205D, with the ticks completed before it)
  crtc.log     field line port value  (every OUT, as cpcrun's out.log)
Usage: python tools/cpcref.py MEM.bin OUTDIR FIELDS
"""
import os
import struct
import sys
import zlib

import numpy as np

sys.path.insert(0, os.path.dirname(__file__))
import cpcrun  # noqa: E402

cpcrun.LINE = 1024


class Ref(cpcrun.CPC):
    def __init__(self, mem):
        super().__init__(mem, entry=int(os.environ.get('ENTRY', '2D0A'), 16))  # kit: Isometrikum's entry
        self.every = 10 ** 9            # no picture rendering
        self.int_count = 0
        self.ints = 0
        self.edge = False
        self.tick = 0
        self.passes = []
        self.ticks = []
        self.ay_ref = []
        self.r_log = []
        self.songs = []
        self.prev = bytes(65536)
        for a in (0x3614, 0x32AF, 0x32B2, 0x35F4, 0x205D):
            self.m.set_breakpoint(a)

    def inp(self, port):
        if port & 0x0800 == 0 and (port >> 8) & 3 == 1:
            if self.edge:
                self.edge = False
                return 0x1F
            return 0x1E
        return 0xFF

    def start_vsync(self, clock=False):
        # fields come from a fixed 312-line clock, not the CRTC: the queued interrupts
        # write the rupture's registers late, and the reference is the logic, not the picture
        if not clock:
            return
        if not self.vsync:
            self.edge = True
        super().start_vsync()

    def out(self, port, v):
        super().out(port, v)
        if port & 0x0800 == 0 and (port >> 8) & 3 == 2 and v >> 6 == 2:
            self.ay_ref.append((self.tick, self.ay_sel, self.ppi[0]))

    def hook(self, pc):
        m = self.m
        if pc == 0x3614:
            mem = bytes(m.memory)
            sp = m.sp
            caller = (mem[sp] | mem[(sp + 1) & 0xFFFF] << 8) - 3
            delta = bytes(a ^ b for a, b in zip(mem, self.prev)) if False else \
                (np.frombuffer(mem, np.uint8) ^ np.frombuffer(self.prev, np.uint8)).tobytes()
            self.passes.append((self.frame, caller & 0xFFFF, self.ints, zlib.compress(delta, 6)))
            self.prev = mem
        elif pc == 0x32AF:
            self.tick += 1
        elif pc == 0x32B2:
            self.ticks.append(bytes(m.memory[0x2000:0x2369]))
        elif pc == 0x35F4:
            self.r_log.append((len(self.passes), m.a))
        elif pc == 0x205D:
            self.songs.append((self.tick, m.hl))

    def run_line(self):
        m = self.m
        end = self.tline + cpcrun.LINE
        while m.frame_tick < end:
            if self.int_count and m.iff1 and 0x3616 <= m.pc < 0x361C:
                self.int_count -= 1
                self.take_int()
            m.ticks_to_stop = min(end - m.frame_tick, 64)
            if m.run() & 1:
                self.hook(m.pc)
                m.step_over_breakpoint()
        over = m.frame_tick - end
        m._StateBase__frame_tick[:] = over.to_bytes(4, 'little')
        self.tline = 0


    def take_int(self):
        # a queued interrupt's acknowledge must not clear the GA counter's bit 5 late
        keep = self.icount
        self.ints += 1
        super().take_int()
        self.icount = keep

    def end_line(self):
        super().end_line()
        self.lines = getattr(self, 'lines', 0) + 1
        if self.lines == cpcrun.LINES:
            self.lines = 0
            self.start_vsync(clock=True)
        if self.int_pending:            # queue the GA's interrupt (see the docstring)
            self.int_pending = False
            self.int_count += 1


def load_passes(path):
    """yield (field, caller, ints, mem64k) for each record"""
    prev = np.zeros(65536, np.uint8)
    with open(path, 'rb') as f:
        while True:
            h = f.read(14)
            if len(h) < 14:
                return
            field, caller, ints, n = struct.unpack('<IHII', h)
            prev = prev ^ np.frombuffer(zlib.decompress(f.read(n)), np.uint8)
            yield field, caller, ints, prev


def main(memfile, outdir, fields):
    os.makedirs(outdir, exist_ok=True)
    c = Ref(open(memfile, 'rb').read())
    c.tline = c.m.frame_tick
    while c.frame < fields:
        c.run_line()
        c.end_line()
    with open(os.path.join(outdir, 'passes.bin'), 'wb') as f:
        for field, caller, ints, z in c.passes:
            f.write(struct.pack('<IHII', field, caller, ints, len(z)) + z)
    np.save(os.path.join(outdir, 'ticks.npy'), np.frombuffer(b''.join(c.ticks), np.uint8).reshape(len(c.ticks), -1))
    with open(os.path.join(outdir, 'ay.log'), 'w') as f:
        for t, r, v in c.ay_ref:
            f.write(f'{t} {r} {v}\n')
    with open(os.path.join(outdir, 'songs.log'), 'w') as f:
        for t, hl in c.songs:
            f.write(f'{t} {hl:04X}\n')
    with open(os.path.join(outdir, 'r.log'), 'w') as f:
        for p, v in c.r_log:
            f.write(f'{p} {v}\n')
    with open(os.path.join(outdir, 'crtc.log'), 'w') as f:
        for fr, ln, t, p, v in c.out_log:
            f.write(f'{fr} {ln} {t} {p:04X} {v:02X}\n')
    callers = {}
    for _, cl, _, _ in c.passes:
        callers[cl] = callers.get(cl, 0) + 1
    print(f'{c.frame} fields, {len(c.passes)} passes {dict((hex(k), v) for k, v in callers.items())}, '
          f'{len(c.ticks)} ticks, {len(c.ay_ref)} AY writes, {len(c.r_log)} LD A,R')


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2], int(sys.argv[3]))
