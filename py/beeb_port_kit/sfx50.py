"""
sfx50.py - sound effects fitted as 50 Hz ramps for lib/sfx50.6502, from the MOS's own
playing of them.

    python -m beeb_port_kit.sfx50 CAPTURE.json OUT.6502 [--effects EFFECTS.json] [--show]

WHY. A game that owns IRQ1V (lib/irq.6502) stops the MOS's 100 Hz tick, and its SOUND and
ENVELOPE driver with it. lib/sfx50.6502 is the replacement: each effect a list of ramps, over
N fields the channel's period and amplitude stepping linearly. This fits the ramps to what the
MOS really played - the SN76489 writes captured by template/tools/sfxcapture.mjs, by MOS
centisecond tick from the SOUND call - so the effect is the original's, measured, not
re-composed by ear.

HOW. Per effect: the writes are replayed on the effect's own chip channel and sampled once a
field (after ticks 1, 3, 5 ...); the samples are trimmed to where the channel goes silent for
good (a silent tone - a sweep that only sets the pitch of noise mode 3, which takes tone 2's
period - is kept for MAX_FIELDS); then split greedily into ramps, each as long as every field
it covers is within tolerance (period: 3% or 2, whichever is more; amplitude: 1 step), each
starting from its own sampled values so errors never build up. The noise channel's control
may not change inside a ramp.

THE CAPTURE (sfxcapture.mjs writes it):
    {"effects": [{"name": NAME, "chip_channel": C, "what": "...", "writes": [[tick, byte], ...]}, ...]}
in the order the effects are numbered (request E + 1 starts effect E); an object keyed by NAME
is read in its file order too (but a JavaScript object puts integer-like keys first, so a
writer keeps a list). NAME is the label's
suffix (sfx_effect_NAME). The older form, {"effects": {"KEY": [[tick, byte], ...]}} (Stryker's
Run's tools/sfx-mos320.json), takes --effects EFFECTS.json for the rest:
    [{"key": "0", "name": "00", "sound_channel": 16, "what": "..."}, ...]
(sound_channel is the SOUND block's channel word's low byte: chip_channel() maps it).

THE LAST FIELD. lib/sfx50.6502 silences a channel in the tick that outputs its last field, so
each effect sounds one field (20 ms) shorter than its ramps; Stryker's Run shipped so (its
effects are the default here, byte for byte). --pad-end adds a field to each last ramp, so the
field cut is one past the MOS's (lib/test/sfx50_test.mjs measures both).

THE OUTPUT: per effect a label and its ramps, 6 bytes each (lib/sfx50.6502's header has the
layout), then sfx_effect_channel (each effect's chip channel: for the game's request code; the
driver does not read it), sfx_effect_lo and sfx_effect_hi.

From Stryker's Run (Enhanced), tools/sfx50.py (decision 25, docs/step2-layer3.md), 2026-10-16;
into the kit 2026-10-25 with its effects table moved into the capture (or --effects) and the
game's own extra effects (an IF GAMEPLAY_SHIELD block of hand-written ones) left out. Measured
there: the game's 8 effects in 158 bytes; within a step or two of the MOS's period and
amplitude field for field, sometimes half a field apart. Proved here (py/tests/test_sfx50.py,
2026-10-25): from that game's capture this writes every ramp of its generated sfx_data.6502
byte for byte. Fork this into your project's tools/; keep this header.
"""
import argparse
import json
import sys
from pathlib import Path

MAX_FIELDS = 24             # a silent sweep is only heard through the noise it drives
BS = chr(92)


def chip_channel(sound_channel):
    """SOUND's channel (its low two bits) to the chip's: SOUND 0, the noise, is chip channel 3;
    SOUND 1-3 are tones 2-0 (the MOS's order)."""
    return 3 if sound_channel & 3 == 0 else 3 - (sound_channel & 3)


