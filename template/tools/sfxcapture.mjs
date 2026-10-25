// sfxcapture.mjs - each sound effect as the MOS plays it: the SN76489 writes, by MOS
// centisecond tick from the SOUND call, from silence. The input py/beeb_port_kit/sfx50.py fits
// lib/sfx50.6502's 50 Hz ramps to.
//
//   node tools/sfxcapture.mjs EFFECTS.json OUT.json [--model Master|B-DFS1.2] [--fields N] [--pairs]
//
// EFFECTS.json - the original's own ENVELOPE and SOUND parameters, as BASIC writes them:
//   { "envelopes": [[N, T, PI1, PI2, PI3, PN1, PN2, PN3, AA, AD, AS, AR, ALA, ALD], ...],
//     "effects": [ { "name": "bullet", "what": "firing a bullet", "sound": [C, A, P, D] }, ... ] }
// envelopes are OSWORD 8's 14 bytes (ENVELOPE's 14 numbers; negatives as their byte);
// a sound is OSWORD 7's four words, SOUND C, A, P, D (A negative for a volume, -15 loudest;
// 1-16 an envelope; C may carry &10 flush / &x00 hold-sync bits). "name" becomes the label
// (sfx_effect_NAME); the effects are numbered in this order (request E + 1).
//
// HOW. A machine is booted to BASIC (no disc), a two-instruction stub put at STUB (CLI, then a
// JMP to itself) and CALLed. Each block is fired from the CPU stopped at the stub's JMP by a
// faked JSR to OSWORD (A = 7 or 8, X/Y the block): the return address pushed, PC set, nothing
// written but the stack and the block. The MOS's tick is System VIA T1 (100 Hz); each chip write
// is put in the tick it falls in (below: the ticks are a grid), counted from the first tick
// after the call. Each effect starts from silence: the sound
// queues flushed (OSBYTE 15) and a quarter of --fields of quiet before it; --fields fields
// (default 200, 4 s) are captured from the call.
//
// --pairs: every effect B fired 3, 9 and 25 ticks into every effect A on the same SOUND
// channel, and B's channel compared from B's start against B alone: where they differ, the MOS
// played B differently over A (its driver is stateful); lib/sfx50.6502 is not, a request
// replaces what the channel was playing. Stryker's Run's 8 effects, MOS 3.20: 27 of 48 pairs differ,
// fired from BASIC here (2026-10-25, 97 s) and in its game by its own tool once that put its ticks
// on this grid too (its BUGS #19; before, it counted entries and said 38).
//
// OUT.json: { model, tick_cycles: {period, entries, ticks, latency_max}, effects: [ { name, sound, chip_channel, what,
// writes: [[tick, byte], ...] }, ... ], pairs? } - sfx50.py's capture form (a list: request order).
//
// From Stryker's Run (Enhanced), tools/sfxcapture.mjs (decision 25, 2026-10-16), which fired the
// game's own play_sound from its pause loop; into the kit 2026-10-25 firing OSWORD 7/8 blocks
// from BASIC, so any original's SOUND and ENVELOPE numbers can be captured without the game.
// Fork this into your project's tools/; keep this header.
import { readFileSync, writeFileSync } from "node:fs";
import { loadMachineSession } from "./jsbeeb_src.mjs";

const args = process.argv.slice(2);
const opt = (k, d) => { const i = args.indexOf(k); return i < 0 ? d : args[i + 1]; };
const PAIRS = args.includes("--pairs");
const MODEL = opt("--model", "Master");
const FIELDS = Number(opt("--fields", 200));
const [cfgPath, outPath] = args.filter((a, i) => !a.startsWith("--") && !["--model", "--fields"].includes(args[i - 1]));
if (!cfgPath || !outPath) { console.error("usage: node tools/sfxcapture.mjs EFFECTS.json OUT.json [--model M] [--fields N] [--pairs]"); process.exit(2); }
const cfg = JSON.parse(readFileSync(cfgPath, "utf8"));

const STUB = 0x7000;            // free under BASIC with no program: below HIMEM, above PAGE
const BLOCK = 0x7010;           // the OSWORD block
const OSWORD = 0xfff1, OSBYTE = 0xfff4;
const chipChannel = (c) => ((c & 3) === 0 ? 3 : 3 - (c & 3));
const word = (v) => [v & 0xff, (v >> 8) & 0xff];

