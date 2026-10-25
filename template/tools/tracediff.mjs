// tracediff.mjs - the relocation proof, second half: the first INSTRUCTION where a
// shifted build stops behaving like its control, named in both builds' symbols.
//
// beeb-port-kit template, MIT, Kieran Connell 2026. From Stryker's Run's
// tools/tracediff.mjs (2026-10-03 on), which named its BUGS #1 and #2 at the
// instruction; its SHIFT argument and hand-written segments are replaced by
// relocate.mjs's label map, read off the two symbol dumps.
//
//   node tools/tracediff.mjs CONFIG CONTROL.ssd SHIFTED.ssd [--start LABEL | --at FRAME]
//        [--max CYCLES] [--seed S]
//
// The pair is lockstep.mjs's (it says why it must be whole pages and padded to the
// same sizes). Both boot alike and run to the start: the config's relocate.entry
// label (default; each build's own address for it), --start LABEL, or with --at F
// lockstep's input played to frame F in both - for a divergence lockstep found in
// play. From there, a field at a time with lockstep's input, every instruction's PC
// is recorded with the paging (ROMSEL's bank and ANDY bit), each SHIFTED build's PC
// matched against the control's by the labels below them (relocate.mjs pcMatcher), and
// between the instructions every write to relocate.writes' ranges (default: the
// compare ranges) as address and value. The streams are compared as they grow: a
// PC that differs is control flow that went another way; a write that differs with
// the same control flow is a data address that did not move with its target.
//
// At the first difference the shifted machine is stopped there, the control is put
// back to the field's start and replayed to the same entry, and the instructions
// before it are printed with both builds' names, the zero page bytes that differ,
// and both register sets. Exit 1 then; 0 if --max cycles (400,000,000) pass with
// none; 2 for a usage error, a name not in a dump, or a pair that is not whole pages.
import { open } from "./harness.mjs";
import { burstKeys, DEFAULT_SCRIPT, keyOf, loadConfig } from "./passplay.mjs";
import { pageShifts, pcMatcher } from "./relocate.mjs";

const args = process.argv.slice(2);
const opt = (flag, d) => { const i = args.indexOf(flag); if (i < 0) return d; return args.splice(i, 2)[1]; };
const START = opt("--start", null), AT = opt("--at", null);
const MAX = parseInt(opt("--max", "400000000"), 10), SEED = parseInt(opt("--seed", "1"), 10);
const [cfgPath, discA, discB] = args;
if (!discB) { console.error("usage: node tools/tracediff.mjs CONFIG CONTROL.ssd SHIFTED.ssd [--start LABEL | --at FRAME] [--max CYCLES] [--seed S]"); process.exit(2); }
let cfg;
try { cfg = await loadConfig(cfgPath); } catch (e) { console.error(`tracediff: ${e.message}`); process.exit(2); }
const R = cfg.relocate || {};

const A = await open({ name: "tracediff", disc: discA, banks: cfg.banks });
const B = await open({ name: "tracediff", disc: discB, banks: cfg.banks });
for (const h of [A, B]) h.model = cfg.model || (h.define("MASTER") ? "Master" : "B-DFS1.2");
const shifts = pageShifts(A, B);
const rng = (list) => list.map(([lo, len]) => { const a = A.addr(lo); return [a, a + (typeof len === "string" ? A.addr(len) : len) - 1]; });
// relocate.writes are [lo, hi] (inclusive); relocate.compare [at, len]
const tracked = R.writes ? R.writes.map(([lo, hi]) => [A.addr(lo), A.addr(hi)]) : rng(R.compare || []);
if (!tracked.length) A.die("the config gives no relocate.writes or relocate.compare ranges to trace writes in");

// lockstep's input, by frame
const ev = new Map();
const at = (f, e) => { if (!ev.has(f)) ev.set(f, []); ev.get(f).push(e); };
const presses = cfg.start?.presses || [];
for (const [f, k, n = 40] of presses) { at(f, ["down", k]); at(f + n, ["up", k]); }
const per = R.framesPerPass ?? 2, spec = cfg.script || DEFAULT_SCRIPT;
const playFrom = R.playFrom ?? (presses.length ? Math.max(...presses.map(([f, , n = 40]) => f + n)) + 100 : 100);
const byFrame = burstKeys(1_000_000, SEED, { ...spec, hold: spec.hold.map((v) => v * per), gap: spec.gap.map((v) => v * per) });
let held = [];
const input = (f) => {
    for (const [what, k] of ev.get(f) || []) for (const h of [A, B]) (what === "down" ? h.keyDownRaw : h.keyUpRaw)(keyOf(h, cfg, k));
    if (f < playFrom) return;
    const want = byFrame[f - playFrom] || [];
    for (const h of [A, B]) {
        for (const k of held) if (!want.includes(k)) h.keyUpRaw(keyOf(h, cfg, k));
        for (const k of want) if (!held.includes(k)) h.keyDownRaw(keyOf(h, cfg, k));
    }
    held = want;
};

for (const h of [A, B]) await h.boot({ settle: 0, ...(cfg.boot || {}) });
let frame = A.frames;
const fc0 = A.s.frameCount - A.frames;
if (AT !== null) {
    for (frame = A.frames + 1; frame <= +AT; frame++) { input(frame); await A.s.runFrames(1); await B.s.runFrames(1); }
    frame = +AT;
    console.error(`tracediff: at frame ${AT}`);
} else {
    const label = START || R.entry;
    if (!label) A.die("no start: give --start LABEL or --at FRAME, or relocate.entry in the config");
    for (const h of [A, B]) {
        const g = h.gateOf(label);
        if ((await h.runTo(h.need(label), 400_000_000, g)) === null) h.die(`${h.disc}: never reached ${label}`, { gaveUp: h.gaveUp });
    }
    frame = A.s.frameCount - fc0;           // the fields since the BREAK, for the input by frame
    console.error(`tracediff: start ${label}: &${A.need(label).toString(16)} / &${B.need(label).toString(16)}, frame ${frame}`);
}
console.error(`tracediff: at start: cycles ${A.s.elapsedCycles} / ${B.s.elapsedCycles}`);

