#!/usr/bin/env python3
"""
build_stamp.py - write the build's generated inputs, touching each file only
when its contents change.

  python tools/build_stamp.py BUILD_DIR CONFIG_NAME [NAME=VALUE ...]

writes two files into BUILD_DIR:
  build_time.6502  one line, BUILD_TIME = "...", which main.6502 INCLUDEs for
                   the !BOOT stamp (Baron has no TIME$);
  CONFIG_NAME      the time and every NAME=VALUE flag (RELEASE=0, MASTER=0),
                   one per line. The Makefile makes the raw image depend on
                   this file, so a new stamp or a changed flag reassembles and
                   nothing else does.

THE TIME IS THE SOURCE'S, NOT THE CLOCK'S, so two machines building the same
commit produce the same image and its SHA256 can be compared between them
(paradroid-beeb issue #3: a tester's hash could not be checked because !BOOT
carried the wall clock). In order:
  1. $SOURCE_DATE_EPOCH, if set - the reproducible-builds.org convention;
  2. the commit time of the last commit touching the working directory, with
     "+" appended when it has uncommitted changes, so a dirty tree's build
     says so;
  3. outside a git checkout, the wall clock. Not reproducible, and it says
     so on stderr.
Always UTC, always English month names (strftime in the C locale, which is
the locale Python starts in).

WRITTEN ONLY WHEN CHANGED. make decides by mtime, so rewriting an unchanged
file would make every build reassemble - Paradroid's Makefile hit exactly
that with a config stamp. Writes go to a temporary file and are renamed into
place, so an interrupted run never leaves half a file behind.

build.ps1 runs this too, so the two builds stamp the same text and produce
the same image.
"""

import os
import subprocess
import sys
import time
from pathlib import Path


def _git(*args):
    return subprocess.run(["git", *args], capture_output=True, text=True,
                          check=True).stdout.strip()


def source_time():
    """(seconds since the epoch, suffix) for the stamp."""
    sde = os.environ.get("SOURCE_DATE_EPOCH")
    if sde:
        return int(sde), ""
    try:
        t = int(_git("log", "-1", "--format=%ct", "--", "."))
        dirty = _git("status", "--porcelain", "--", ".")
        return t, "+" if dirty else ""
    except (OSError, subprocess.CalledProcessError, ValueError):
        print("build_stamp: no SOURCE_DATE_EPOCH and not a git checkout - "
              "stamping the wall clock, so this build is not reproducible",
              file=sys.stderr)
        return int(time.time()), ""


def write_if_changed(path, text):
    data = text.encode("ascii")
    if path.exists() and path.read_bytes() == data:
        return False
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)
    return True


def main(argv):
    if len(argv) < 2 or any("=" not in a for a in argv[2:]):
        raise SystemExit(__doc__)
    build, config = Path(argv[0]), argv[1]
    build.mkdir(parents=True, exist_ok=True)

    t, suffix = source_time()
    stamp = time.strftime("%d %b %Y %H:%M:%S", time.gmtime(t)) + suffix
    write_if_changed(build / "build_time.6502", f'BUILD_TIME = "{stamp}"\n')
    lines = [f"BUILD_TIME={stamp}"] + list(argv[2:])
    if write_if_changed(build / config, "\n".join(lines) + "\n"):
        print(f"  stamp: {stamp} {' '.join(argv[2:])}")


if __name__ == "__main__":
    main(sys.argv[1:])
