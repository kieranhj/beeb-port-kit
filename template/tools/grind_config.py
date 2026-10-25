"""
grind_config.py - what tools/grind.py (the kit's beeb-micro-grind skill) needs to know about THIS
project: which code it must not touch, which sources are generated, how to build it, how to prove
a change and how to measure one. grind.py names no game; everything project-specific is here.

beeb-port-kit template, MIT, Kieran Connell 2026. The shape is Stryker's Run's
tools/grind_config.py (2026-10-17 to 10-25); its values, kept in the comments as the worked
example, are a 25 Hz Master game with four sideways banks, a raster-timed palette split and a
pair harness; the values below are the template's own (a Model B, one 25 Hz loop, a two-cycle
CRTC rupture). Every entry says why: a grind is only as safe as this file.

Proved on the template 2026-10-25 (the commit says how): `grind.py windows` over its annotated
build, and `grind.py gate` against a hand-made candidate and a deliberately slower one.
"""
import os

# ---------------------------------------------------------------- where things are
# The annotated sources (tools/analyse.py annotate), the debug file baron_dbg.py wrote for the
# analyses (it maps every source line to its address), and the source directories a candidate
# may change (`run` commits these and the ledger, nothing else).
ANNOTATED = 'build/annotated'
DBG = 'build/dataflow-in/game.dbg'
SOURCES = ('src/',)
# The record: ledger.jsonl (every candidate ever and its fate), seen.txt (windows evaluated, by
# content hash), README.md (`grind.py report`). Committed with the code it changed.
LEDGER_DIR = 'docs/grind'

# ---------------------------------------------------------------- what is not ground
# Sources written by a generator: never edited by hand, so never windows. A better pattern there
# is a change to the generator, proposed and gated outside the window workflow. The template
# generates only data (src/data/panel.bin, tools/export_panel.py). Stryker's Run listed twelve:
# its compiled sprites, the run-length sprites, the sound effects' ramps, the packed music.
GENERATED = ()

# Lines that must not change, by label: from the line of `.frm` to the first line after it whose
# code contains `to` (inclusive). A window overlapping them is still shown to the optimisers with
# the lines marked PROTECTED, for context; a window that is all protected is dropped.
# The template's are its raster timing: every cycle from the interrupt's entry to fire 2's first
# palette write is part of T1_TUNE2's measured phase (CLAUDE.md "Confirmed hardware facts"), and
# the VSync hook restarts T1 first (decision 5). A cycle saved there moves the palette switch off
# the panel's blank last scanline. Stryker's Run protected the same kind of code: its interrupt's
# palette writes (timed from vsync) and an OSBYTE 19 wait whose returned registers it relied on.
PROTECT = (
    dict(file='src/lib/irq.6502', frm='irq_handler', to='jsr irq_vsync_hook',
         why='raster timing: the dispatch is in the cycles from the interrupt to every T1 fire and '
             'to the palette writes (T1_TUNE2 was measured through it)'),
    dict(file='src/rupture.6502', frm='rupt_vsync', to='sta SYS_VIA_T1LH',
         why='decision 5: T1 is restarted FIRST in the VSync hook; anything before the restart moves '
             'every fire'),
    dict(file='src/rupture.6502', frm='rupt_timer', to='PALSET 0, PLAY_PHYS_0',
         why='raster timing: fire 2\'s palette writes land at a measured cycle of the panel\'s last '
             'scanline (T1_TUNE2 = 58, measured to the first write)'),
)

# Byte ranges that must not change, by SECTION (the debug file's segment) and run address: code
# the build reads as data. None here. Stryker's Run: ('moved_0004', 0x0004, 0x001E, ...) - a dead
# zero-page unpacker whose bytes the shipping build's ground texture read (its BUGS #1), which the
# proofs (run on a relocated build) could not see change.
PROTECT_BYTES = ()

# Where a SECTION's code runs, for the profile's keys (bank << 16 | address in &8000-&BFFF): the
# bank it is paged into. The template uses no bank. Stryker's Run: {'DATA1': 4, 'DATA2': 5,
# 'DATA3': 6, 'DATA4': 7}.
SEGMENT_BANK = {}

