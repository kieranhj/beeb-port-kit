"""runner.py - drive MAME as a measuring instrument, reproducibly.

Fork this into your project's tools/; keep this header.

From 1942-beeb's `tools/run_mame.py` (2026-09-07 onwards), which ran every arcade
capture that port made: the stage captures, the whole-game invincible capture
(242,100 frames), the sound-CPU RAM captures, the DIP-switch reads and the headless
debugger sessions. What it guards against, each found the hard way there:

  * A SECOND INSTANCE. MAME 0.177 will not run two instances of the same machine: the
    second blocks for ever instead of failing, and a stuck one poisons every run
    after it. Measured 2026-09-07: with one running, the capture timed out at 45 s;
    alone it took 14 s (1942-beeb docs/arcade-facts.md s1). `already_running()`.
  * A RELATIVE OUTPUT PATH. MAME runs with its own directory as its working
    directory, so a relative capture path never resolves and the Lua dies with "No
    such file or directory". `out` is made absolute.
  * STALE OUTPUT. A generating script died on a locked file, the error was lost in a
    pipe, and the stale file it left was handed over as a fix (1942-beeb BUGS.md #3).
    Every expected file must exist AND be newer than the run's start
    (`check_outputs`).
  * MAME's EXIT CODE, checked; and a run that never finishes is KILLED on a timeout,
    the process tree and only that tree.
  * stdin. MAME hung before running the autoboot script when handed a stdin with no
    console behind it - a backgrounded or piped parent (measured 2026-09-07). stdin
    is DEVNULL.
  * `-debugger none` WITH `-debug`. The debugscript then never runs, nothing is
    written and the session hangs (arcade-facts s8). `build_command` refuses it.
  * The cfg's DIP OVERRIDES. MAME applies cfg/<game>.cfg to -playback too, and
    1942-beeb's had set Easy and five lives by hand, so every capture for weeks was
    Easy (decision 36, arcade-facts s34). `cfg_overrides()` reports them; the run
    prints them every time.

Nothing here is 1942's: the MAME directory and the game come from arguments or the
MAME_DIR / MAME_GAME / MAME_EXE environment variables, never from a constant.

    python -m beeb_port_kit.mame.runner --game 1942 --script tools/mame/capture_ram.lua \\
        --out D:/scratch/cap --frames 3000 --expect ram.bin,schema.txt \\
        --env CAPTURE_SPEC=f:frame;spr:bytes@cc00-cc7f
    python -m beeb_port_kit.mame.runner --game 1942 --debug cmds.txt --expect out.txt
    python -m beeb_port_kit.mame.runner --game 1942 --cfg      # just print cfg overrides
"""

import argparse
import os
import re
import subprocess
import sys
import time

DEFAULT_EXE = "mame64.exe" if os.name == "nt" else "mame"
LUA_ERROR = "lua_error.txt"     # template/tools/mame/_compat.lua writes it, then exits


class MameError(Exception):
    """A run that cannot be trusted: MAME failed, timed out, or did not write what it
    promised. The message says which, and that nothing it left behind is current."""


def mame_dir(arg=None):
    d = arg or os.environ.get("MAME_DIR")
    if not d:
        raise MameError("no MAME directory: pass --mame or set MAME_DIR")
    return os.path.abspath(d)


def mame_exe(directory, arg=None):
    name = arg or os.environ.get("MAME_EXE") or DEFAULT_EXE
    path = name if os.path.isabs(name) else os.path.join(directory, name)
    if not os.path.exists(path):
        raise MameError("MAME executable not found at %s (set MAME_EXE)" % path)
    return path


def already_running(image=DEFAULT_EXE):
    """True if a process with this image name is running. False when it cannot tell
    (the timeout then catches a hang)."""
    try:
        if os.name == "nt":
            out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq %s" % image],
                                 capture_output=True, text=True, timeout=20).stdout
            return image.lower() in out.lower()
        r = subprocess.run(["pgrep", "-x", os.path.basename(image)],
                           capture_output=True, text=True, timeout=20)
        return r.returncode == 0
    except Exception:
        return False