const MachineSession = await loadMachineSession();
const s = new MachineSession(MODEL, { tube: false });
await s.initialise();
await s.boot(30);
const cpu = s._machine.processor;
const cyc = () => cpu.currentCycles + cpu.cycleSeconds * 2000000;
s.writeMemory(STUB, [0x58, 0x4c, (STUB + 1) & 0xff, (STUB + 1) >> 8]);     // CLI : JMP *
await s.type(`CALL &${STUB.toString(16)}\r`);
const LOOP = STUB + 1;
const irq1v = () => { const v = s.readMemory(0x204, 2); return v[0] | (v[1] << 8); };

async function runToLoop(fields = 50) {
    let armed = true;
    const h = cpu.debugInstruction.add((pc) => armed && pc === LOOP);
    try {
        for (let i = 0; i < fields; i++) { await s.runFrames(1); if (cpu.pc === LOOP) return true; }
        return false;
    } finally { armed = false; h.remove(); }
}
/** The CPU stopped at the stub's JMP calls `target` as a JSR there would. */
function callFrom(target, a, x, y) {
    const ret = (cpu.pc - 1) & 0xffff;
    cpu.writemem(0x100 + cpu.s, ret >> 8); cpu.s = (cpu.s - 1) & 0xff;
    cpu.writemem(0x100 + cpu.s, ret & 0xff); cpu.s = (cpu.s - 1) & 0xff;
    cpu.a = a; cpu.x = x; cpu.y = y; cpu.pc = target;
}
async function call(target, a, x = 0, y = 0, bytes = null) {
    if (!(await runToLoop())) throw new Error("the CPU never came back to the stub");
    if (bytes) s.writeMemory(BLOCK, bytes);
    callFrom(target, a, x, y);
    const t = cyc();
    if (!(await runToLoop())) throw new Error("OSWORD/OSBYTE never returned");
    return t;
}

// chip writes and MOS ticks, logged only while `log` is set
const chip = cpu.soundChip, poke = chip.poke.bind(chip);
let log = null;
chip.poke = (v) => { if (log) log.push([cyc(), v]); return poke(v); };
const entries = [];             // IRQ1V entries with System VIA T1's flag up, while logging
// THE TICKS ARE A GRID, not the entries. T1 is free-running (continuous, period = latch + 2 at 1 MHz),
// so the MOS's ticks are exactly P cycles apart; but an entry with T1's flag up is not one a
// tick: an entry for another source can see the flag before the MOS takes it (two entries
// ~300 cycles apart), and the MOS can take T1 inside an entry made for another source (a gap
// of 2P). Measured 2026-10-25: from BASIC on MOS 3.20, 3,192 entries with the flag up for
// 1,176 ticks (counted one per 10,000 cycles instead, 8 gaps of 2P); through Stryker's Run's
// own handler, entries 300 cycles apart and gaps of 2P. So the entries only fix the phase:
// the earliest-serviced one, (entry - t0) mod P at its least, is the underflow. With the grid
// this tool's capture of Stryker's Run's 8 effects (its SOUND and ENVELOPE blocks fired from
// BASIC) puts every write on each effect's channel in the same tick as that game's own
// capture did, on a Master and on a B (MOS 1.20) alike, and sfx50.py makes the same 158 bytes.
const latch = s.readMemory(0xfe46, 2);
const P = ((latch[0] | (latch[1] << 8)) + 2) * 2;     // the VIA counts at 1 MHz, the CPU at 2
const IRQ = irq1v();
cpu.debugInstruction.add((pc) => {
    if (pc === IRQ && log && (s.readMemory(0xfe4d, 1)[0] & 0x40)) entries.push(cyc());
    return false;
});
const phaseCheck = { entries: 0, ticks: 0, latency_max: 0 };

