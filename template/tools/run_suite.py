#!/usr/bin/env python3
"""run_suite.py -- run every line verify_cmds.py prints, N at a time; the verdict is the exit code.

beeb-port-kit template, MIT, Kieran Connell 2026. From 1942's tools/run_suite.py (41 lines),
which ran its 148-line suite ten at a time from 2026-09-29 to v1.0.

    python tools/run_suite.py OUT_DIR [N]        N defaults to 4

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


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    out = sys.argv[1]
    n = int(sys.argv[2]) if len(sys.argv) > 2 else 4
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
    os.makedirs(out, exist_ok=True)

    def run(i, line):
        t = time.time()
        env = dict(os.environ, **line["env"])
        shown = " ".join(["%s=%s" % kv for kv in line["env"].items()] + line["argv"])
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

    t0 = time.time()
    res = []
    with cf.ThreadPoolExecutor(n) as ex:
        for got in ex.map(lambda a: run(*a), enumerate(lines)):
            res.append(got)
            i, rc, dt, shown = got
            ok = rc == lines[i]["expect"]
            print("%s %03d rc=%d %6.1fs  %s" % ("pass" if ok else "FAIL", i, rc, dt, shown), flush=True)

    bad = [g for g in res if g[1] != lines[g[0]]["expect"]]
    with open(os.path.join(out, "summary.txt"), "w", encoding="utf-8") as f:
        f.write("%d lines, %d passed, %d failed, %.0fs wall, %d at a time\n"
                % (len(lines), len(lines) - len(bad), len(bad), time.time() - t0, n))
        if len(bad) > 1 and len(bad) >= 0.8 * len(lines):
            f.write("NEARLY EVERY LINE FAILED: suspect the TOOLS (jsbeeb, the listing/dump format, the "
                    "build) before the port - read 000.out first\n")
        for i, rc, dt, shown in res:
            f.write("%s %03d rc=%d want=%d %6.1fs  %s\n" % (
                "pass" if rc == lines[i]["expect"] else "FAIL", i, rc, lines[i]["expect"], dt, shown))
    print(open(os.path.join(out, "summary.txt"), encoding="utf-8").read())
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
