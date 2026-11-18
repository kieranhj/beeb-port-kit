// harness_selftest.mjs - harness.mjs's helpers proved on the template's own build.
//
// beeb-port-kit template, MIT, Kieran Connell 2026. The helpers Stryker's Run's
// tools/playscript.mjs had and the kit's harness lacked (2026-10-25), each shown to
// do what it says on a build where the answer is known:
//
//   need       a scoped leaf (main_loop.step_left as step_left), name+N, an
//              assignment (SCROLL_STEP) and a ZA_AUTO, all from the dump
//   keyDownRaw a key by the build's own internal number (KEY_RIGHT, from the dump):
//              the scroll moves by SCROLL_STEP a pass while it is held
//   callFrom   a JSR faked from the stopped CPU: keydown_int called with X = the
//              key, back at the instruction it was stopped on, the stack as it was
//   refusal    a hook in &8000-&BFFF with no bank, and on a Master one in &C000-&DFFF
//              with no HAZEL gate, THROWS (anyBank: true is the way to say any will do)
//   symAt      a PC in a bank named only from a section the banks map puts there
//   hang       where(), the trail by label, and the first-bad watch
// From the phX port, 2026-11:
//   runUntil   run on until field_count reaches a value (RUN_UNTIL's helper)
//   parse      parseCond / parsePress / cli, on known strings
//   --junk     JUNK=seed: three boots, two with one seed and one with another;
//              the template must boot and run under each, the same seed must leave
//              the same RAM after the same fields and the other seed other RAM
//
//   node tools/harness_selftest.mjs build/game-master.ssd     (or build/game.ssd)
//   node tools/harness_selftest.mjs build/game.ssd --junk=1234
//   exit 0 every check held; 1 one did not; 2 could not judge
import { createHash } from "node:crypto";

import { cli, labelAt, open, parseCond, parsePress } from "./harness.mjs";

const { pos, opt } = cli();
const disc = pos[0];
if (!disc) { console.error("usage: node tools/harness_selftest.mjs DISC [--junk=SEED]"); process.exit(2); }

if (opt.junk !== undefined) {
    // each boot in its own harness (open() is cheap; the machines are separate)
    const seed = +opt.junk || 1;
    const run = async (s) => {
        const h = await open({ name: "harness_selftest junk", disc });
        h.model = h.define("MASTER") ? "Master" : "B-DFS1.2";
        await h.boot({ field: h.zp("field_count"), junk: String(s) });
        if ((await h.runTo(h.need("main_loop"), 400_000)) === null) h.die("never reached main_loop", { gaveUp: h.gaveUp });
        await h.s.runFrames(50);
        // all of main RAM below the screen, and zero page: what the fill touched
        const sum = createHash("sha256").update(Buffer.from(h.rd(0, 0x3000))).digest("hex").slice(0, 16);
        return { seed: s, regions: h.junked?.regions, sum, h };
    };
    const a = await run(seed), b = await run(seed), c = await run(seed + 1);
    const same = a.sum === b.sum, other = a.sum !== c.sum;
    const wrong = [];
    if (!same) wrong.push(`seed ${seed} twice: ${a.sum} and ${b.sum}`);
    if (!other) wrong.push(`seeds ${seed} and ${seed + 1} both ${a.sum}: the fill reached nothing`);
    a.h.finish({ junk: [a, b, c].map(({ seed, regions, sum }) => ({ seed, regions, sum })), wrong },
               same && other, { samples: 3 });
}
const h = await open({ name: "harness_selftest", disc });
h.model = h.define("MASTER") ? "Master" : "B-DFS1.2";
const wrong = [], ok = (what, cond, got) => { if (!cond) wrong.push(`${what}: ${JSON.stringify(got)}`); };

// names
const LOOP = h.need("main_loop"), STEP = h.asmConst("SCROLL_STEP");
ok("step_left is main_loop.step_left", h.need("step_left") === h.need("main_loop.step_left"), h.need("step_left"));
ok("name+N", h.need("main_loop+3") === LOOP + 3 && h.need("main_loop+&10") === LOOP + 16, h.need("main_loop+3"));
ok("an assignment", h.need("SCROLL_STEP") === 8, h.need("SCROLL_STEP"));
const SCROLL = h.zp("scroll"), FIELD = h.zp("field_count");

