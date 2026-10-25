#!/usr/bin/env python3
"""verify_cmds.py -- print every oracle's command line, with THIS build's addresses.

beeb-port-kit template, MIT, Kieran Connell 2026. The skeleton of 1942's
tools/verify_cmds.py (578 lines by v1.0, 148 command lines on its suite build).

**BARON MOVES ZERO PAGE ON EVERY EDIT**, so an address written in a doc is a
measurement of nothing waiting to happen. 1942's CLAUDE.md carried a worked
verify_dynamic line; the sprite table moved, `frame_count` went &10 -> &12 and
`scroll` took &10, and the line reported 13,696 frames where the answer was 50. It
did not fail - it answered, in the right shape, wrongly. So nothing is written down:
this prints the lines from the symbol dump, and `zp()` refuses a name that is not
zero page, because a label of a similar name is the confusion that bit.

    python tools/verify_cmds.py            the lines, for a human (POSIX `A=B cmd` form)
    python tools/verify_cmds.py --json     the same, one JSON object a line, for run_suite.py:
                                           {"argv": [...], "env": {...}, "expect": 0, "why": "..."}

EVERY LINE SAYS WHY IT EXISTS. A run is worth what it covered, and two runs of one
oracle are two different checks (1942's verify_sprite runs three times: the recording's
load, the screen edges, and fire held - the third is the one BUGS.md #31 needed). Write
the reason beside the line, as the one-line comment `why`, so nobody deletes the run that
covers the case the others cannot.

`expect` is the exit code a PASS is: 0, except for a NEGATIVE CONTROL - the oracle run on
a deliberately broken input, which must exit 1. An oracle never seen failing has not been
shown able to.

A line is printed only for a build that exists; a missing build is said on stderr, not
skipped silently.
"""
import json
import os
import shlex
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import listing                                      # noqa: E402


class Build:
    """One build's symbols, from its --symbols dump."""

    def __init__(self, disc):
        self.disc = disc
        self.dump = disc[:-len(".ssd")] + ".symbols.json"
        self.ok = os.path.exists(os.path.join(ROOT, disc)) and os.path.exists(os.path.join(ROOT, self.dump))
        self.syms = listing.symbols(os.path.join(ROOT, self.dump)) if self.ok else {}

    def addr(self, name):
        hits = self.syms.get(name)
        if not hits:
            raise SystemExit("verify_cmds: no symbol `%s` in %s" % (name, self.dump))
        if len(hits) > 1:
            raise SystemExit("verify_cmds: `%s` has %d values in %s -- qualify it"
                             % (name, len(hits), self.dump))
        return hits[0]

    def zp(self, name):
        """A zero-page variable's address, as the harnesses want it: hex, two digits.
        Refuses anything above &FF -- `frame` the label is not `frame_count` the
        variable."""
        a = self.addr(name)
        if a > 0xFF:
            raise SystemExit("verify_cmds: `%s` is &%04X in %s, not zero page -- wrong symbol?"
                             % (name, a, self.dump))
        return "%02X" % a


def lines():
    out = []

    def add(why, argv, env=None, expect=0):
        out.append({"why": why, "argv": argv, "env": env or {}, "expect": expect})

    for disc, model in (("build/game.ssd", "B-DFS1.2"), ("build/game-master.ssd", "Master")):
        b = Build(disc)
        if not b.ok:
            print("verify_cmds: no %s (or its dump) -- build it to get its lines" % disc, file=sys.stderr)
            continue
        add("the build DOES what it did: fields 100, frames 50, idle 0, X 200, the panel "
            "unpacked - the gate for any change that moves addresses (%s)" % model,
            ["node", "tools/verify_dynamic.mjs", disc, b.zp("scroll"), b.zp("field_count"),
             b.zp("frame_count"), model])

        add("harness.mjs's helpers on a known answer: names from the dump, a key by its "
            "internal number, callFrom, the refusal of an unbanked hook, bank-aware names (%s)" % model,
            ["node", "tools/harness_selftest.mjs", disc])
        add("the A/B pair harness on the build against ITSELF: the same keys per pass, the "
            "state and the shown strip identical for 600 passes (%s)" % model,
            ["node", "tools/pairlock.mjs", "examples/pairlock/template.mjs", disc, disc,
             "--passes", "600", "--screen"])
        add("NEGATIVE CONTROL: the pair with step_left poked to 4 at pass 50 in the test "
            "machine must FAIL, at the first pass after it with LEFT held (%s)" % model,
            ["node", "tools/pairlock.mjs", "examples/pairlock/template.mjs", disc, disc,
             "--passes", "600", "--poke", "50:step_left=04"], expect=1)

    sh, ctl = Build("build/game-shift256.ssd"), Build("build/game-shift256end.ssd")
    if sh.ok and ctl.ok:
        add("the relocation proof: Game 256 bytes higher runs frame for frame like its padded "
            "control (build.ps1 -Shift 256 and -Shift 256 -ShiftEnd)",
            ["node", "tools/lockstep.mjs", "examples/pairlock/template.mjs", ctl.disc, sh.disc,
             "--frames", "1500"])
        add("the relocation proof by instruction: every PC mapped back through the labels, "
            "every strip write, for 1,000 fields",
            ["node", "tools/tracediff.mjs", "examples/pairlock/template.mjs", ctl.disc, sh.disc,
             "--max", "40000000"])
    else:
        print("verify_cmds: no build/game-shift256*.ssd -- build.ps1 -Shift 256 (and -ShiftEnd) "
              "for the relocation proof's lines", file=sys.stderr)

    vs = Build("examples/vscroll/build/vscroll.ssd")
    if vs.ok:
        add("the vertical scroll's PICTURE: the strip formula and the CRTC's view, 0 wrong at "
            "all eight sub-row phases, the sliver the adjust fetches, the 50 Hz rate",
            ["node", "examples/vscroll/tools/verify_vscroll.mjs", vs.disc,
             vs.zp("crtc_live"), vs.zp("line_live"), vs.zp("ypos")])
        add("the vertical scroll's LOGIC, record/replay: every pass and every CRTC write of a "
            "driven run against a Python model of the spec, both wraps covered",
            ["node", "examples/vscroll/tools/record_vscroll.mjs", vs.disc])
        add("NEGATIVE CONTROL: the same oracle on a poked adj_of_line must FAIL - an oracle "
            "never seen failing has not been shown able to",
            ["node", "examples/vscroll/tools/record_vscroll.mjs", vs.disc], {"MUTATE": "adj"}, expect=1)
    else:
        print("verify_cmds: no examples/vscroll build -- examples\\vscroll\\build.ps1 for its lines",
              file=sys.stderr)

    add("the floor-fit cost model recovers a known fixed + slope where a mean fit goes negative",
        ["node", "tools/floorfit.mjs", "--selftest"])
    add("tools/boards.mjs's Watford and Solidisk boards still work on this jsbeeb",
        ["node", "tools/boards_check.mjs"])
    return out


def main():
    want_json = "--json" in sys.argv[1:]
    ls = lines()
    if want_json:
        for l in ls:
            print(json.dumps(l))
        return
    print("# from the symbol dumps in build/ -- Baron moves these on every edit, so do not write them down")
    for l in ls:
        print("# " + l["why"] + (" [a PASS is exit %d]" % l["expect"] if l["expect"] else ""))
        env = " ".join("%s=%s" % (k, shlex.quote(v)) for k, v in l["env"].items())
        print((env + " " if env else "") + " ".join(shlex.quote(a) for a in l["argv"]))


if __name__ == "__main__":
    main()
