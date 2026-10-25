"""z80sub.py - an arcade sub-CPU (a sound Z80, typically) run headless from its ROM.

Fork this into your project's tools/; keep this header.

From 1942-beeb's `tools/sound_rip.py` (`SoundCPU`) and `tools/z80dis.py`, on Ivan
Kosarev's `z80` package (`pip install z80`; MIT; 1.2.0 measured here). In 1942 the sound
is a Z80 at 3 MHz driving two AY-3-8910s from a latch the main CPU writes, and
sound_rip.py was THE ONLY MODEL of it: probe_sound.py scored it against MAME, RAM for
RAM, over 3,000 frames of the 1942a clone with commands injected into the main CPU's
request ring (template/tools/mame/subcpu_ram.lua) - 2,859 frames match, 146 "torn"
(MAME sampled mid-IRQ; every one followed by a match), 0 wrong. Every sound the port
ships was ripped from this model and converted offline (beeb_port_kit/ay2sn.py).

What it took, all of it in this module:

  * MMIO by MARKS. The z80 package calls back only on marked addresses; mark the
    latch for reads and the chip ports for writes, and every other access is plain
    memory at full speed. A write callback must store the byte itself if the address
    is also RAM.
  * A HELD IRQ, not a pulse. MAME's irq0_line_hold asserts every period and the CPU
    takes it whenever interrupts are next enabled. Two things delay it: a handler
    that returns with `ret` (not `reti`/`ei`) into an `ei` that holds interrupts
    off one more instruction, and a command handler that runs with interrupts off
    for a long time (re-measured 2026-10-25 on this module: 1942's $11 takes its IRQ
    up to 3,067 T late on 905 of its first 2,400; $17 loses one assertion WHOLE, a
    12,500 T period). So step() runs until
    the IRQ is taken, takes the LATENESS off the rest of the period, and counts a
    period lost whole as `merged`. Without the accounting the model drifts a cycle
    or two an IRQ and the RAM comparison fails after a few seconds.
  * The IRQ RATE IS MEASURED, not read off a schematic: 1942's handler opens
    `inc ($4000)`, so the counter's step per MAME frame is the rate (4 per frame,
    2,977 of 3,000 frames; the rest boot).
  * A clone() that copies the machine state exactly, because aligning a latch change
    against a capture that only samples at frame end means trying it at each of the
    IRQs inside the frame (probe_sound.py's search).

`z80` is imported when a SubCPU is first made, so the rest of the kit works without it.

    cpu = SubCPU([(0, rom)], clock=3_000_000, irq_hz=240,
                 reads={0x6000: lambda a: latch[0]},
                 writes={0x8000: ay_sel, 0x8001: ay_data})
    cpu.boot(2_000_000, until=lambda c: c.pc in (0x64, 0x65) and c.iff1)
    for _ in range(n): cpu.step()
"""

TICKS_PER_FRAME = 100_000     # the z80 package's frame_tick modulus (_z80module.cpp)


def _z80():
    try:
        import z80
    except ImportError:
        raise ImportError("z80sub needs the `z80` package: pip install z80")
    return z80


