"""Disassemble the original along its coverage (tools/cpccov.py): every executed instruction
start, in address order, with a gap marker where execution never went (data or dead code).
python tools/covdis.py MEM.bin cov.txt START END"""
import sys
from skoolkit.snaskool import DisassemblerConfig
from skoolkit.disassembler import Disassembler

class Instruction:
    def __init__(self, address, operation, data):
        self.address, self.operation, self.bytes = address, operation, data
mem = list(open(sys.argv[1], 'rb').read())
cov = [int(l, 16) for l in open(sys.argv[2])]
# kosarev's core stops between a DD/FD prefix and its opcode: drop the second stop
covs = set(cov)
cov = [a for a in cov if not (a - 1 in covs and mem[a - 1] in (0xDD, 0xFD))]
s, e = int(sys.argv[3], 16), int(sys.argv[4], 16)
cfg = DisassemblerConfig(True, False, 8, 65, 1, 0, Instruction, '', 0)
d = Disassembler(mem, cfg)
prev_end = None
for a in cov:
    if not s <= a < e:
        continue
    ins = d.disassemble(a, a + 1, 'h')[0]
    n = len(ins.bytes)
    if prev_end is not None and a != prev_end:
        tag = 'OVERLAP' if a < prev_end else f'-- gap {prev_end:04X}-{a - 1:04X}'
        print(f'      {tag}')
    b = ' '.join(f'{x:02X}' for x in mem[a:a + n])
    print(f'{a:04X}  {b:<12} {ins.operation}')
    prev_end = a + n
