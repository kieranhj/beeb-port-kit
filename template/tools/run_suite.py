#!/usr/bin/env python3
"""run_suite.py -- run every line verify_cmds.py prints, N at a time; the verdict is the exit code.

beeb-port-kit template, MIT, Kieran Connell 2026. From 1942's tools/run_suite.py (41 lines),
which ran its 148-line suite ten at a time from 2026-09-29 to v1.0. The jsbeeb-version axis is
from the phX port, 2026-11 (its tools/b7_suite.sh, run on the pin and on jsbeeb's main).

    python tools/run_suite.py OUT_DIR [N] [--jsbeeb NAME=SRC ...] [--only REGEX]   N defaults to 4

--only REGEX runs the lines whose command matches (a re.search on the argv joined by spaces):
a part of the suite, by tool or by build. The summary says how many were left out.

BUILD FIRST, AND DO NOT REBUILD WHILE IT RUNS: every line reads the build's disc and symbol
dump, and a rebuild under a running suite scores half of it on one build and half on another.

OUT_DIR MUST BE ABSOLUTE AND OUTSIDE THE REPO - a scratch or temp directory (1942's rule: never
the home folder either). One file a line, NNN.out, the command on its first line and everything
it printed after; summary.txt with every line's verdict and time.

PASS/FAIL IS THE EXIT CODE ONLY, against the line's `expect` (0, or 1 for a negative control).
Grepping the outputs for "pass" matches field names and lies (1942 BUGS.md #9).

The environment each line wants is passed AS A DICT - no shell, no Git bash, no `A=B node`
parsing - so the same suite runs from PowerShell, cmd or a POSIX shell. 1942's needed Git's
bash.exe at a fixed path for its `A=B node ...` lines.

IF (NEARLY) EVERY LINE FAILS AT ONCE, SUSPECT THE TOOLS before the port. 1942 lost a suite at a time to a
new Baron listing layout (BUGS.md #26) and to jsbeeb 2.x's key API change, each of which failed
every oracle identically on a good build. This says so when it happens.

TWO (OR MORE) JSBEEB. `--jsbeeb NAME=SRC` (repeatable; or RUN_SUITE_JSBEEB="NAME=SRC;NAME=SRC")
runs the whole suite once per version: SRC a jsbeeb checkout's src/ (set as JSBEEB_SRC for every
line), or empty - `--jsbeeb pin=` - for the jsbeeb the MCP pins (JSBEEB_SRC removed). Each line
also gets JSBEEB_NAME=NAME, which jsbeeb_src.mjs appends to the version every report line
carries. Outputs go to OUT_DIR/NAME/; the summary lists each version, and then every line whose
verdict DIFFERS between versions - each one a fact about the emulator to explain in the port's
BUGS.md (phX: the pin has no MA13 flip; main moves palette writes half a cycle early, as a real
Master does). A line in verify_cmds.py's JSON may carry:
    "jsbeeb": {"main": {"argv": [...], "env": {...}, "expect": 1}, "pin": {"skip": true}}
        what changes for that version (an expected file per version - phX's sine and Multi-FX
        pictures had one each - or a different verdict), merged over the line
    "{jsbeeb}" anywhere in argv or env values: replaced by NAME (work/expected_{jsbeeb}.bin)
Without --jsbeeb nothing of this applies and the outputs are OUT_DIR/NNN.out, as before.
"""
import concurrent.futures as cf
import json
import os
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def repo_top():
    try:
        r = subprocess.run(["git", "rev-parse", "--show-toplevel"], cwd=ROOT,
                           capture_output=True, text=True)
        if r.returncode == 0 and r.stdout.strip():
            return os.path.normcase(os.path.abspath(r.stdout.strip()))
    except OSError:
        pass
    return os.path.normcase(ROOT)


