// record_vscroll.mjs - RECORD / REPLAY: the running port's every pass and every
// CRTC write, recorded in jsbeeb, replayed through a Python model of the spec.
//
// beeb-port-kit template example, MIT, Kieran Connell 2026. The worked example of
// ../../../../docs/verification.md's record/replay procedure, after 1942's
// verify_turner.mjs + check_turner.py, verify_class2, verify_side and verify_sound:
// the harness records, the model judges, and ONE COMMAND IS ONE VERDICT - this
// spawns check_vscroll.py on its own trace and exits with the model's exit code.
//
// verify_vscroll.mjs proves the PICTURE at twenty fields. This proves the LOGIC on
// every pass of a driven run: that each pass moves `ypos` as the keys say, wrapping
// at both ends of the ring, and that every take writes the CRTC exactly what that
// position means - R12/R13 the row's address, R5 = 8 - line in the VSync hook and
// R5 = line at fire 2. Nothing is sampled by time; everything is hooked:
//
//   pass   onExec(main_loop)            ypos as the pass found it, the keys held
//   park   onExec(main_loop.wait_take)  ypos as the pass left it (first hit a pass)
//   field  onExec(rupt_vsync)           a field begins: the take happens here
//   crtc   onWrite(&FE00-&FE01)         register and value, and which handler wrote it
//
// check_vscroll.py RE-SEEDS THE MODEL FROM THE PORT EVERY PASS - each step starts from
// the ypos the port had, not the model's own last answer - so a wrong step is reported
// at the pass it happened and does not smear over every pass after it.
//
// THE RUN IS DRIVEN, and its length is part of what it covers: idle, DOWN for 140
// passes (all eight lines, the wrap 127 -> 0), UP for 140 (0 -> 127), both keys at
// once. The model FAILS a run that did not take each of those paths.
//
//   node examples/vscroll/tools/record_vscroll.mjs examples/vscroll/build/vscroll.ssd
//   MUTATE=adj ...     the NEGATIVE CONTROL: pokes adj_of_line[3] from 5 to 4 after the
//                      boot. The model must FAIL it - an oracle never seen failing has
//                      not been shown able to (docs/verification.md). verify_cmds.py
//                      prints both, the mutant with "expect": 1.
//   OUT=<file>         the trace (default: the build directory, beside the disc)
//   PYTHON=<exe>       the interpreter (default python on Windows, python3 elsewhere)
import { writeFileSync } from "node:fs";
import { spawnSync } from "node:child_process";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { open } from "../../../tools/harness.mjs";

const [disc] = process.argv.slice(2);
if (!disc) {
    console.error("usage: node examples/vscroll/tools/record_vscroll.mjs DISC");
    process.exit(2);
}
const h = await open({ name: "record_vscroll", disc, model: process.env.MODEL || "B-DFS1.2" });
const MAIN_LOOP = h.need("main_loop"), WAIT_TAKE = h.need("main_loop.wait_take");
const VSYNC = h.need("rupt_vsync"), TIMER = h.need("rupt_timer"), TIMER_END = h.need("rupt_timer.done");
const YPOS = h.zp("ypos"), FIELD = h.zp("field_count"), ADJ_OF_LINE = h.need("adj_of_line");
const spec = { BUF_BASE: h.asmConst("BUF_BASE"), ROW_BYTES: h.asmConst("ROW_BYTES"),
               BUF_ROWS: h.asmConst("BUF_ROWS") };
const OUT = process.env.OUT || join(dirname(disc), `vscroll_trace${process.env.MUTATE ? "_" + process.env.MUTATE : ""}.json`);

await h.boot({ field: FIELD });
if (process.env.MUTATE === "adj") h.wr(ADJ_OF_LINE + 3, [4]);   // main RAM below &3000: no bank to name
else if (process.env.MUTATE) h.die(`MUTATE=${process.env.MUTATE}: only "adj" is defined`);

const held = { up: 0, down: 0 };
const press = (k, on) => { held[k] = on ? 1 : 0; (on ? h.s.keyDown : h.s.keyUp).call(h.s, k === "up" ? h.keys.UP : h.keys.DOWN); };
const ev = [];
let parked = true;                      // the first pass we see is mid-flight: skip to a top
let started = false;
h.onExec(MAIN_LOOP, () => {
    started = true; parked = false;
    ev.push({ t: "pass", y: h.byte(YPOS), up: held.up, down: held.down });
});
h.onExec(WAIT_TAKE, () => {
    if (!started || parked) return;
    parked = true;
    ev.push({ t: "park", y: h.byte(YPOS) });
});
h.onExec(VSYNC, () => { if (started) ev.push({ t: "field" }); });
let reg = -1;
h.onWrite(0xfe00, 0xfe01, (addr, val, c) => {
    if (addr === 0xfe00) { reg = val; return; }
    if (!started) return;
    const by = c.pc >= VSYNC && c.pc < TIMER ? "vsync" : c.pc >= TIMER && c.pc <= TIMER_END ? "timer" : "other";
    ev.push({ t: "crtc", r: reg, v: val, by });
});

// THE DRIVE. 50 Hz (FRAME_LOCK = 1): one pass a field.
await h.s.runFrames(20);                                    // idle
press("down", true); await h.s.runFrames(140); press("down", false);
await h.s.runFrames(10);
press("up", true); await h.s.runFrames(140);
press("down", true); await h.s.runFrames(6);                // both: dec then inc, no move
press("down", false); press("up", false);
await h.s.runFrames(10);

writeFileSync(OUT, JSON.stringify({ spec, mutate: process.env.MUTATE || null, events: ev }));
const py = process.env.PYTHON || (process.platform === "win32" ? "python" : "python3");
const here = dirname(fileURLToPath(import.meta.url));
const chk = spawnSync(py, [join(here, "check_vscroll.py"), OUT], { encoding: "utf8" });
process.stderr.write(chk.stderr || "");
if (chk.error || chk.status === null) h.die(`could not run ${py} check_vscroll.py: ${chk.error || "killed"}`);
let verdict = {};
try { verdict = JSON.parse(chk.stdout.trim().split("\n").pop()); } catch { h.die("check_vscroll.py printed no JSON verdict"); }
h.finish({ trace: OUT, events: ev.length, model_: verdict }, chk.status === 0, { samples: verdict.judged ?? 0 });