def build_command(exe, game, script=None, debugscript=None, playback=None, record=None,
                  video=False, sound=False, throttle=False, extra=()):
    """The MAME command line. Pure, so it can be tested without MAME.

    Headless by default: -video none -sound none -nothrottle. A screenshot harness
    needs video on (`video=True`): -video none has nothing to snapshot."""
    extra = list(extra)
    if debugscript and "-debugger" in extra:
        i = extra.index("-debugger")
        if i + 1 < len(extra) and extra[i + 1] == "none":
            raise MameError("-debug with -debugger none: the debugscript never runs and "
                            "the session hangs (1942-beeb arcade-facts s8)")
    cmd = [exe, game, "-skip_gameinfo"]
    if not sound:
        cmd += ["-sound", "none"]
    if not throttle:
        cmd += ["-nothrottle"]
    if not video:
        cmd += ["-video", "none"]
    if script:
        cmd += ["-autoboot_script", os.path.abspath(script).replace("\\", "/")]
    if debugscript:
        cmd += ["-debug", "-debugscript", os.path.abspath(debugscript).replace("\\", "/")]
    if playback:
        cmd += ["-playback", playback]
    if record:
        cmd += ["-record", record]
    return cmd + extra


def check_outputs(out, expects, started):
    """[(file, problem)] for every expected file that is absent or older than
    `started` (a time.time()). Empty means every one was written by this run."""
    bad = []
    for f in expects:
        p = os.path.join(out, f)
        if not os.path.exists(p):
            bad.append((f, "absent"))
        elif os.path.getmtime(p) < started - 1.0:
            # one second's slack for filesystems with coarse mtimes; a stale file
            # from an earlier run is minutes or days old
            bad.append((f, "STALE - not written by this run"))
    return bad


_PORT = re.compile(r'<port\s+([^>]*?)/?>')
_ATTR = re.compile(r'(\w+)="([^"]*)"')


def cfg_overrides(directory, game):
    """The DIP switches and configuration settings MAME's cfg/<game>.cfg changes from
    the driver's defaults: [(tag, type, mask, defvalue, value)].

    MAME writes these when a setting is changed by hand and applies them to every
    later run, -playback included. A capture is therefore taken under the cfg's
    cabinet, not the driver's - so what the cabinet is set to is a measurement
    (dips.lua) and this is the cheap first look."""
    path = os.path.join(directory, "cfg", game + ".cfg")
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8", errors="replace") as f:
        text = f.read()
    out = []
    for m in _PORT.finditer(text):
        a = dict(_ATTR.findall(m.group(1)))
        if a.get("type") not in ("DIPSWITCH", "CONFIG") or "value" not in a:
            continue
        if a.get("value") != a.get("defvalue"):
            out.append((a.get("tag"), a.get("type"), int(a.get("mask", "0")),
                        int(a.get("defvalue", "0")), int(a["value"])))
    return out


def _kill_tree(proc):
    if os.name == "nt":
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                       capture_output=True)
    else:
        proc.kill()
    try:
        proc.wait(timeout=30)
    except Exception:
        pass


class Result:
    def __init__(self, cmd, returncode, stdout, stderr, written, seconds):
        self.cmd, self.returncode = cmd, returncode
        self.stdout, self.stderr = stdout, stderr
        self.written, self.seconds = written, seconds

    def tail(self, n=4):
        return [l for l in (self.stdout or "").splitlines() if l.strip()][-n:]


