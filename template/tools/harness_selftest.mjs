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
//
//   node tools/harness_selftest.mjs build/game-master.ssd     (or build/game.ssd)
//   exit 0 every check held; 1 one did not; 2 could not judge
import { labelAt, open } from "./harness.mjs";

const disc = process.argv[2];
if (!disc) { console.error("usage: node tools/harness_selftest.mjs DISC"); process.exit(2); }
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

const hang = h.hang();
ok("hang() names the PC and keeps a trail", !!hang.at && hang.trail.length > 0 && hang.firstBad === null, hang);
h.finish({ checks: 9, wrong, keyRun: { moved, passes }, where: { at: hang.at, trail: hang.trail.slice(-3) } }, wrong.length === 0, { samples: 9 });
