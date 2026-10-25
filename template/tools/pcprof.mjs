// pcprof.mjs - every instruction's cycles by its address, its bank and the phase it ran in, over
// a stretch of the running game: the weights tools/grind.py cuts its windows by, and the
// measurement its gate compares a change against.
//
// beeb-port-kit template, MIT, Kieran Connell 2026. From Stryker's Run's tools/pcprof.mjs
// (2026-10-17 to 10-25), which weighted and measured its micro-optimisation grind: a pass's work
// 43,036 -> 31,869 cycles over three rounds, every batch measured this way against its control.
//
//   node tools/pcprof.mjs DISC [--from 0] [--fields 500 | --passes N] [--pass LABEL]
//        [--wait LABEL:BYTES[,...]] [--keys SPEC] [--model M] [--out PC.json]
//
// Boots DISC (harness.mjs; MODEL default Master if the build defines MASTER=1, else B-DFS1.2),
// runs --from fields with the --keys schedule (tools/keyscript.mjs, fields from the end of the
// boot), then profiles. Each instruction's cycles (the CPU's counter, from it to the next) go to
//   phase  "irq" inside an interrupt (from the CPU's IRQ vector to the instruction after the RTI,
//          nesting kept: irqprofile.mjs's IrqTracker); "wait" in a --wait range (LABEL from the
//          symbol dump, BYTES long: the frame lock's spin, which a faster pass only lengthens);
//          else "run"
//   key    the address, as bank << 16 | address in &8000-&BFFF (the bank ROMSEL had paged, 16 for
//          ANDY on a Master), the plain address elsewhere (HAZEL included)
// With --pass LABEL a pass is an execution of LABEL (the main loop's top) and the profile runs from
// the first pass after --from for --passes passes; without it, a pass is a field and --fields
// fields are profiled. PC.json is {passes, fields, pc: {"phase:key": cycles}} - grind.py windows'
// --profile format. The JSON line on stdout has the cycles a pass by phase: `work` (run + irq: all
// but the wait) is grind.py's MEASURE field.
//
// DETERMINISM. Keys here are by FIELD. Two builds of different speed given keys by field play
// different games after the first key (Stryker's Run: 31 against 41 late frames on one seed),
// so a gate comparing a faster build against its control must feed keys by PASS - the pair
// harness's way. The template's game is frame-locked and its keys only scroll, so by field is
// the same game here; a port whose passes vary must key by pass before trusting a saving.
//
// Exit 0 with at least one pass profiled, 1 with none (--pass never reached), 2 could not run.
// Measured 2026-10-25, jsbeeb 2.10.2: the template's build/game.ssd, see the commit.
import { writeFileSync } from "node:fs";

import { open } from "./harness.mjs";
import { parseKeys, applyKeys } from "./keyscript.mjs";
import { IrqTracker, cpuCycles } from "./irqprofile.mjs";

const args = process.argv.slice(2);
const opt = (name, dflt) => { const i = args.indexOf(name); if (i < 0) return dflt; const v = args[i + 1]; args.splice(i, 2); return v; };
const FROM = parseInt(opt("--from", "0"), 10), FIELDS = parseInt(opt("--fields", "500"), 10);
const PASSES = parseInt(opt("--passes", "0"), 10), PASS = opt("--pass", null), WAIT = opt("--wait", "");
const KEYS = opt("--keys", ""), MODEL = opt("--model", null), OUT = opt("--out", null);
const [disc] = args;
if (!disc || (PASS && !(PASSES > 0))) {
    console.error("usage: node tools/pcprof.mjs DISC [--from F] [--fields N | --pass LABEL --passes N] [--wait LABEL:BYTES,...] [--keys SPEC] [--model M] [--out PC.json]");
    process.exit(2);
}
const h = await open({ name: "pcprof", disc });
h.model = MODEL || (h.define("MASTER") ? "Master" : "B-DFS1.2");
let sched;
try { sched = parseKeys(KEYS); } catch (e) { h.die(e.message); }
const passAt = PASS ? h.need(PASS) : null;
const waits = WAIT.split(",").filter(Boolean).map((w) => {
    const [l, n] = w.split(":");
    const a = h.need(l), len = parseInt(n || "1", 10);
    if (!(len > 0)) h.die(`--wait ${w}: say how many bytes, LABEL:BYTES`);
    return [a, a + len];
});
const inWait = (pc) => waits.some(([a, b]) => pc >= a && pc < b);

await h.boot();
let f = 0;
for (; f < FROM; f++) { applyKeys(h.s, sched, f); await h.s.runFrames(1); }

const cpu = h.cpu, master = cpu.model.isMaster;
const irq = new IrqTracker(cpu);
const pc = new Map();
const byPhase = { run: 0, wait: 0, irq: 0 };
let on = !PASS, passes = 0, lastKey = null, lastPhase = null, lastC = 0, stopAt = -1;
cpu.debugInstruction.add((at, opcode) => {
    const c = cpuCycles(cpu);
    irq.step(at, opcode, c);
    if (on && lastKey !== null) {
        pc.set(lastKey, (pc.get(lastKey) || 0) + c - lastC);
        byPhase[lastPhase] += c - lastC;
    }
    if (passAt !== null && at === passAt && irq.depth === 0 && c !== stopAt) {
        if (!on) on = true;                        // the first pass after --from starts the profile
        else if (++passes >= PASSES) { on = false; lastKey = null; stopAt = c; return true; }
    }
    if (on) {
        const phase = irq.depth ? "irq" : inWait(at) ? "wait" : "run";
        const key = at >= 0x8000 && at < 0xc000 ? (master && (cpu.romsel & 0x80) && at < 0x9000 ? 16 : cpu.romsel & 15) * 0x10000 + at : at;
        lastKey = `${phase}:${key}`; lastPhase = phase; lastC = c;
    }
    return false;
});
const f0 = f;
if (PASS) {
    const cap = FROM + Math.max(1000, PASSES * 20);           // a pass longer than 20 fields is a hang
    while (passes < PASSES && f < cap) {
        applyKeys(h.s, sched, f);
        await h.s.runFrames(1);
        if (passes < PASSES || on) f++;                      // stopped mid-field on the last pass
    }
} else {
    for (let n = 0; n < FIELDS; n++, f++) { applyKeys(h.s, sched, f); await h.s.runFrames(1); }
    on = false;
    passes = FIELDS;
}
const per = (n) => +(n / Math.max(1, passes)).toFixed(1);
const report = { disc, from: FROM, passLabel: PASS, passes, fields: f - f0, keys: KEYS || null,
                 perPass: { run: per(byPhase.run), wait: per(byPhase.wait), irq: per(byPhase.irq),
                            work: per(byPhase.run + byPhase.irq) },
                 addresses: pc.size };
if (OUT) writeFileSync(OUT, JSON.stringify({ disc, passes, fields: f - f0, pc: Object.fromEntries(pc) }));
console.error(`${disc}: ${passes} passes over ${f - f0} fields; a pass: run ${report.perPass.run}, ` +
              `wait ${report.perPass.wait}, irq ${report.perPass.irq} cycles${OUT ? ` -> ${OUT}` : ""}`);
h.finish(report, passes > 0 && (!PASS || passes >= PASSES), { samples: passes });
