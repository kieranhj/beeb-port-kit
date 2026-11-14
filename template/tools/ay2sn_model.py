"""src/lib/ay2sn.6502 in Python: the SN76489 bytes ay2sn sends for each frame's AY registers.

A line-for-line model of the 6502 (forked from Unspoken's: the CPC's 1 MHz AY, N = 2P, the
software bass only, no envelope), so tools/verify_music.py can say what the build should
have written. It models ay2sn's own writes and the bass voice's parameters; the bass
interrupt's toggles are checked separately (by timing), not here.

    m = Ay2sn()                 # the state after ay2sn_silence
    writes = m.call(regs)       # regs: 14 ints, R0..R13; returns the bytes in order
    m.bass_chan, m.bass_n, m.bass_on, m.bass_off, m.bass_running
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import make_ay2sn_tables as T  # noqa: E402

YM_SN_VOL = T.ym_sn_vol()
NOISE_RATE = T.ay_noise_rate()
AY_VOL5 = [0, 3, 4, 7, 8, 11, 12, 15, 16, 19, 20, 23, 24, 27, 28, 31]
SN_TONE_LATCH = [0x80, 0xA0, 0xC0]
SN_VOL_LATCH = [0x90, 0xB0, 0xD0]
NOISE_BIT = [8, 16, 32]
TONE_BIT = [1, 2, 4]


class Ay2sn:
    def __init__(self):
        # ay2sn_silence: sn_forget, bass_stop (bass_last low byte := &FF, bass_prev := &FF),
        # bass_timer_off; music_init zeroed env_phase and noise_last first.
        self.cache_t0 = [0] * 3
        self.cache_t1 = [0] * 3
        self.cache_v = [0] * 4
        self.noise_last = 0
        self.bass_prev = 0xFF
        self.bass_last = 0x00FF
        self.bass_running = 0
        self.bass_n = 0
        self.bass_on = 0
        self.bass_off = 0
        self.bass_chan = 0xFF
        self.out = []

    def write(self, b):
        self.out.append(b)

    def bass_pick(self, r):
        mask = 0
        for x in (2, 1, 0):
            if r[8 + x] & 31 == 0 or r[7] & TONE_BIT[x]:
                continue
            p = (r[2 * x + 1] & 15) << 8 | r[2 * x]
            if p >= 0x200:
                mask |= 1 << x
        if not mask:
            return 0xFF
        if self.bass_prev < 0x80 and mask & (1 << self.bass_prev):
            return self.bass_prev
        for x in range(3):
            if mask & (1 << x):
                return x

    def call(self, r):
        self.out = []
        noise_att = 15
        self.bass_chan = 0xFF
        bass_skip = 0xFF
        bass_want = self.bass_pick(r)
        t0, t1, v = [0] * 3, [0] * 3, [0] * 3
        for x in range(3):
            vol = r[8 + x]
            v5 = AY_VOL5[vol & 15]
            att = YM_SN_VOL[v5]
            if not r[7] & NOISE_BIT[x] and att < noise_att:
                noise_att = att
            if r[7] & TONE_BIT[x]:
                att = 15
            snper = ((r[2 * x + 1] & 15) << 8 | r[2 * x]) * 2
            if snper >= 1024 and x == bass_want:
                # bass_claim
                self.bass_chan = x
                bass_skip = x
                self.bass_n = (4 * snper - 2) & 0xFFFF
                self.bass_on = SN_VOL_LATCH[x] | att
                self.bass_off = SN_VOL_LATCH[x] | 15
                snper = 1
            while snper >= 1024:
                snper >>= 1
            if snper == 0:
                snper = 1
            t0[x] = (snper & 15) | SN_TONE_LATCH[x]
            v[x] = att | SN_VOL_LATCH[x]
            t1[x] = ((snper >> 8) << 4) | ((snper & 0xFF) >> 4)
        for x in range(3):                                   # sn_chan
            if t0[x] != self.cache_t0[x] or t1[x] != self.cache_t1[x]:
                self.cache_t0[x] = t0[x]
                self.write(t0[x])
                self.cache_t1[x] = t1[x]
                self.write(t1[x])
            if x == bass_skip:
                self.cache_v[x] = 0
            elif v[x] != self.cache_v[x]:
                self.cache_v[x] = v[x]
                self.write(v[x])
        if r[7] & 0x38 == 0x38:                              # no noise
            self.vol3(0xFF)
        else:
            nb = NOISE_RATE[r[6] & 31] | 0xE4
            if nb != self.noise_last:
                self.noise_last = nb
                self.write(nb)
            self.vol3(noise_att | 0xF0)
        # bass_update
        self.bass_prev = self.bass_chan
        if self.bass_chan & 0x80:
            self.bass_last = (self.bass_last & 0xFF00) | 0xFF   # bass_stop: low byte only
            self.bass_prev = 0xFF
            self.bass_running = 0
        else:
            if self.bass_n != self.bass_last:
                self.bass_last = self.bass_n
            if not self.bass_running:
                self.bass_running = 1
        return self.out

    def vol3(self, b):
        if b != self.cache_v[3]:
            self.cache_v[3] = b
            self.write(b)
