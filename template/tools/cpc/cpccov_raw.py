"""Coverage of the original under tools/cpcrun.py (raw timing, real interrupts): every address
executed as an instruction start, over FIELDS fields, anywhere in 64K, with the field each was
first hit. Used to find the code before the reference (tools/cpcref.py) existed.
Writes OUTDIR/cov_raw.txt (hex address, first field).
Usage: python tools/cpccov_raw.py MEM.bin OUTDIR FIELDS"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
import cpcrun  # noqa: E402


class Cov(cpcrun.CPC):
    def __init__(self, mem):
        super().__init__(mem)          # kit: the entry from ENTRY=hex (cpcrun.py)
        self.every = 10 ** 9
        self.seen = {}
        for a in range(0x0000, 0x10000):
            self.m.set_breakpoint(a)

    def run_line(self):
        m = self.m
        end = self.tline + cpcrun.LINE
        while m.frame_tick < end:
            if self.int_pending and m.iff1:
                self.take_int()
            m.ticks_to_stop = min(end - m.frame_tick, 64)
            if m.run() & 1:
                pc = m.pc
                self.seen.setdefault(pc, self.frame)
                m.clear_breakpoint(pc)
        over = m.frame_tick - end
        m._StateBase__frame_tick[:] = over.to_bytes(4, 'little')
        self.tline = 0


c = Cov(open(sys.argv[1], 'rb').read())
c.tline = c.m.frame_tick
while c.frame < int(sys.argv[3]):
    c.run_line()
    c.end_line()
os.makedirs(sys.argv[2], exist_ok=True)
open(os.path.join(sys.argv[2], 'cov_raw.txt'), 'w').write(
    ''.join(f'{a:04X} {f}\n' for a, f in sorted(c.seen.items())))
open(os.path.join(sys.argv[2], 'cov.txt'), 'w').write(''.join(f'{a:04X}\n' for a in sorted(c.seen)))
print(len(c.seen), 'instruction starts')
