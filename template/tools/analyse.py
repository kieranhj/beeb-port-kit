"""
analyse.py - static analysis of this build's 6502: liveness, constants, value
ranges and the bytes they can save, by beebgame's tools/dataflow.

beeb-port-kit template, MIT, Kieran Connell 2026. The analyses are Eben
Upton's (github.com/ebenupton/beebgame, tools/dataflow), run unmodified at a
pinned commit; docs/dataflow.md in the kit says what they find and how to use
it safely.

    python tools/analyse.py report      build/dataflow/report.md, abi.md, annotated/
    python tools/analyse.py annotate    build/annotated/src/... (the sources with
                                        the state before every instruction), summary.md
    python tools/analyse.py patterns    mechanical finds over the ranges, printed
    python tools/analyse.py all         the three

Build first: it reads what the build left (build/game.lst, game.symbols.json,
game-raw.ssd), never reassembles. `report` takes about a second; `annotate`
and `patterns` run the whole-program range analysis, about two minutes on the
template the first time and seconds after (it caches a sound starting point,
keyed to the build, in build/dataflow-in/ranges_I.json).

WHERE THE ANALYSES COME FROM. tools/dataflow/, vendored: beebgame's
tools/dataflow at the commit pinned below (MIT, its LICENSE beside it), and
UNMODIFIED - every file is checked against its SHA-256 before anything runs,
and a copy that differs is refused rather than run. tools/dataflow/VENDORED.md
says what was checked when it was installed. Two ways to look at another
commit, both fetched from a beebgame checkout ($BEEBGAME, ../../beebgame,
../beebgame - read with `git show <commit>:...`, so its own state does not
matter) or else GitHub's archive of that commit:

    python tools/analyse.py report --try <commit>   run that commit's analyses,
                                    fetched into build/dataflow-upstream/<commit>/,
                                    leaving the vendored copy alone
    python tools/analyse.py --vendor <commit>       replace tools/dataflow/ with
                                    that commit's and print the PIN and SHA256 to
                                    paste below - nothing runs until they are

Move the pin as a decision: read the changes, `--try` it on the template and a
real port against the current results, then `--vendor`, paste, and redo
VENDORED.md's checks.

HOW THEY RUN ON A BARON BUILD. The analyses read ld65's debug file. A Baron
build has none, so tools/baron_dbg.py writes one from the listing, the symbol
dump and the raw disc (its header says how and what it cannot know), and the
analyses are pointed at that. Upstream functions are patched as they run,
in memory, and two only: `model.Source.short` joins paths with os.sep while
every caller compares with '/' (on Windows no file would be the game's), and
a range analysis that runs out of steps is marked unconverged - upstream
calls it converged and annotates it without a warning, though it is not a
fixpoint (_run_upstream says more). `--budget N` raises the step limit.

CONFIG. tools/dataflow_config.py says what is this game's: the interrupt's
entry, its sources' directory, and what the template has none of (inline
operand helpers, an object model). beebgame's tools/dataflow/gamecfg.py
documents every field.
"""

import argparse
import hashlib
import io
import os
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path

PIN = "e07f8b25af4493a37f21604883949c3658eb5e53"     # beebgame, 2026-10-06: MIT
REPO = "https://github.com/ebenupton/beebgame"
SHA256 = {
    "LICENSE": "790e97e5467e541e53f2b8f45b3f95d0a1d086d4005551cc6496eb39aafa9b2e",
    "README.md": "ffebb0d9b1bf4ddd2687550c80ee8e3da0b8da98765ce42fb6d57ef526035816",
    "analysis.py": "63de194f57ec89f2072ac0faac23fcea39b38c15db1c75f42a6fed1d6a84992d",
    "annotate.py": "a6875ee74604f3db9a27e7ba519645e4b2dae68dace9767efe1b7f2ae1ee6ec8",
    "dataflow.py": "cfad13aa3df3f629272d9c10428309b6684e6afb485330d656948ab66f648a30",
    "dom.py": "3d5f983539047defa35fa6f55cfbf3b011d451bcd8f478229453b023721112c3",
    "findings.py": "48c8e701b65efb0122946b2f56aae7b3aa9be34fab516cc9a76bb8173b545025",
    "forward.py": "bbea6a4cb13e2a70789d9df5715e72e4300c7aef8828d7f72bd285a160179145",
    "gamecfg.py": "fc0551ca46689a2be574c24f5b5600ae0c9b2dea136e88db35225ff2cdd3b8b4",
    "model.py": "2a540bf46f6d362f6007eb65b92d5e0292c90d73a18e7af2468ee80a7f2009bf",
    "patterns.py": "992ebe5fcc7149c6d43e865a0f63f28bf811543095db6a221ff65ba6dd8f280e",
    "ranges.py": "dd012e80a88e97c3ed56914dc2c019a4606b819ad930f7e2c1b0afa0005774d5",
}

