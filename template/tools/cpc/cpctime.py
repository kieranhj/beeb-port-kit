"""CPC instruction timing: a Z80 instruction's length on an Amstrad CPC, in microseconds ("NOPs").

The Gate Array stretches every memory and I/O cycle onto a 1 us grid, so an instruction's
length is not its T count / 4. The rule used here: ceil(T / 4), with the exceptions known from
CPC demo timing tables (an M-cycle pattern that loses a partial microsecond). T is what kosarev's
core charged for the instruction just executed, so taken / not-taken branches and the repeats of
LDIR / OTIR are told apart by T.

NOT MEASURED: there is no CPC emulator on this machine. The table is the CPC scene's, from
memory; tools/cpcrun.py's timing mode is checked only for consistency - the original's own
cycle-counted delays (&1C5B, &1710) land where its author put them, and the demo runs to its end
without the span overrun that wrecks &0038 (docs/layer-1-spec.md).
"""

# (prefix, opcode) -> {T: nops} exceptions; prefix '' / 'CB' / 'ED' / 'DD' (DD and FD alike) /
# 'DDCB'
EXC = {}


def _set(prefix, ops, t, n):
    for o in ops:
        EXC.setdefault((prefix, o), {})[t] = n


_set('', [0xC5, 0xD5, 0xE5, 0xF5], 11, 4)               # PUSH rr
_set('', range(0xC7, 0x100, 8), 11, 4)                    # RST
_set('', [0xC0, 0xC8, 0xD0, 0xD8, 0xE0, 0xE8, 0xF0, 0xF8], 11, 4)   # RET cc taken
_set('', [0x10], 8, 3)                                    # DJNZ not taken
_set('', [0xE3], 19, 6)                                   # EX (SP),HL
_set('', [0x22, 0x2A], 16, 5)                             # LD (nn),HL / LD HL,(nn)
_set('ED', [0x40, 0x48, 0x50, 0x58, 0x60, 0x68, 0x70, 0x78], 12, 4)   # IN r,(C)
_set('ED', [0x41, 0x49, 0x51, 0x59, 0x61, 0x69, 0x71, 0x79], 12, 4)   # OUT (C),r
_set('ED', [0x43, 0x53, 0x63, 0x73, 0x4B, 0x5B, 0x6B, 0x7B], 20, 6)   # LD (nn),rr / rr,(nn)
_set('ED', [0xA0, 0xA8, 0xB0, 0xB8], 16, 5)               # LDI/LDD, LDIR/LDDR last
_set('ED', [0xA2, 0xAA, 0xB2, 0xBA], 16, 5)               # INI/IND
_set('ED', [0xA3, 0xAB, 0xB3, 0xBB], 16, 5)               # OUTI/OUTD, OTIR/OTDR last
_set('DD', [0x36], 19, 6)                                 # LD (IX+d),n
_set('DD', [0xE5], 15, 5)                                 # PUSH IX
_set('DD', [0x22, 0x2A], 20, 6)                           # LD (nn),IX / IX,(nn)
_set('DD', [0xE3], 23, 7)                                 # EX (SP),IX
_set('DDCB', range(0x40, 0x80), 20, 6)                    # BIT b,(IX+d)
_set('DDCB', range(0x00, 0x40), 23, 7)                    # rotates/shifts (IX+d)
_set('DDCB', range(0x80, 0x100), 23, 7)                   # RES/SET b,(IX+d)

INT_NOPS = 5        # an IM 1 interrupt's acknowledge and RST &38


def nops(mem, pc, t):
    """the CPC length of the instruction at pc, which took t T states in the core"""
    b = mem[pc]
    if b in (0xDD, 0xFD):
        o = mem[(pc + 1) & 0xFFFF]
        key = ('DDCB', mem[(pc + 3) & 0xFFFF]) if o == 0xCB else ('DD', o)
    elif b == 0xED:
        key = ('ED', mem[(pc + 1) & 0xFFFF])
    elif b == 0xCB:
        key = ('CB', mem[(pc + 1) & 0xFFFF])
    else:
        key = ('', b)
    e = EXC.get(key)
    if e and t in e:
        return e[t]
    return (t + 3) // 4