def parse_args(argv):
    pos, versions, only = [], [], None
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--only" and i + 1 < len(argv):
            only = argv[i + 1]; i += 2; continue
        if a.startswith("--only="):
            only = a.split("=", 1)[1]; i += 1; continue
        if a == "--jsbeeb" and i + 1 < len(argv):
            versions.append(argv[i + 1]); i += 2; continue
        if a.startswith("--jsbeeb="):
            versions.append(a.split("=", 1)[1]); i += 1; continue
        pos.append(a); i += 1
    if not versions and os.environ.get("RUN_SUITE_JSBEEB"):
        versions = [v for v in os.environ["RUN_SUITE_JSBEEB"].split(";") if v.strip()]
    out = []
    for v in versions:
        name, _, src = v.partition("=")
        name = name.strip()
        if not name or not name.replace("-", "").replace("_", "").isalnum():
            sys.exit("run_suite: --jsbeeb %s: NAME=SRC, NAME letters, digits, - and _" % v)
        src = src.strip()
        if src and not os.path.exists(os.path.join(src, "machine-session.js")):
            sys.exit("run_suite: --jsbeeb %s: %s has no machine-session.js (it must be a jsbeeb src/)" % (name, src))
        out.append((name, src))
    if len({n for n, _ in out}) != len(out):
        sys.exit("run_suite: two --jsbeeb versions with one NAME")
    return pos, out, only


def for_version(line, name, src):
    """The line as it runs on one jsbeeb: its overrides merged, {jsbeeb} substituted, the env set.
    None when the version skips it."""
    l = dict(line)
    over = (line.get("jsbeeb") or {}).get(name) or {}
    if over.get("skip"):
        return None
    for k in ("argv", "expect", "why"):
        if k in over:
            l[k] = over[k]
    env = dict(line.get("env") or {}, **(over.get("env") or {}))
    sub = lambda s: s.replace("{jsbeeb}", name) if isinstance(s, str) else s
    l["argv"] = [sub(a) for a in l["argv"]]
    l["env"] = {k: sub(v) for k, v in env.items()}
    l["env"]["JSBEEB_NAME"] = name
    if src:
        l["env"]["JSBEEB_SRC"] = src
    l["unset"] = [] if src else ["JSBEEB_SRC"]
    return l


def run_set(lines, out, n, label=""):
    """Run `lines` n at a time, NNN.out each in `out`; returns [(i, rc, dt, shown)] by line."""
    os.makedirs(out, exist_ok=True)

    def run(i, line):
        t = time.time()
        env = dict(os.environ, **line["env"])
        for k in line.get("unset", []):
            env.pop(k, None)
        shown = " ".join(["%s=%s" % kv for kv in line["env"].items() if kv[0] != "JSBEEB_NAME"] + line["argv"])
        with open(os.path.join(out, "%03d.out" % i), "w", encoding="utf-8") as f:
            f.write(shown + "\n# " + line["why"] + "\n")
            f.flush()
            try:
                rc = subprocess.run(line["argv"], cwd=ROOT, env=env, stdout=f,
                                    stderr=subprocess.STDOUT).returncode
            except OSError as e:
                f.write("run_suite: could not start: %s\n" % e)
                rc = 127
        return i, rc, time.time() - t, shown

    res = []
    todo = [(i, l) for i, l in enumerate(lines) if l is not None]
    with cf.ThreadPoolExecutor(n) as ex:
        for got in ex.map(lambda a: run(*a), todo):
            res.append(got)
            i, rc, dt, shown = got
            ok = rc == lines[i]["expect"]
            print("%s%s %03d rc=%d %6.1fs  %s" % (label, "pass" if ok else "FAIL", i, rc, dt, shown), flush=True)
    return res