ROOT = Path(__file__).resolve().parent.parent
TOOLS = Path(__file__).resolve().parent
VENDORED = TOOLS / "dataflow"
sys.path.insert(0, str(TOOLS))


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _from_checkout(commit):
    """tools/dataflow/* and LICENSE at `commit`, from a local beebgame checkout."""
    places = [os.environ.get("BEEBGAME"), ROOT.parent.parent / "beebgame", ROOT.parent / "beebgame"]
    for p in places:
        if not p or not (Path(p) / ".git").exists():
            continue
        ls = subprocess.run(["git", "-C", str(p), "ls-tree", "--name-only", commit, "tools/dataflow/"],
                            capture_output=True, text=True)
        if ls.returncode != 0 or not ls.stdout.strip():
            continue
        got = {}
        for path in ls.stdout.split() + ["LICENSE"]:
            r = subprocess.run(["git", "-C", str(p), "show", "%s:%s" % (commit, path)], capture_output=True)
            if r.returncode == 0:
                got[path.rsplit("/", 1)[-1]] = r.stdout
        return got, "%s at %s" % (p, commit[:7])
    return None, None


def _from_github(commit):
    url = "https://codeload.github.com/ebenupton/beebgame/zip/%s" % commit
    with urllib.request.urlopen(url, timeout=60) as r:
        z = zipfile.ZipFile(io.BytesIO(r.read()))
    got = {}
    for info in z.infolist():
        parts = info.filename.split("/")
        if len(parts) == 4 and parts[1:3] == ["tools", "dataflow"] and parts[3]:
            got[parts[3]] = z.read(info)
        elif len(parts) == 2 and parts[1] == "LICENSE":
            got["LICENSE"] = z.read(info)
    return got, url


def _fetch(commit):
    got, where = _from_checkout(commit)
    if got is None:
        got, where = _from_github(commit)
    if not any(n.endswith(".py") for n in got):
        raise SystemExit("beebgame %s from %s: no tools/dataflow there" % (commit[:7], where))
    return got, where


def vendored():
    """tools/dataflow/, checked byte for byte against the pin."""
    bad = [n for n, h in SHA256.items()
           if not (VENDORED / n).exists() or _sha((VENDORED / n).read_bytes()) != h]
    if bad:
        raise SystemExit(
            "tools/dataflow/%s: missing or not beebgame %s's bytes - nothing was run.\n"
            "The vendored copy is kept unmodified (tools/dataflow/VENDORED.md): restore it with\n"
            "`git checkout -- tools/dataflow`, or after a --vendor paste the PIN and SHA256 it printed."
            % (", ".join(bad), PIN[:7]))
    return VENDORED


def trial(commit):
    """Another commit's analyses in build/dataflow-upstream/<commit>/, for comparison."""
    d = ROOT / "build" / "dataflow-upstream" / commit
    if not (d / "model.py").exists():
        got, where = _fetch(commit)
        d.mkdir(parents=True, exist_ok=True)
        for n, data in got.items():
            (d / n).write_bytes(data)
        print("fetched beebgame %s from %s (a trial: not the vendored copy)" % (commit[:7], where),
              flush=True)
    return d


def vendor(commit):
    """Replace tools/dataflow/ with `commit`'s and print the constants to paste."""
    got, where = _fetch(commit)
    if "LICENSE" not in got:
        raise SystemExit("beebgame %s has no LICENSE: it cannot be vendored" % commit[:7])
    VENDORED.mkdir(exist_ok=True)
    for f in VENDORED.iterdir():
        if f.is_file() and f.name != "VENDORED.md" and f.name not in got:
            f.unlink()
    for n, data in got.items():
        (VENDORED / n).write_bytes(data)
    print("# tools/dataflow/ is now beebgame %s, from %s. Paste into tools/analyse.py,\n"
          "# then update tools/dataflow/VENDORED.md and redo its checks:" % (commit[:7], where))
    print('PIN = "%s"' % commit)
    print("SHA256 = {")
    for n in sorted(got, key=lambda n: (n.endswith(".py"), n)):
        print('    "%s": "%s",' % (n, _sha(got[n])))
    print("}")