def samples(writes, ch):
    """The channel's (period or noise control, amplitude 0-15) once a field: after ticks 1, 3, 5..."""
    period, att, latch, out, k = 0x3FF if ch < 3 else 0, 15, None, [], 0
    last = max([t for t, _ in writes] + [0])
    for t in range(last + 2):
        while k < len(writes) and writes[k][0] == t:
            v = writes[k][1]
            k += 1
            if v & 0x80:
                c, vol = (v >> 5) & 3, v & 0x10
                latch = (c, vol)
                if c != ch:
                    continue
                if vol:
                    att = v & 15
                elif ch == 3:
                    period = v & 7
                else:
                    period = (period & 0x3F0) | (v & 15)
            elif latch == (ch, 0) and ch < 3:
                period = (period & 15) | ((v & 63) << 4)
        if t % 2 == 1:
            out.append((period, 15 - att))
    return out


def trim(s, max_fields=MAX_FIELDS):
    """Up to where the channel goes silent for good; a silent sweep, max_fields."""
    if all(a == 0 for _, a in s):
        return s[:max_fields]
    end = max(i for i, (_, a) in enumerate(s) if a > 0) + 1
    return s[:end]


def fits(s, i, j, noise):
    """Does one ramp from field i through j (inclusive) cover every field within tolerance?
    (period step, amplitude step in sixteenths), or None."""
    n = j - i
    p0, a0 = s[i]
    dp = round((s[j][0] - p0) / n) if n else 0
    dv = round(16 * (s[j][1] - a0) / n) if n else 0
    if not -128 <= dp <= 127 or not -128 <= dv <= 127:
        return None
    for k in range(i, j + 1):
        p, a = s[k]
        pp = p0 + dp * (k - i)
        aa = (a0 * 16 + 8 + dv * (k - i)) >> 4
        if noise and p != p0:
            return None
        if abs(pp - p) > max(2, 0.03 * p) or abs(aa - a) > 1:
            return None
    return dp, dv


def ramps(s, noise):
    """The samples as ramps: (fields, period, period step, amplitude, amplitude step)."""
    out, i = [], 0
    while i < len(s):
        j, best = i, (0, 0)
        while j + 1 < len(s) and j + 1 - i < 255:
            r = fits(s, i, j + 1, noise)
            if r is None:
                break
            j, best = j + 1, r
        out.append((j - i + 1, s[i][0], best[0], s[i][1], best[1]))
        i = j + 1
    return out


def play(rs):
    """What the ramps play, field by field, as lib/sfx50.6502 steps them: (period, amplitude).
    The amplitude byte is clamped as the driver clamps it: below 0 to 0, past &FF to &F8."""
    got = []
    for n, p, dp, a, dv in rs:
        v = a * 16 + 8
        for k in range(n):
            got.append(((p + dp * k) & 0xFFFF, v >> 4))
            if dv:
                v += dv
                v = 0 if v < 0 else 0xF8 if v > 0xFF else v
    return got


def fit(writes, ch, max_fields=MAX_FIELDS, pad_end=False):
    """(the trimmed samples, their ramps) for one effect's writes on chip channel ch.
    pad_end: one more field on the last ramp. lib/sfx50.6502 silences a channel in the same
    tick that outputs its last field, so that field sounds for microseconds, not 20 ms (an
    effect is a field short); padding makes the last fitted field the one cut."""
    s = trim(samples(writes, ch), max_fields)
    rs = ramps(s, ch == 3)
    if pad_end and rs:
        n, p, dp, a, dv = rs[-1]
        if n < 255:
            rs[-1] = (n + 1, p, dp, a, dv)
        else:
            pp, aa = play([rs[-1]])[-1]
            rs.append((1, pp, 0, aa, 0))
    return s, rs


def ramp_bytes(rs):
    """The ramps as the driver reads them, with the ending 0."""
    out = []
    for n, p, dp, a, dv in rs:
        out += [n, p & 255, p >> 8, dp & 255, a * 16 + 8, dv & 255]
    return bytes(out + [0])