def summarise(lines, res, n, t0):
    bad = [g for g in res if g[1] != lines[g[0]]["expect"]]
    s = "%d lines, %d passed, %d failed, %.0fs wall, %d at a time\n" % (
        len(res), len(res) - len(bad), len(bad), time.time() - t0, n)
    if len(bad) > 1 and len(bad) >= 0.8 * len(res):
        s += ("NEARLY EVERY LINE FAILED: suspect the TOOLS (jsbeeb, the listing/dump format, the "
              "build) before the port - read 000.out first\n")
    for i, rc, dt, shown in res:
        s += "%s %03d rc=%d want=%d %6.1fs  %s\n" % (
            "pass" if rc == lines[i]["expect"] else "FAIL", i, rc, lines[i]["expect"], dt, shown)
    return s, bad


def main():
    pos, versions, only = parse_args(sys.argv[1:])
    if not pos:
        sys.exit(__doc__)
    out = pos[0]
    n = int(pos[1]) if len(pos) > 1 else 4
    if not os.path.isabs(out):
        sys.exit("run_suite: OUT_DIR must be absolute: %s" % out)
    top = repo_top()
    o = os.path.normcase(os.path.abspath(out))
    if o == top or o.startswith(top + os.sep):
        sys.exit("run_suite: OUT_DIR %s is inside the repo (%s): use a scratch directory" % (out, top))

    r = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "verify_cmds.py"), "--json"],
                       cwd=ROOT, capture_output=True, text=True)
    sys.stderr.write(r.stderr)
    if r.returncode:
        sys.exit("run_suite: verify_cmds.py failed (%d)" % r.returncode)
    lines = [json.loads(l) for l in r.stdout.splitlines() if l.strip()]
    if not lines:
        sys.exit("run_suite: verify_cmds.py printed no lines -- is anything built?")
    if only:
        import re
        kept = [l for l in lines if re.search(only, " ".join(l["argv"]))]
        print("run_suite: --only %s: %d of %d lines" % (only, len(kept), len(lines)), flush=True)
        lines = kept
        if not lines:
            sys.exit("run_suite: --only %s matches no line" % only)
    os.makedirs(out, exist_ok=True)

    t0 = time.time()
    if not versions:
        res = run_set(lines, out, n)
        text, bad = summarise(lines, res, n, t0)
        with open(os.path.join(out, "summary.txt"), "w", encoding="utf-8") as f:
            f.write(text)
        print(text)
        sys.exit(1 if bad else 0)

    # the version axis: the whole suite once per jsbeeb, one after the other (not interleaved:
    # two jsbeeb in one batch would halve the parallelism each version's timings were taken at)
    per, text, anybad = {}, "", False
    for name, src in versions:
        vl = [for_version(l, name, src) for l in lines]
        tv = time.time()
        res = run_set(vl, os.path.join(out, name), n, label="[%s] " % name)
        t, bad = summarise(vl, res, n, tv)
        per[name] = {i: (rc, vl[i]["expect"]) for i, rc, _, _ in res}
        anybad = anybad or bool(bad)
        with open(os.path.join(out, name, "summary.txt"), "w", encoding="utf-8") as f:
            f.write(t)
        text += "== jsbeeb %s (%s)\n%s\n" % (name, src or "the MCP's pin", t)
    names = [nm for nm, _ in versions]
    differ = []
    for i, l in enumerate(lines):
        got = {nm: per[nm].get(i) for nm in names}
        rcs = {nm: g[0] for nm, g in got.items() if g is not None}
        if len(set(rcs.values())) > 1:
            differ.append("%03d %s  %s" % (i, " ".join("%s=%d" % kv for kv in rcs.items()), " ".join(l["argv"])))
    text += "== %d lines whose exit differs between %s%s\n%s\n" % (
        len(differ), ", ".join(names), " (each a fact about the emulator: BUGS.md)" if differ else "",
        "\n".join(differ))
    with open(os.path.join(out, "summary.txt"), "w", encoding="utf-8") as f:
        f.write("%.0fs wall\n%s" % (time.time() - t0, text))
    print(text)
    sys.exit(1 if anybad else 0)


if __name__ == "__main__":
    main()
