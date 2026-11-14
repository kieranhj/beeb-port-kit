"""Coverage of the original under tools/cpcrun.py's CPC timing: every address executed as an
instruction start over FIELDS fields, with the field it was first executed in.
Writes OUTDIR/cov.txt (hex address per line, for tools/covdis.py) and cov_first.txt (address field).
Usage: python tools/cpccov.py MEM.bin OUTDIR FIELDS"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
import cpcrun  # noqa: E402


class Cov(cpcrun.CPC):
    def __init__(self, mem):
        super().__init__(mem)
        self.every = 10 ** 9
        self.timed = True
        self.seen = {}

    def step(self):
        pc = super().step()
        if pc not in self.seen:
            self.seen[pc] = self.frame
        return pc


if __name__ == '__main__':
    c = Cov(open(sys.argv[1], 'rb').read())
    c.tline = c.m.frame_tick
    while c.frame < int(sys.argv[3]):
        c.run_line()
        c.end_line()
    out = sys.argv[2]
    os.makedirs(out, exist_ok=True)
    open(os.path.join(out, 'cov.txt'), 'w').write(''.join(f'{a:04X}\n' for a in sorted(c.seen)))
    open(os.path.join(out, 'cov_first.txt'), 'w').write(
        ''.join(f'{a:04X} {f}\n' for a, f in sorted(c.seen.items())))
    print(len(c.seen), 'instruction starts')
