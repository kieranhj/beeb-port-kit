// lockstep.mjs - the relocation proof, first half: two builds of the same source,
// one moved by whole pages, run side by side on the same input, and the first frame
// whose screen differs.
//
// beeb-port-kit template, MIT, Kieran Connell 2026. From Stryker's Run's
// tools/lockstep.mjs (2026-10-03 on; its PLAN's phase 2 and decision 7), which with
// tracediff.mjs found its BUGS #1 and #2: data the original reads at an address
// that does not move with the code that names it.
//
//   node tools/lockstep.mjs CONFIG CONTROL.ssd SHIFTED.ssd [--frames F] [--seed S]
//
// THE PAIR. SHIFTED is the source assembled with its code moved by a whole number of
// pages (the template: build.ps1 -Shift 256; make SHIFT=256), CONTROL the same
// source with the same padding where it moves nothing (-Shift 256 -ShiftEnd), so the
// two discs hold files of the same sizes in the same places and load in exactly the
// same time. Moving by whole pages keeps every page crossing where it was, so a
// correct relocation runs CYCLE FOR CYCLE like its control - even a game that takes
// its random numbers from a free-running VIA timer, which is why this can compare
// frames and need not compare passes. Any difference in what is shown is an address
// that did not move with its target. (A shift that is not whole pages moves page
// crossings, and a cycle's difference is then not a fault: the harness refuses it.)
//
// THE INPUT, by frame: the config's start presses, then from relocate.playFrom
// (default: the last press + 100) passplay.mjs's generator with its hold and gap
// read as FIELDS x relocate.framesPerPass (default 2). Both machines get the same
// key on the same field.
//
// THE COMPARE, from relocate.compareFrom (the frames before it load the files, where
// the builds legitimately differ): relocate.compare's [at, len] ranges ("paged": the
// two machines page alike or the proof has already failed), and every 10 frames the
// emulator's rendered frame. Exit 0 identical for F frames (default 6000); 1 with
// the first frame that differs, both PCs named from each build's own symbols; 2 for
// a usage error or a pair whose labels moved by something other than whole pages.
import { createHash } from "node:crypto";

import { open } from "./harness.mjs";
import { burstKeys, DEFAULT_SCRIPT, keyOf, loadConfig } from "./passplay.mjs";
import { pageShifts } from "./relocate.mjs";

const args = process.argv.slice(2);
const opt = (flag, d) => { const i = args.indexOf(flag); if (i < 0) return d; return args.splice(i, 2)[1]; };
const FRAMES = parseInt(opt("--frames", "6000"), 10), SEED = parseInt(opt("--seed", "1"), 10);
const [cfgPath, discA, discB] = args;
if (!discB) { console.error("usage: node tools/lockstep.mjs CONFIG CONTROL.ssd SHIFTED.ssd [--frames F] [--seed S]"); process.exit(2); }
let cfg;
try { cfg = await loadConfig(cfgPath); } catch (e) { console.error(`lockstep: ${e.message}`); process.exit(2); }
const R = cfg.relocate || {};

const A = await open({ name: "lockstep", disc: discA, banks: cfg.banks });
const B = await open({ name: "lockstep", disc: discB, banks: cfg.banks });
for (const h of [A, B]) h.model = cfg.model || (h.define("MASTER") ? "Master" : "B-DFS1.2");
const shifts = pageShifts(A, B);
const ranges = (R.compare || []).map(([at, len]) => [A.addr(at), typeof len === "string" ? A.addr(len) : len]);
if (!ranges.length) A.die("the config's relocate.compare names no ranges");

// the input, by frame
const ev = new Map();
const at = (f, e) => { if (!ev.has(f)) ev.set(f, []); ev.get(f).push(e); };
const presses = cfg.start?.presses || [];
for (const [f, k, n = 40] of presses) { at(f, ["down", k]); at(f + n, ["up", k]); }
const per = R.framesPerPass ?? 2;
const spec = cfg.script || DEFAULT_SCRIPT;
const playFrom = R.playFrom ?? (presses.length ? Math.max(...presses.map(([f, , n = 40]) => f + n)) + 100 : 100);
const fieldSpec = { ...spec, hold: spec.hold.map((v) => v * per), gap: spec.gap.map((v) => v * per) };
const byFrame = burstKeys(Math.max(0, FRAMES - playFrom + 2), SEED, fieldSpec);
const COMPARE_FROM = R.compareFrom ?? 0;

for (const h of [A, B]) await h.boot({ settle: 0, ...(cfg.boot || {}) });
const hash = (s) => s._completeFb8 ? createHash("md5").update(s._completeFb8).digest("hex") : null;
let held = [], compared = 0;
const name = (h) => h.symAt(h.cpu.pc) ?? `&${h.cpu.pc.toString(16)}`;
for (let f = A.frames + 1; f <= FRAMES; f++) {
    for (const [what, k] of ev.get(f) || []) for (const h of [A, B]) (what === "down" ? h.keyDownRaw : h.keyUpRaw)(keyOf(h, cfg, k));
    if (f >= playFrom) {
        const want = byFrame[f - playFrom] || [];
        for (const h of [A, B]) {
            for (const k of held) if (!want.includes(k)) h.keyUpRaw(keyOf(h, cfg, k));
            for (const k of want) if (!held.includes(k)) h.keyDownRaw(keyOf(h, cfg, k));
        }
        held = want;
    }
    await A.s.runFrames(1);
    await B.s.runFrames(1);
    if (f < COMPARE_FROM) continue;
    let what = null;
    for (const [lo, n] of ranges) {
        const ra = A.rd(lo, n, "paged"), rb = B.rd(lo, n, "paged");
        for (let i = 0; i < n; i++) if (ra[i] !== rb[i]) { what = `memory &${(lo + i).toString(16).toUpperCase()}: ${ra[i]} vs ${rb[i]}`; break; }
        if (what) break;
    }
    if (!what && f % 10 === 0 && hash(A.s) !== hash(B.s)) what = "rendered frame";
    compared++;
    if (what) A.finish({ control: discA, shifted: discB, shifts, framesCompared: compared, firstDifference: f, what,
                         pc: { control: name(A), shifted: name(B) }, cycles: [A.s.elapsedCycles, B.s.elapsedCycles] },
                       false, { samples: compared });
    if (f % 500 === 0) console.error(`lockstep: frame ${f}: identical (cycles ${A.s.elapsedCycles} / ${B.s.elapsedCycles})`);
}
A.finish({ control: discA, shifted: discB, shifts, frames: FRAMES, framesCompared: compared, identical: true,
           cycles: [A.s.elapsedCycles, B.s.elapsedCycles] }, true, { samples: compared });