def load(capture, effects_config=None):
    """[(name, chip channel, what, writes)] in request order, from either capture form."""
    eff = json.loads(Path(capture).read_text())["effects"]
    if effects_config:
        cfg = json.loads(Path(effects_config).read_text())
        return [(e["name"], e.get("chip_channel", chip_channel(e.get("sound_channel", 0))),
                 e.get("what", ""), eff[e["key"]] if isinstance(eff[e["key"]], list) else eff[e["key"]]["writes"])
                for e in cfg]
    out = []
    items = [(e["name"], e) for e in eff] if isinstance(eff, list) else eff.items()
    for name, e in items:
        if isinstance(e, list):
            raise SystemExit("%s: effect %r has no channel - give --effects (the older capture form)"
                             % (capture, name))
        ch = e["chip_channel"] if "chip_channel" in e else chip_channel(e["sound"][0])
        out.append((name, ch, e.get("what", ""), e["writes"]))
    return out


def render(effects, source_name, out_name, show=False, pad_end=False):
    """The data file's text, and its size in bytes."""
    c = BS + " "
    lines = [c + out_name + " - GENERATED by beeb_port_kit/sfx50.py from " + source_name + "; do not edit.",
             c + "Sound effects as 50 Hz ramps for lib/sfx50.6502, fitted to the MOS's own playing",
             c + "of each (template/tools/sfxcapture.mjs).",
             c + "Each ramp: fields, period (low, high), period step, amplitude * 16 + 8, amplitude step."]
    total = 0
    for name, ch, what, writes in effects:
        s, rs = fit(writes, ch, pad_end=pad_end)
        total += 6 * len(rs) + 1
        lines.append("")
        lines.append(f".sfx_effect_{name}{' ' * 20}{c}{what}: chip channel {ch}, {len(s)} fields")
        for n, p, dp, a, dv in rs:
            lines.append(f"    EQUB {n}, &{p & 255:02X}, &{p >> 8:02X}, {dp & 255}, &{a * 16 + 8:02X}, {dv & 255}"
                         f"{' ' * 4}{c}period {p} {dp:+d}, amplitude {a} {dv / 16:+.2f}")
        lines.append("    EQUB 0")
        if show:
            got = play(rs)
            print(f"{name} ch {ch}: {len(rs)} ramps for {len(s)} fields")
            print("  MOS:   " + " ".join(f"{p}/{a}" for p, a in s[:40]))
            print("  ramps: " + " ".join(f"{p}/{a}" for p, a in got[:40]))
    lines.append("")
    lines.append(".sfx_effect_channel" + " " * 16 + c + "each effect's chip channel (0-2 tone, 3 noise): sfx_request + this")
    lines.append("    EQUB " + ", ".join(str(ch) for _, ch, _, _ in effects))
    for half in ("lo", "hi"):
        lines.append(f".sfx_effect_{half}")
        lines.append("    EQUB " + ", ".join(f"{half.upper()}(sfx_effect_{name})" for name, _, _, _ in effects))
    lines.append(f"ASSERT HI(sfx_effect_{effects[0][0]}) >= &10   {c}lib/sfx50.6502's rule: no effect below &1000")
    return "\n".join(lines) + "\n", total + 3 * len(effects)


def main(argv=None):
    ap = argparse.ArgumentParser(description="50 Hz ramps for lib/sfx50.6502 from a MOS capture")
    ap.add_argument("capture")
    ap.add_argument("out")
    ap.add_argument("--effects", help="the effects' names and channels, for a capture without them")
    ap.add_argument("--show", action="store_true", help="each effect's ramps against the MOS, field by field")
    ap.add_argument("--pad-end", action="store_true",
                    help="one more field on each effect's last ramp, so the driver's end cuts that one (fit())")
    a = ap.parse_args(argv)
    effects = load(a.capture, a.effects)
    text, size = render(effects, Path(a.capture).name, Path(a.out).name, a.show, a.pad_end)
    with open(a.out, "w", newline="\n") as f:
        f.write(text)
    print(f"wrote {a.out}: {len(effects)} effects, {size} bytes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