class SubCPU:
    """A Z80 with ROM/RAM images, memory-mapped I/O callbacks and a held IRQ.

    images: [(address, bytes)] loaded into the 64K space.
    reads:  {address: fn(address) -> byte}   marked READ: the value the CPU sees
    writes: {address: fn(address, value)}    marked WRITE: called, then the byte is
            stored to memory as well unless store_writes is False
    """

    def __init__(self, images, clock, irq_hz, reads=None, writes=None,
                 store_writes=True, ticks_per_frame=TICKS_PER_FRAME):
        z80 = _z80()
        self.clock, self.irq_hz = clock, irq_hz
        self.ticks_per_irq = clock // irq_hz
        self.ticks_per_frame = ticks_per_frame
        self.reads, self.writes = dict(reads or {}), dict(writes or {})
        self.store_writes = store_writes
        self.irq = 0                # IRQs taken
        self.merged = 0             # assertions lost whole to a long handler
        self.images = list(images)
        self.m = z80.Z80Machine()
        for addr, data in self.images:
            self.m.set_memory_block(addr, data)
        self._wire()

    def _wire(self):
        m = self.m
        m.set_read_callback(self._read)
        m.set_write_callback(self._write)
        for a in self.reads:
            m.mark_addrs(a, 1, m.READ_MARK)
        for a in self.writes:
            m.mark_addrs(a, 1, m.WRITE_MARK)

    def _read(self, a):
        fn = self.reads.get(a)
        return (fn(a) & 0xFF) if fn else self.m.memory[a]

    def _write(self, a, v):
        fn = self.writes.get(a)
        if fn:
            fn(a, v)
        if self.store_writes or not fn:
            self.m.memory[a] = v & 0xFF

    # --- running -------------------------------------------------------------------
    @property
    def pc(self):
        return self.m.pc

    @property
    def iff1(self):
        return self.m.iff1

    def run(self, ticks):
        """Run for `ticks` T-states (or until the package stops)."""
        m = self.m
        m.ticks_to_stop = ticks
        while True:
            ev = m.run()
            if m.ticks_to_stop == 0 or ev & m._TICKS_LIMIT_HIT:
                return

    def boot(self, ticks, until=None):
        """Run the reset path. `until(cpu)` is asserted afterwards: a boot that does
        not reach the idle loop is a model that is not the machine."""
        self.run(ticks)
        if until is not None and not until(self):
            raise RuntimeError("boot did not reach its idle state: pc $%04X iff1 %s"
                               % (self.m.pc, self.m.iff1))

    def step(self, max_wait=1_000_000):
        """One IRQ, then the rest of its period. Returns the T-states it was late."""
        self.irq += 1
        m = self.m
        t0 = m.frame_tick
        for _ in range(max_wait):
            if m.on_handle_active_int():
                break
            self.run(1)
        else:
            raise RuntimeError("IRQ %d not taken at pc $%04X" % (self.irq, m.pc))
        late = (m.frame_tick - t0) % self.ticks_per_frame
        lost = 0
        while late >= self.ticks_per_irq:
            late -= self.ticks_per_irq
            self.merged += 1
            lost += 1
        self.run(self.ticks_per_irq - late)
        return late + lost * self.ticks_per_irq

    def ram(self, lo, hi):
        """memory[lo:hi] as bytes."""
        return bytes(self.m.memory[lo:hi])

    def clone(self):
        """A second SubCPU in exactly this one's state, callbacks rebound to it.
        The callables are SHARED: if they close over state (a latch, a register
        file), give the clone its own before stepping both."""
        z80 = _z80()
        new = SubCPU.__new__(SubCPU)
        new.__dict__.update({k: v for k, v in self.__dict__.items() if k != "m"})
        new.reads, new.writes = dict(self.reads), dict(self.writes)
        m = z80.Z80Machine()
        m.set_memory_block(0, bytes(self.m.memory))
        st = m.get_state_view()
        st[:] = self.m.get_state_view()
        new.m = m
        new._wire()
        return new


class AYPorts:
    """An AY-3-8910's address/data port pair as a write sink: `sel(a, v)` latches the
    register, `data(a, v)` writes it. `regs` is the register file, `log` every write
    as (irq, reg, value). Hook them into SubCPU.writes."""

    def __init__(self, clock_source=None):
        self.regs = [0] * 16
        self.select = 0
        self.log = []
        self._irq = clock_source or (lambda: 0)

    def sel(self, a, v):
        self.select = v & 0xFF

    def data(self, a, v):
        if self.select < 16:
            self.regs[self.select] = v & 0xFF
        self.log.append((self._irq(), self.select, v & 0xFF))


def disassemble(fetch, addr, count=30):
    """[(addr, bytes, text)] for `count` instructions from `addr`, with the z80
    package's own decoder. `fetch(addr)` -> byte (romset.Banked.fetcher()).

    Print a table's pointers with this rather than reading them by eye: 1942's
    dispatch table was misread with one digit transposed and the wrong handler -
    a bare `ret` - was documented as "no steering at all" (arcade-facts s18)."""
    z80 = _z80()
    builder = z80.Z80InstrBuilder()
    out = []
    for _ in range(count):
        raw = bytes(fetch((addr + k) & 0xFFFF) for k in range(4))
        instr, size = builder.build_instr(addr, raw)
        out.append((addr, raw[:size], str(instr)))
        addr = (addr + size) & 0xFFFF
    return out