await h.boot({ field: FIELD });
h.keepTrail(32);
h.watchBad();

// refusal of an ungated hook in a switched window
let threw = 0;
try { h.onExec(0x8123, () => false); } catch { threw++; }
if (h.cpu.model.isMaster) { try { h.onExec(0xc123, () => false); } catch { threw++; } }
const off = h.onExec(0x8123, () => false, { anyBank: true }); off();
ok("ungated hooks refused", threw === (h.cpu.model.isMaster ? 2 : 1), threw);

// stop at the loop, then a key by the build's own number
if ((await h.runTo(LOOP, 400_000)) === null) h.die("never reached main_loop", { gaveUp: h.gaveUp });
const s0 = h.word(SCROLL);
h.keyDownRaw("KEY_RIGHT");
let passes = 0;
const offPass = h.onExec(LOOP, () => { passes++; return false; });
await h.s.runFrames(20);
offPass();
h.keyUpRaw("KEY_RIGHT");
const moved = (h.word(SCROLL) - s0 + 10240) % 10240;
ok("KEY_RIGHT by matrix moves the scroll SCROLL_STEP a pass", passes >= 5 && (moved === STEP * passes || moved === STEP * (passes - 1)), { moved, passes });

// callFrom: keydown_int with X = KEY_LEFT (not held: N clear), back at the loop
await h.s.runFrames(2);
if ((await h.runTo(LOOP, 400_000)) === null) h.die("never reached main_loop", { gaveUp: h.gaveUp });
const sp = h.cpu.s;
h.callFrom("keydown_int", { x: h.need("KEY_LEFT") });
ok("callFrom set the PC", h.cpu.pc === h.need("keydown_int"), h.cpu.pc);
const back = await h.runTo(LOOP, 20_000);
ok("callFrom returned to the stopped instruction, stack as it was", back !== null && h.cpu.s === sp, { back, s: h.cpu.s, sp });

// symAt with a bank map, on the template's labels: a label put in bank 5 names a PC
// only while bank 5 is paged
const banked = [{ name: "in_bank5", raw: "in_bank5", value: 0x8100, sections: ["B5"] },
                { name: "in_bank4", raw: "in_bank4", value: 0x8100, sections: ["B4"] }];
const at = (romsel) => labelAt(banked, 0x8105, { banks: { B4: 4, B5: 5 }, romsel })?.[0].name;
ok("bank-aware names", at(5) === "in_bank5" && at(4) === "in_bank4" && at(6) === undefined, [at(4), at(5), at(6)]);

// runUntil: on to field_count + 7 (a byte that wraps: the target is taken mod 256)
const fc0 = h.byte(FIELD), want = (fc0 + 7) & 0xff;
const ran = await h.runUntil(`field_count==${want}`, { budget: 20 });
ok("runUntil stops where the symbol reaches the value", h.byte(FIELD) === want && ran >= 6 && ran <= 8, { fc0, want, ran });

// the parsers, on strings whose answers are known
const pc = parseCond("row:sw>=-2"), pp = parsePress("SPACE@dc_secs?"), pk = parsePress("98@flag:w==&10");
ok("parseCond", pc.sym === "row" && pc.size === "sw" && pc.op === ">=" && pc.value === -2, pc);
ok("parsePress", pp.key === "SPACE" && pp.cond.op === "!=" && pp.clear && pp.optional &&
   pk.key === 98 && pk.cond.value === 16 && !pk.clear, [pp, pk]);

const hang = h.hang();
ok("hang() names the PC and keeps a trail", !!hang.at && hang.trail.length > 0 && hang.firstBad === null, hang);
h.finish({ checks: 12, wrong, keyRun: { moved, passes }, where: { at: hang.at, trail: hang.trail.slice(-3) } }, wrong.length === 0, { samples: 12 });