def run(game, out, script=None, debugscript=None, expects=(), env=None, frames=None,
        playback=None, record=None, timeout=900, directory=None, exe=None,
        video=False, sound=False, extra=(), guard=True, log=print):
    """One MAME run. Returns a Result, or raises MameError.

    `env` is merged over os.environ; CAPTURE_DIR (= out, absolute, forward slashes)
    and, if given, CAPTURE_FRAMES are always set, because every template harness
    reads them. `expects` are files relative to `out` that must be fresh afterwards."""
    if not script and not debugscript:
        raise MameError("nothing to run: pass a Lua script or a debugscript")
    directory = mame_dir(directory)
    exe = mame_exe(directory, exe)
    out = os.path.abspath(out)
    for p in (script, debugscript):
        if p and not os.path.exists(p):
            raise MameError("no such file: %s" % p)
    if guard and already_running(os.path.basename(exe)):
        raise MameError("a %s is already running and will block this one. Kill it "
                        "first, and do not leave a session open while capturing."
                        % os.path.basename(exe))
    os.makedirs(out, exist_ok=True)
    cmd = build_command(exe, game, script, debugscript, playback, record,
                        video=video, sound=sound, extra=extra)
    full_env = dict(os.environ)
    full_env.update({k: str(v) for k, v in (env or {}).items()})
    full_env["CAPTURE_DIR"] = out.replace("\\", "/")
    if frames is not None:
        full_env["CAPTURE_FRAMES"] = str(frames)
    if script:
        full_env.setdefault("MAME_LUA_DIR",
                            os.path.dirname(os.path.abspath(script)).replace("\\", "/"))
    for tag, typ, mask, dv, v in cfg_overrides(directory, game):
        log("  NOTE cfg/%s.cfg overrides %s %s mask %02X: %02X (driver %02X)"
            % (game, tag, typ, mask, v, dv))
    log("$ " + " ".join(cmd))
    started = time.time()
    proc = subprocess.Popen(cmd, cwd=directory, env=full_env, stdin=subprocess.DEVNULL,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            text=True, errors="replace")
    try:
        so, se = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        _kill_tree(proc)
        raise MameError("MAME did not finish in %d s and was killed. The usual causes: "
                        "another instance holding the machine, a Lua error before the "
                        "output was opened, or a script with no exit condition. Nothing "
                        "it wrote is current." % timeout)
    secs = time.time() - started
    res = Result(cmd, proc.returncode, so, se, [], secs)
    for l in res.tail():
        log("  " + l)
    if proc.returncode != 0:
        raise MameError("MAME exited %d\n%s" % (proc.returncode, (se or "")[-800:]))
    err = os.path.join(out, LUA_ERROR)
    if os.path.exists(err) and os.path.getmtime(err) >= started - 1.0:
        with open(err, encoding="utf-8", errors="replace") as f:
            raise MameError("the Lua harness failed: %s" % f.read().strip())
    bad = check_outputs(out, expects, started)
    if bad:
        raise MameError("the run did not produce: " +
                        ", ".join("%s (%s)" % b for b in bad))
    for f in expects:
        p = os.path.join(out, f)
        res.written.append((f, os.path.getsize(p)))
        log("  wrote %-16s %d bytes" % (f, os.path.getsize(p)))
    if playback:
        log("  NOTE: MAME runs on after the .inp ends. Frames past the recording's own "
            "length are not play (1942-beeb BUGS.md #13).")
    return res


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--mame", help="MAME directory (default $MAME_DIR)")
    ap.add_argument("--exe", help="executable name or path (default $MAME_EXE or %s)"
                    % DEFAULT_EXE)
    ap.add_argument("--game", default=os.environ.get("MAME_GAME"),
                    help="machine name (default $MAME_GAME)")
    ap.add_argument("--script", help="a Lua autoboot script")
    ap.add_argument("--debug", metavar="CMDS", help="run the DEBUGGER with this command "
                    "script instead. Never add -debugger none")
    ap.add_argument("--out", help="capture directory - outside the repo")
    ap.add_argument("--frames", type=int, help="sets CAPTURE_FRAMES")
    ap.add_argument("--expect", default="", help="comma-separated files that must be "
                    "written by this run")
    ap.add_argument("--playback", help="a .inp in MAME's inp/ directory")
    ap.add_argument("--record", help="record input to this .inp")
    ap.add_argument("--env", action="append", default=[], metavar="K=V")
    ap.add_argument("--timeout", type=int, default=900)
    ap.add_argument("--video", action="store_true", help="keep video on (screenshots)")
    ap.add_argument("--cfg", action="store_true", help="print the cfg overrides and stop")
    a = ap.parse_args(argv)
    if not a.game:
        ap.error("--game or MAME_GAME is required")
    try:
        if a.cfg:
            ov = cfg_overrides(mame_dir(a.mame), a.game)
            for tag, typ, mask, dv, v in ov:
                print("%s %s mask=%02X value=%02X (driver default %02X)"
                      % (tag, typ, mask, v, dv))
            print("%d override(s)" % len(ov))
            return 0
        if not a.out:
            ap.error("--out is required")
        env = dict(kv.split("=", 1) for kv in a.env)
        run(a.game, a.out, script=a.script, debugscript=a.debug,
            expects=[f.strip() for f in a.expect.split(",") if f.strip()], env=env,
            frames=a.frames, playback=a.playback, record=a.record, timeout=a.timeout,
            directory=a.mame, exe=a.exe, video=a.video)
    except MameError as e:
        print("FAIL: %s" % e, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
