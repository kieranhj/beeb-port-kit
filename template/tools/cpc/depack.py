"""Run the original's Shrinkler depacker (kosarev z80); save the 64K image at the demo's entry.

Usage: python tools/depack.py FILE OUT.bin [LOAD EXEC ENTRY]   (hex; default Square Roots':
       load &4000, exec &4087, entry &164B. Isometrikum's were &8000, &8E50, &2D0A.)
The firmware's TXT OUTPUT (&BB5A) is a RET; the stub unpacks and jumps to ENTRY.
As a library: run(data, load, exe, entry) -> 64K bytes.
"""
import sys

import z80

LOAD, EXEC, ENTRY = 0x4000, 0x4087, 0x164B


def run(data, load=LOAD, exe=EXEC, entry=ENTRY):
    m = z80.Z80Machine()
    img = bytearray(65536)
    img[load:load + len(data)] = data
    img[0xBB5A] = 0xC9
    m.set_memory_block(0, img)
    m.pc, m.sp = exe, 0xBFF0
    m.set_breakpoint(entry)
    n = 0
    while m.pc != entry:
        m.ticks_to_stop = 1000000
        m.run()
        n += 1
        assert n < 1000, 'the stub never reached the entry'
    return bytes(m.memory)


if __name__ == '__main__':
    a = [int(x, 16) for x in sys.argv[3:6]] or [LOAD, EXEC, ENTRY]
    mem = run(open(sys.argv[1], 'rb').read(), *a)
    print('PC at entry &%04X' % a[2])
    open(sys.argv[2], 'wb').write(mem)