function byTick(writes, t0) {
    const mod = (v) => ((v % P) + P) % P;
    const after = entries.filter((t) => t > t0);
    const ph = Math.min(...after.map((t) => mod(t - t0)));
    const first = t0 + ph;                 // the first underflow after t0
    const end = Math.max(...writes.map(([c]) => c), first);
    const n = Math.floor((end - first) / P) + 1;
    phaseCheck.entries += after.length; phaseCheck.ticks += n;
    phaseCheck.latency_max = Math.max(phaseCheck.latency_max, ...after.map((t) => mod(t - first)));
    const res = [];
    for (const [c, v] of writes) if (c >= t0) res.push([Math.floor((c - first) / P), v]);
    return res;
}
function states(list, n) {
    const r = { t0: 0x3ff, t1: 0x3ff, t2: 0x3ff, n: 0, v0: 15, v1: 15, v2: 15, v3: 15 };
    let latch = null, k = 0;
    const out = [];
    for (let t = 0; t < n; t++) {
        while (k < list.length && list[k][0] === t) {
            const v = list[k++][1];
            if (v & 0x80) {
                const ch = (v >> 5) & 3, vol = v & 0x10; latch = { ch, vol };
                if (vol) r["v" + ch] = v & 15; else if (ch === 3) r.n = v & 7; else r["t" + ch] = (r["t" + ch] & 0x3f0) | (v & 15);
            } else if (latch && !latch.vol && latch.ch < 3) r["t" + latch.ch] = (r["t" + latch.ch] & 15) | ((v & 63) << 4);
        }
        out.push({ ...r });
    }
    return out;
}

for (const e of cfg.envelopes || []) {
    if (e.length !== 14) throw new Error("an envelope is 14 numbers: " + JSON.stringify(e));
    await call(OSWORD, 8, BLOCK & 0xff, BLOCK >> 8, e.map((v) => v & 0xff));
}
const soundBlock = (e) => e.sound.flatMap(word);
async function quiet() { await call(OSBYTE, 15, 0); await s.runFrames(FIELDS / 4 | 0); }
async function fire(e) { return call(OSWORD, 7, BLOCK & 0xff, BLOCK >> 8, soundBlock(e)); }

const effects = {};
for (const e of cfg.effects) {
    await quiet();
    log = []; entries.length = 0;
    const t0 = await fire(e);
    await s.runFrames(FIELDS);
    effects[e.name] = { sound: e.sound, chip_channel: chipChannel(e.sound[0]), what: e.what || "", writes: byTick(log, t0) };
    log = null;
}
const tick = { period: P, ...phaseCheck };
const result = { model: MODEL, tick_cycles: tick, effects: cfg.effects.map((e) => ({ name: e.name, ...effects[e.name] })) };
if (PAIRS) {
    const report = [];
    for (const a of cfg.effects) for (const b of cfg.effects) {
        if ((a.sound[0] & 3) !== (b.sound[0] & 3)) continue;
        for (const gap of [3, 9, 25]) {
            await quiet();
            log = []; entries.length = 0;
            await fire(a); await s.runFrames(Math.ceil(gap / 2));
            const tb = await fire(b); await s.runFrames(FIELDS);
            const pair = byTick(log, tb); log = null;
            const N = 2 * FIELDS, alone = states(effects[b.name].writes, N), both = states(pair, N);
            const ch = chipChannel(b.sound[0]);
            const keys = ch === 3 ? ["n", "v3"] : ["t" + ch, "v" + ch];
            let firstDiff = null;
            for (let t = 1; t < N && !firstDiff; t++) for (const kk of keys) if (alone[t][kk] !== both[t][kk]) { firstDiff = { tick: t, reg: kk, alone: alone[t][kk], after: both[t][kk] }; break; }
            report.push({ a: a.name, b: b.name, gap, firstDiff });
        }
    }
    result.pairs = report;
    console.log(report.filter((r) => r.firstDiff).length, "of", report.length, "pairs differ");
}
writeFileSync(outPath, JSON.stringify(result));
console.log(MODEL, `T1 every ${P} cycles; ${phaseCheck.entries} entries for ${phaseCheck.ticks} ticks, latest ${phaseCheck.latency_max} after its underflow;`, Object.entries(effects).map(([k, v]) => `${k}: ${v.writes.length} writes over ${v.writes.length ? v.writes[v.writes.length - 1][0] + 1 : 0} ticks`).join("; "));
