"""
fdc.py - the CPC's uPD765A, polled (no interrupts, no DMA), enough for a polling track loader
(phX's was Arnoldemu's). From the phX port, 2026-11 (its tools/fdc.py, unchanged but for this
docstring). Used by cpcboot.py: FDC(disc.Disc, clock), clock() the CPU's absolute T-states.

Ports: &FB7E main status (read), &FB7F data (read/write), &FA7E motor (write, bit 0).
Commands: &03 specify, &04 sense drive status, &07 recalibrate, &08 sense interrupt status, &0F
seek, read data (&06 and its MT/MF/SK variants, e.g. &46), &0A/&4A read ID. Anything else
(write, format, scan, read track) is answered as an invalid command (ST0 = &80): a loader that
writes or formats needs more here.

TIMING (PROVISIONAL: modelled from the uPD765 data sheet, not measured on a CPC; phX's WinAPE
check found its three in-demo loads 1-2.6 s off WinAPE's drive, in both directions - two models,
neither yet a real drive). The CPC clocks the 765 at 4 MHz, so the data sheet's 8 MHz times
double. The disc turns at 300 rpm: 200 ms, 6,250 byte-times of 32 us (250 kbit/s MFM).
  - Layout: the 765's own format (GAP4a 80, sync 12, IAM 4, GAP1 50, then per sector sync 12,
    IDAM 4, ID 4, CRC 2, GAP2 22, sync 12, DAM 4, data, CRC 2, GAP3), GAP3 the DSK's but cut so
    the track fits a turn (e.g. 10 x 512 at a 610-byte pitch, which is what an HFE image of such
    a disc showed). Every track starts at the index (no skew: a real disc's skew is not in a
    DSK); the index's phase at T = 0 is `index_phase_t`, the turn `turn_t` (300 rpm exactly
    unless set: a real drive is within a percent or two). A demo whose loads race its music can
    lock to phase 0 / 300 rpm or hang at another phase: vary both (cpcboot --index-phase, --rpm).
  - Read data waits for the sector's ID address mark to come under the head (a mark already
    passed costs a turn), then delivers a byte every 32 us; RQM shows only while a byte waits.
  - Overrun: a byte still unread when the next one arrives (32 us) ends the read: ST0 = &4x,
    ST1 = &10 (OR), the result phase at once (UNVERIFIED: the data sheet guarantees only 13 us
    at 8 MHz MFM, 26 us here, and does not say when the result phase starts). The 765A does
    not flag an overrun on the last byte.
  - Seek and recalibrate: one step pulse every SRT ((16 - SRT) x 2 ms), Seek End (sense
    interrupt status) after the last; until then sense interrupt status answers &80. A loader
    that sends no SPECIFY gets what AMSDOS left: &A1 &03, 12 ms a step (UNVERIFIED: the AMSDOS
    values are from memory). Head load and unload times, and the motor's spin-up, are not
    modelled (the motor bit is stored, never waited for).
  - As on a CPC, no terminal count: a read ends past EOT with ST0 = &4x and ST1 = &80 (EN).
  - Only one disc: every drive number reads the same image, and side 1 is the DSK's second side.
`overrun_ends`, `seek_timed`, `ids_needed` = False give the first, simpler model (cpcboot
--fdc-v1: overruns counted but ignored, seeks instant, no ID to wait for).

    python fdc.py          prints this
"""

T_US = 4                    # T-states a microsecond
BYTE_T = 32 * T_US          # one byte time
OR_T = 32 * T_US            # a byte still unread when the next one arrives is an overrun (see the docstring)
TURN_T = 200000 * T_US      # one revolution
TURN_BYTES = 6250
TRACK_HEAD = 146            # GAP4a, sync, IAM, GAP1: the index to the first sector's sync