def _run_upstream(up, tool, args, budget=None):
    """In a child process: the pinned tool, with the two patches below."""
    sys.path.insert(0, up)
    import runpy
    import model
    import ranges

    # 1. model.Source.short joins with os.sep and every caller compares with
    #    '/': on Windows no file would be the game's.
    short = model.Source.short
    model.Source.short = lambda self, fid: short(self, fid).replace(os.sep, "/")

    # 2. When the range analysis runs out of steps it stops mid-worklist but
    #    still calls the result converged, caches it as a sound start and
    #    writes the annotations without a warning (measured on puzzle-beeble,
    #    2026-10-06: 8,295 of 9,380 instructions reached). A cut-off run is not
    #    a fixpoint: mark it so - annotate.py then prints its own NOT-sound
    #    banner on every file - drop the cache, and say so. --budget raises
    #    the limit (upstream's is 3,000,000 steps).
    init = ranges.Ranges.__init__

    def init_budget(self, *a, **k):
        init(self, *a, **k)
        if budget:
            self.budget = budget
    ranges.Ranges.__init__ = init_budget
    analyse = ranges.analyse

    def analyse_honestly(build, *a, **k):
        R = analyse(build, *a, **k)
        if any("step budget exhausted" in n for n in getattr(R, "notes_all", [])):
            R.converged = False
            R.notes_all.append("WARNING (tools/analyse.py): the step budget ran out, so these "
                               "states are not a fixpoint and are NOT sound - raise --budget")
            try:
                os.remove(os.path.join(build, "ranges_I.json"))
            except OSError:
                pass
            print("WARNING: the range analysis ran out of steps (%d of %d instructions reached): "
                  "the ranges are NOT sound. Raise --budget." % (len(R.reached), len(R.P.insns)),
                  file=sys.stderr, flush=True)
        return R
    ranges.analyse = analyse_honestly
    sys.argv = [os.path.join(up, tool)] + args
    runpy.run_path(sys.argv[0], run_name="__main__")


def main(argv):
    if argv[:1] == ["--run-upstream"]:
        budget = int(os.environ.get("DATAFLOW_BUDGET", "0")) or None
        return _run_upstream(argv[1], argv[2], argv[3:], budget)
    ap = argparse.ArgumentParser(description="beebgame's dataflow analyses on this Baron build")
    ap.add_argument("what", nargs="?", default="report", choices=["report", "annotate", "patterns", "all"])
    ap.add_argument("--config", default=str(TOOLS / "dataflow_config.py"))
    ap.add_argument("--listing", default="build/game.lst")
    ap.add_argument("--symbols", default="build/game.symbols.json")
    ap.add_argument("--disc", default="build/game-raw.ssd")
    ap.add_argument("--main", default=None, help="the main source (default: the dump's first)")
    ap.add_argument("--budget", type=int, default=None,
                    help="range analysis steps a round (upstream: 3,000,000)")
    ap.add_argument("--try", dest="trial", metavar="COMMIT",
                    help="run another beebgame commit's analyses instead of the vendored copy")
    ap.add_argument("--vendor", metavar="COMMIT",
                    help="replace tools/dataflow/ with that commit's and print the new pin")
    ap.add_argument("extra", nargs=argparse.REMAINDER, help="after --: passed to the analysis")
    a = ap.parse_args(argv)
    if a.vendor:
        return vendor(a.vendor)
    for p in (a.listing, a.symbols, a.disc):
        if not (ROOT / p).exists():
            raise SystemExit("%s is missing: build first" % p)
    up = trial(a.trial) if a.trial else vendored()
    import baron_dbg
    s = baron_dbg.convert(ROOT, ROOT / a.listing, ROOT / a.symbols, ROOT / a.disc,
                          ROOT / "build" / "dataflow-in", a.main)
    print("baron_dbg: %d statements, %d placed in the sources, %d not placed"
          % (s["emits"], s["placed"], s["unplaced"]), flush=True)
    for n in s["notes"]:
        print("  note: " + n)
    extra = [x for x in a.extra if x != "--"]
    common = ["--root", str(ROOT), "--build", str(ROOT / "build" / "dataflow-in")]
    if a.config and Path(a.config).exists():
        common += ["--config", a.config]
    jobs = {"report": ("dataflow.py", ["--out", str(ROOT / "build" / "dataflow")]),
            "annotate": ("annotate.py", ["--out", str(ROOT / "build" / "annotated")]),
            "patterns": ("patterns.py", [])}
    for w in (["report", "annotate", "patterns"] if a.what == "all" else [a.what]):
        tool, own = jobs[w]
        env = dict(os.environ)
        if a.budget:
            env["DATAFLOW_BUDGET"] = str(a.budget)
        r = subprocess.run([sys.executable, "-X", "utf8", __file__, "--run-upstream", str(up), tool]
                           + common + own + extra, cwd=ROOT, env=env)
        if r.returncode:
            raise SystemExit(r.returncode)


if __name__ == "__main__":
    main(sys.argv[1:])