# Profile phases that are not work: the frame lock's spin (tools/pcprof.mjs --wait), which a
# faster pass only lengthens.
EXCLUDE_PHASES = ('wait',)

# Candidates claiming this many cycles a pass get the third skeptic (the project lens).
THREE_SKEPTICS_FROM = 5

# ---------------------------------------------------------------- building
# Each build the gate makes, as the arguments to build.ps1 (Windows) and make (elsewhere), and
# the image it leaves (its .symbols.json and .lst beside it are kept with it). Every one must
# assemble; BENCH is the one every proof and measurement runs on. The gate builds the control
# (HEAD) in a git worktree, where bin/ (gitignored) is absent: build_env points the build at this
# copy's tools. Stryker's Run built four: the bench (DEBUG_LIVES: no deaths, so a long game), its
# full-redraw twin (the oracle), the shipping disc (the front end check) and the release.
BUILDS = {
    'bench': dict(ps=[], make=[], image='build/game.ssd'),
    'master': dict(ps=['-Master'], make=['master'], image='build/game-master.ssd'),
}
BENCH = 'bench'


def build_env(root):
    """Environment for every build: the assembler and compressor from this copy's bin/ when they
    are there (build.ps1 and the Makefile take $BARON and $ZX02 first)."""
    exe = '.exe' if os.name == 'nt' else ''
    env = {}
    for name in ('baron', 'zx02'):
        p = root / 'bin' / (name + exe)
        if p.exists() and not os.environ.get(name.upper()):
            env[name.upper()] = p
    return env


# What a failed build's output says when a candidate clashed with one kept before it (its label
# or callee gone) and when its region's ASSERT failed (worth retrying once the region has grown).
# Baron's own words for the first; the second is the text of the project's region ASSERTs.
STALE = r'Duplicate symbol|Undefined symbol'
NO_ROOM = r'overruns|would load over'

# ---------------------------------------------------------------- proving
# Every check a batch must pass, at most PARALLEL at once: (name, argv) judged by the kit's exit
# code contract (0 pass, 1 wrong, 2 could not judge), or (name, argv, judge(returncode, stdout)
# -> (ok, why)). argv's {KIND} is the test's image of that build, {ctl_KIND} the control's.
# The template's oracle is verify_dynamic (the panel byte for byte, the field counter, the
# 25 Hz lock, the scroll under a held X) on both models. That is thin: it never compares the
# test against the control. A real port's list is its suite - Stryker's Run's ran state and
# shown screen in lockstep with the control over 6,000 passes (seed 1) and 4,000 (seed 3), the
# full-redraw oracle over 4,000, two helicopter flights, the front end's 15 checks and observer
# mode's keys, a path play never takes (its BUGS #11: a grind change broke it unseen). The gate
# can only refute what the checks run: every rarely-taken path needs a check of its own.
CHECKS = (
    ('verify_dynamic B', ['node', 'tools/verify_dynamic.mjs', '{bench}', 'B-DFS1.2']),
    ('verify_dynamic Master', ['node', 'tools/verify_dynamic.mjs', '{master}', 'Master']),
)
QUICK = ('verify_dynamic B',)
PARALLEL = 4

# ---------------------------------------------------------------- measuring
# (name, argv with {img}, the field of its last JSON line): cycles a pass, lower is better,
# measured on the control and the test alike. tools/pcprof.mjs's `perPass.work` is a pass's
# cycles less the frame lock's spin. Two games: idle and X held (the scroll's path). Stryker's
# Run measured pcprof's work on two keyed-by-pass games (a scripted seed, RIGHT held).
_PC = ['node', 'tools/pcprof.mjs', '{img}', '--pass', 'main_loop', '--passes', '200', '--wait', 'wait_take:4']
MEASURE = (
    ('idle', _PC),
    ('X held', _PC + ['--keys', 'X']),
)
MEASURE = tuple((name, argv, 'perPass.work') for name, argv in MEASURE)

# A difference this small (cycles a pass) is not a saving. pcprof is deterministic on the same
# image; two builds of the same source differ only in the stamp. Stryker's Run measured 0.1 on an
# unchanged tree and used 1.0.
NOISE = 0.5