class FDC:
    def __init__(self, disc, clock):
        self.disc = disc
        self.clock = clock              # callable: the CPU's absolute time in T-states
        self.pcn = [0, 0, 0, 0]         # present cylinder per drive
        self.motor = 0
        self.cmd = []
        self.result = []
        self.phase = 'cmd'              # cmd, exec, result
        self.int_pending = []           # (due t, st0, pcn) for sense interrupt status
        self.exec_bytes = b''
        self.exec_i = 0
        self.next_byte_t = 0
        self.exec_r = [0]               # the sector IDs (R) of a read, in order
        self.exec_len = 512             # their length
        self.ovr_seen = -1              # the byte index already counted as an overrun
        self.overrun_ends = True        # False: count overruns but deliver the data (pre-fix model)
        self.seek_timed = True          # False: seeks end at once (pre-fix model)
        self.ids_needed = True          # False: the pre-fix sector positions, no ID to wait for
        self.exec_gap = 0
        self.index_phase_t = 0          # T-states of the turn already gone at T = 0
        self.turn_t = TURN_T            # one revolution (cpcboot --rpm)
        # SPECIFY as AMSDOS leaves it (&A1, &03: SRT 12 ms, HUT 32 ms, HLT 4 ms at 4 MHz;
        # UNVERIFIED, from memory): until the loader sends its own
        self.srt, self.hut, self.hlt, self.nd = 0xA, 0x1, 0x1, 1
        self.overruns = 0
        self.log = []                   # (t, 'cmd'|'res', bytes)

    # ------------------------------------------------------------------ status
    def msr(self):
        if self.phase == 'cmd':
            return 0x80 | (0x10 if self.cmd else 0)
        if self.phase == 'result':
            return 0xD0
        # execution: RQM only when the next byte has come round
        t = self.clock()
        if self.overrun(t):
            return 0xD0
        if t >= self.next_byte_t:
            return 0xF0
        return 0x70

    def overrun(self, t):
        """a byte not taken within OR_T of its arrival ends the read (OR); True if it has"""
        if t <= self.next_byte_t + OR_T or self.exec_i >= len(self.exec_bytes) - 1 \
                or self.ovr_seen == self.exec_i:
            return False                    # (the last byte: the 765A does not flag it)
        self.ovr_seen = self.exec_i
        due = self.next_byte_t + OR_T
        self.overruns += 1
        self.log.append((due, 'ovr', bytes([self.exec_i >> 8, self.exec_i & 255])))
        if not self.overrun_ends:
            return False                    # the first model: counted only
        res = list(self.exec_result)
        res[0] = 0x40 | (res[0] & 7)        # abnormal termination
        res[1], res[2] = 0x10, 0x00         # ST1 = OR
        res[5] = self.exec_r[self.exec_i // self.exec_len]
        self.phase = 'result'
        self.result = res
        self.log.append((due, 'res', bytes(res)))
        return True

    # ------------------------------------------------------------------ data port
    def read_data(self):
        if self.phase == 'exec':
            t = self.clock()
            if self.overrun(t):
                return self.read_data()     # the result phase's first byte
            if t < self.next_byte_t:
                return 0xFF                 # read before RQM: the bus floats
            b = self.exec_bytes[self.exec_i]
            self.exec_i += 1
            self.next_byte_t += BYTE_T      # the disc does not wait for a late CPU
            if self.exec_i % self.exec_len == 0:
                self.next_byte_t += self.exec_gap   # multi-sector: the next sector's ID and gaps
            if self.exec_i >= len(self.exec_bytes):
                self.phase = 'result'
                self.result = list(self.exec_result)
                self.log.append((t, 'res', bytes(self.result)))
            return b
        if self.phase == 'result' and self.result:
            b = self.result.pop(0)
            if not self.result:
                self.phase = 'cmd'
            return b
        return 0xFF

    def write_data(self, v):
        if self.phase != 'cmd':
            return
        self.cmd.append(v)
        need = self.length(self.cmd[0])
        if len(self.cmd) >= need:
            c, self.cmd = self.cmd, []
            self.log.append((self.clock(), 'cmd', bytes(c)))
            self.execute(c)

    @staticmethod
    def length(op):
        o = op & 0x1F
        return {0x03: 3, 0x04: 2, 0x07: 2, 0x08: 1, 0x0F: 3, 0x06: 9, 0x0C: 9, 0x0A: 2,
                0x05: 9, 0x09: 9, 0x02: 9, 0x0D: 6, 0x11: 9, 0x19: 9, 0x1D: 9}.get(o, 1)

    def motor_write(self, v):
        self.motor = v & 1

    # ------------------------------------------------------------------ commands
    def set_result(self, res):
        self.result = list(res)
        self.phase = 'result' if res else 'cmd'
        if res:
            self.log.append((self.clock(), 'res', bytes(res)))

    def execute(self, c):
        o = c[0] & 0x1F
        if o == 0x03:                       # specify
            self.srt, self.hut = c[1] >> 4, c[1] & 15
            self.hlt, self.nd = c[2] >> 1, c[2] & 1
            self.set_result([])
        elif o == 0x04:                     # sense drive status
            d, hd = c[1] & 3, (c[1] >> 2) & 1
            st3 = 0x20 | 0x08 | (0x10 if self.pcn[d] == 0 else 0) | hd << 2 | d
            self.set_result([st3])
        elif o == 0x07:                     # recalibrate: step out to track 0
            d = c[1] & 3
            self.start_seek(d, 0, 0)
        elif o == 0x0F:                     # seek
            d, hd = c[1] & 3, (c[1] >> 2) & 1
            self.start_seek(d, hd, c[2])
        elif o == 0x08:                     # sense interrupt status
            t = self.clock()
            k = next((i for i, e in enumerate(self.int_pending) if e[0] <= t), None)
            if k is not None:
                _, st0, pcn = self.int_pending.pop(k)
                self.set_result([st0, pcn])
            else:
                self.set_result([0x80])     # no interrupt yet: 'invalid command'
        elif o == 0x0A:                     # read ID: the next sector to come round
            d, hd = c[1] & 3, (c[1] >> 2) & 1
            trk = self.disc.track(self.pcn[d], hd)
            if not trk:
                self.set_result([0x40 | hd << 2 | d, 0x01, 0x00, 0, 0, 0, 0])
                return
            k = self.next_sector_index(trk, self.disc.gap3(self.pcn[d], hd))
            s = trk[k]
            self.set_result([hd << 2 | d, 0, 0, s.c, s.h, s.r, s.n])
        elif o == 0x06:                     # read data
            self.read(c)
        else:
            self.set_result([0x80])

    def start_seek(self, d, hd, ncn):
        """step pulses SRT apart, Seek End after the last (UNVERIFIED: one SRT a step)"""
        steps = abs(ncn - self.pcn[d])
        step_t = (16 - self.srt) * 2000 * T_US if self.seek_timed else 0
        self.pcn[d] = ncn
        self.int_pending.append((self.clock() + steps * step_t, 0x20 | hd << 2 | d, ncn))
        self.set_result([])

    @staticmethod
    def layout(trk, gap3):
        """byte offsets in the turn of each sector's ID address mark and first data byte: the 765's
        format (GAP4a 80, sync 12, IAM 4, GAP1 50; per sector sync 12, IDAM 4, ID 4, CRC 2, GAP2 22,
        sync 12, DAM 4, data, CRC 2, GAP3), GAP3 cut so the track fits a turn"""
        n = len(trk)
        size = len(trk[0].data) if trk else 512
        pitch = min(62 + size + gap3, (TURN_BYTES - TRACK_HEAD) // max(n, 1))
        return [(TRACK_HEAD + pitch * k + 12, TRACK_HEAD + pitch * k + 60) for k in range(n)], pitch

    def next_sector_index(self, trk, gap3):
        pos = ((self.clock() + self.index_phase_t) % self.turn_t) // BYTE_T
        ids = [i for i, _ in self.layout(trk, gap3)[0]]
        for k, i in enumerate(ids):
            if i >= pos:
                return k
        return 0

    def read(self, c):
        d, hd = c[1] & 3, (c[1] >> 2) & 1
        C, H, R, N, EOT = c[2], c[3], c[4], c[5], c[6]
        trk = self.disc.track(self.pcn[d], hd)
        n = len(trk)
        data = b''
        r = R
        first_k = None
        rs = []
        while True:
            k = next((i for i, s in enumerate(trk) if (s.c, s.h, s.r, s.n) == (C, H, r, N)), None)
            if k is None:
                if not data:
                    self.set_result([0x40 | hd << 2 | d, 0x04, 0x00, C, H, r, N])   # no data
                    return
                break
            if first_k is None:
                first_k = k
            data += trk[k].data
            rs.append(r)
            if r == EOT:
                break
            r += 1
        # wait for the first sector's ID to come under the head (missed: a turn later), then its data
        t = self.clock()
        pos_t = (t + self.index_phase_t) % self.turn_t
        lay, pitch = self.layout(trk, self.disc.gap3(self.pcn[d], hd))
        if self.ids_needed:
            id_t, data_t = lay[first_k][0] * BYTE_T, lay[first_k][1] * BYTE_T
            self.next_byte_t = t + (id_t - pos_t) % self.turn_t + (data_t - id_t)
        else:                               # the pre-fix model: data at k * 6250 / n + 62
            start = (first_k * TURN_BYTES // n + 62) * BYTE_T
            self.next_byte_t = t + (start - pos_t) % self.turn_t
        self.exec_gap = (pitch - len(trk[first_k].data)) * BYTE_T
        self.exec_bytes = data
        self.exec_i = 0
        self.exec_r, self.exec_len = rs, len(trk[first_k].data)
        self.ovr_seen = -1
        self.exec_result = [0x40 | hd << 2 | d, 0x80, 0x00, C, H, r, N]
        self.phase = 'exec'


if __name__ == '__main__':
    print(__doc__)
