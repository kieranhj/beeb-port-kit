#!/usr/bin/env python3
"""check_vscroll.py -- replay a recorded vscroll run through a model of the SPEC.

beeb-port-kit template example, MIT, Kieran Connell 2026. The model half of
record_vscroll.mjs (which runs this and exits with its verdict), after 1942's
check_turner.py: the harness records what the port did, this says what it should
have done, and the two never share code.

THE MODEL IS WRITTEN FROM THE SPEC, NOT FROM THE 6502. main.6502 wraps `ypos` with a
`cmp #BUF_ROWS * 8` and a reload; this says "one scanline a held key a pass, round a
ring of BUF_ROWS * 8 lines" as modular arithmetic. main.6502 takes the CRTC address
off two tables; this computes (BUF_BASE + row * ROW_BYTES) / 8. The adjust pair is
"sums to 8", not a lookup. A model that transcribes the code under test agrees with
its bugs (1942 BUGS.md #16, #45, #91: oracles that shared the port's table, its
arithmetic or its substitute, and scored zero on a wrong port). Only the geometry
constants come from the build, through the trace.

RE-SEEDED EVERY PASS: each step starts from the `ypos` the PORT had at the top of
that pass, so one wrong step is one wrong pass, not every pass after it.

    python check_vscroll.py TRACE.json

Exit 0: every judged event agreed AND every path below was taken. Exit 1 otherwise.
Exit 2: the trace is unreadable. One line of JSON last; a few wrong events first.
"""
import json
import sys


def main():
    if len(sys.argv) != 2:
        print("usage: check_vscroll.py TRACE.json", file=sys.stderr)
        return 2
    try:
        with open(sys.argv[1]) as f:
            tr = json.load(f)
        spec, events = tr["spec"], tr["events"]
    except (OSError, ValueError, KeyError) as e:
        print("check_vscroll: cannot read %s: %s" % (sys.argv[1], e), file=sys.stderr)
        return 2

    ring = spec["BUF_ROWS"] * 8                 # scanlines round the ring

    def crtc_of(y):
        a = (spec["BUF_BASE"] + (y // 8) * spec["ROW_BYTES"]) // 8
        return a >> 8, a & 0xFF                 # R12, R13

    judged, wrong, shown = 0, 0, []
    excluded = {}
    cover = {"idle": 0, "down": 0, "up": 0, "both": 0, "wrapDown": 0, "wrapUp": 0, "takes": 0}
    lines = set()

    def bad(i, what, got, want):
        nonlocal wrong
        wrong += 1
        if len(shown) < 8:
            shown.append({"event": i, "what": what, "got": got, "want": want})

    def exclude(why):
        excluded[why] = excluded.get(why, 0) + 1

    want_park = None        # the model's answer for the pass in flight
    pass_in = None
    last_park = None        # the port's ypos at the end of the last pass
    parked = None           # parked, not yet taken
    live = None             # what the CRTC is being given this field
    for i, e in enumerate(events):
        t = e["t"]
        if t == "pass":
            if last_park is not None:           # nothing else may write ypos
                judged += 1
                if e["y"] != last_park:
                    bad(i, "ypos changed between passes", e["y"], last_park)
            pass_in = e
            want_park = (e["y"] - e["up"] + e["down"]) % ring
            key = "both" if e["up"] and e["down"] else "up" if e["up"] else "down" if e["down"] else "idle"
            cover[key] += 1
        elif t == "park":
            if want_park is None:
                exclude("a park with no pass before it (the recording's first)")
                continue
            judged += 1
            if e["y"] != want_park:
                bad(i, "the pass's move", e["y"], want_park)
            if pass_in["down"] and not pass_in["up"] and pass_in["y"] == ring - 1 and e["y"] == 0:
                cover["wrapDown"] += 1
            if pass_in["up"] and not pass_in["down"] and pass_in["y"] == 0 and e["y"] == ring - 1:
                cover["wrapUp"] += 1
            last_park = parked = e["y"]
            want_park = None
        elif t == "field":
            if parked is not None:              # the take: all four bytes at once
                live, parked = parked, None
                cover["takes"] += 1
                lines.add(live % 8)
        elif t == "crtc":
            r, v, by = e["r"], e["v"], e["by"]
            if (by, r) not in (("vsync", 5), ("vsync", 12), ("vsync", 13), ("timer", 5)):
                continue                        # not a register this model speaks for
            if live is None:
                exclude("before the first take: the CRTC holds the boot's values")
                continue
            hi, lo = crtc_of(live)
            line = live % 8
            want = {("vsync", 5): 8 - line, ("vsync", 12): hi, ("vsync", 13): lo, ("timer", 5): line}[(by, r)]
            judged += 1
            if v != want:
                bad(i, "R%d by the %s handler, ypos %d" % (r, by, live), v, want)

    need = {"idle": 5, "down": 100, "up": 100, "both": 3, "wrapDown": 1, "wrapUp": 1, "takes": 200}
    gaps = ["%s: %d of %d" % (k, cover[k], n) for k, n in need.items() if cover[k] < n]
    if len(lines) != 8:
        gaps.append("lines taken: %s of all eight" % sorted(lines))
    for s in shown:
        print("WRONG", json.dumps(s), file=sys.stderr)
    for g in gaps:
        print("NEVER EXERCISED", g, file=sys.stderr)
    ok = wrong == 0 and judged > 0 and not gaps
    print(json.dumps({"judged": judged, "wrong": wrong, "firstWrong": shown, "excluded": excluded,
                      "coverage": cover, "lines": sorted(lines), "neverExercised": gaps,
                      "mutate": tr.get("mutate"), "pass": ok}))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