const cpuA = A.cpu, cpuB = B.cpu;
const master = !!cpuA.model.isMaster;
const same = pcMatcher(A, B, { master });
const paging = (c) => (c.romsel & 0x0f) | (master && (c.romsel & 0x80) ? 0x10 : 0);
const WRITE = 0x40000000;
const inTracked = (a) => tracked.some(([lo, hi]) => a >= lo && a <= hi);
const ta = [], tb = [];
// one stream entry: an instruction (pc | paging << 16, with ACCCON's Y bit beside it
// for naming) or a write (WRITE | address << 8 | value)
const match = (ea, eb) => {
    if ((ea & WRITE) || (eb & WRITE)) return ea === eb;
    if ((ea >>> 16) !== (eb >>> 16)) return false;           // the paging differs
    const pg = ea >>> 16, romsel = (pg & 0x0f) | (pg & 0x10 ? 0x80 : 0);
    return same(ea & 0xffff, eb & 0xffff, romsel, cpuA.acccon);
};
let haltB = false, diverged = -1, replayTo = -1;
// the control runs each field first; the shifted then checks itself against it as it
// goes and halts AT the first entry that differs (before an instruction; just after
// a write). The control is then put back and replayed to the same entry.
cpuA.debugInstruction.add((pc) => {
    if (replayTo >= 0 && ta.length >= replayTo) return true;
    ta.push(pc | paging(cpuA) << 16);
    return replayTo >= 0 && ta.length > replayTo;
});
cpuA.debugWrite.add((a, v) => { if (inTracked(a)) ta.push(WRITE | a << 8 | v); return false; });
cpuB.debugInstruction.add((pc) => {
    if (haltB) return true;
    tb.push(pc | paging(cpuB) << 16);
    const i = tb.length - 1;
    if (i < ta.length && !match(ta[i], tb[i])) { diverged = i; return true; }
    return false;
});
cpuB.debugWrite.add((a, v) => {
    if (!inTracked(a)) return false;
    tb.push(WRITE | a << 8 | v);
    const i = tb.length - 1;
    if (i < ta.length && !match(ta[i], tb[i])) { diverged = i; haltB = true; }
    return false;
});
const hex = (v, w = 4) => "&" + v.toString(16).toUpperCase().padStart(w, "0");
// an entry named in its own build's symbols
const line = (h, e) => {
    if (e & WRITE) return `      write ${hex((e >> 8) & 0xffff)} = ${hex(e & 0xff, 2)}`;
    const pc = e & 0xffff, pg = e >>> 16, romsel = (pg & 0x0f) | (pg & 0x10 ? 0x80 : 0);
    const nm = h.symAt(pc, { romsel, acccon: h.cpu.acccon }) ?? "?";
    return `   ${hex(pc)} b${pg & 15}${pg & 0x10 ? "+andy" : ""}  ${nm}`;
};

let total = 0, done = 0, fields = 0;
while (done < MAX) {
    frame++; fields++;
    input(frame);
    const snapA = A.s.snapshot({ includeRoms: false });
    const c0 = A.s.elapsedCycles;
    await A.s.runFrames(1);
    await B.s.runFrames(1);
    done += A.s.elapsedCycles - c0;
    if (diverged >= 0) {
        const i = diverged, before = ta.slice(Math.max(0, i - 40), i), at = ta[i], bt = tb[i];
        A.s.restore(snapA);
        ta.length = 0; replayTo = (at & WRITE) ? i + 1 : i;
        await A.s.runFrames(1);
        const za = A.rd(0, 256), zb = B.rd(0, 256), zd = [];
        for (let z = 0; z < 256; z++) if (za[z] !== zb[z]) zd.push(`${hex(z, 2)}:${za[z].toString(16)}/${zb[z].toString(16)}`);
        console.error(`tracediff: first divergence in field ${fields} from the start${AT !== null ? ` (frame ${frame})` : ""}, ${total + i} entries and ${done} cycles in; before it (the control's):`);
        for (const e of before) console.error(line(A, e));
        console.error(`=> control ${line(A, at)}`);
        console.error(`   shifted ${line(B, bt)}`);
        console.error(`stopped at: control ${A.symAt(cpuA.pc) ?? hex(cpuA.pc)}, shifted ${B.symAt(cpuB.pc) ?? hex(cpuB.pc)}${at & WRITE ? " (the instruction after the write)" : ""}`);
        A.finish({ control: discA, shifted: discB, shifts, firstDivergenceField: fields, ...(AT !== null ? { frame } : {}),
                   entries: total + i, cycles: done, control_at: line(A, at).trim(), shifted_at: line(B, bt).trim(),
                   stoppedAt: { control: A.symAt(cpuA.pc) ?? hex(cpuA.pc), shifted: B.symAt(cpuB.pc) ?? hex(cpuB.pc) }, zeroPageDiffers: zd,
                   registers: { control: A.s.registers(), shifted: B.s.registers() } }, false, { samples: total + i });
    }
    total += ta.length;
    ta.length = 0; tb.length = 0;
    if (fields % 250 === 0) console.error(`tracediff: field ${fields}: ${total} entries identical`);
}
A.finish({ control: discA, shifted: discB, shifts, cycles: done, entries: total, identical: true }, true, { samples: total });
