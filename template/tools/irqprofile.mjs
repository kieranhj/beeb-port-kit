// irqprofile.mjs - what each interrupt costs, by the source it serviced and by where its cycles
// went, in the running build.
//
// beeb-port-kit template, MIT, Kieran Connell 2026. From Stryker's Run's tools/irqprofile.mjs
// (2026-10-12, its step 2 layer 1): it found that the MOS took 21.0% of the CPU in play - the
// 100 Hz tick 16.0% (sound 6.8%, the keyboard scan 6.3% while a key is held), a User VIA timer
// the MOS did not recognise 2.8% (offered to every paged ROM as service call 5, 1,165 cycles
// each) - which is what owning the interrupt was then costed against (21.0% to 10.6%).
//
//   node tools/irqprofile.mjs DISC [--from 0] [--fields 1000] [--keys SPEC] [--model M] [--json OUT.json]
//
// Boots DISC (harness.mjs; MODEL default Master if the build defines MASTER=1, else B-DFS1.2),
// runs --from fields with the --keys schedule (tools/keyscript.mjs; fields counted from the end
// of the boot) and then follows every interrupt for --fields fields, from the first instruction at
// the CPU's IRQ vector (&FFFE, read through the CPU, so the MOS's own entry) to the instruction
// after the RTI that ends it, charging its cycles to:
//   serviced  the VIA flags it CLEARED - (IFR & IER) at entry, less IFR after the RTI: "sys CA1
//             vsync", "sys T1", "usr T1"... What was actually serviced, not what the code meant
//             to; "nothing cleared" is an interrupt whose source was left pending (or a BRK)
//   region    where the cycles went: below &8000 the nearest label in the build's symbol dump;
//             a sideways bank by number and page ("bank 4 &90xx"; ANDY on a Master as "ANDY");
//             the MOS by the innermost subroutine called since the interrupt began ("MOS sub
//             &F416", looked up in the ROM by hand), or its page where no JSR was made
// NESTING. The MOS re-enables interrupts inside its 100 Hz tick (MOS 3.20: CLI at &E720, around
// its sound processing), so a vsync can be taken inside a tick. The tool keeps a stack and charges
// each interrupt only its own cycles, the outer one paused while an inner one runs; `nested` counts
// those taken inside another.
// Cycles are the CPU's own counter. The 7-cycle entry sequence is charged to the instruction it
// interrupted, so a handler's cost is a little under what a breakpoint pair would say.
//
// One JSON line on stdout (the share of all cycles in interrupts, each source's count, mean and
// share, its regions); the table on stderr; --json the same with every region. Exit 0 if any
// interrupt was followed, 1 if none was (an interrupt profile of nothing proves nothing), 2 if it
// could not run.
//
// Measured 2026-10-25, jsbeeb 2.10.2 (the commit has the full numbers): the template's
// build/game.ssd, and Stryker's Run's original (build/strykers-original.ssd) and shipping build
// in play, against its docs/step2-layer1.md.
//
// Also a module: `new IrqTracker(cpu, regionOf)` and `tracker.step(pc, opcode, cycles)` from a
// harness's own debugInstruction hook, `tracker.depth` > 0 inside an interrupt (pcprof.mjs).
import { readFileSync, writeFileSync } from "node:fs";
import { pathToFileURL } from "node:url";

const SYS_BITS = ["CA2 keyboard", "CA1 vsync", "SR", "CB2 lightpen", "CB1 ADC", "T2", "T1"];
const USR_BITS = ["CA2", "CA1", "SR", "CB2", "CB1", "T2", "T1"];
export function describeFlags(sys, usr) {
    const out = [];
    for (let b = 0; b < 7; b++) if (sys & (1 << b)) out.push(`sys ${SYS_BITS[b]}`);
    for (let b = 0; b < 7; b++) if (usr & (1 << b)) out.push(`usr ${USR_BITS[b]}`);
    return out.length ? out.join(" + ") : "nothing cleared";
}

const flags = (via) => { via._catchUp(); return via.ifr & 0x7f; };
const pending = (via) => { via._catchUp(); return via.ifr & via.ier & 0x7f; };

/** Interrupts followed from the vector to the RTI, nesting kept as a stack. */
export class IrqTracker {
    constructor(cpu, regionOf = () => "?") {
        this.cpu = cpu;
        this.regionOf = regionOf;
        this.vector = cpu.readmem(0xfffe) | (cpu.readmem(0xffff) << 8);
        this.stack = [];
        this.byKey = new Map();
        this.inIrq = 0;
        this.last = null;            // { opcode, cycles, region }
    }
    get depth() { return this.stack.length; }
    /** Call before each instruction runs, with the CPU's cycle count. */
    step(pc, opcode, c) {
        const top = this.stack[this.stack.length - 1], last = this.last;
        if (top && last && last.region !== null) {
            top.own += c - last.cycles;
            top.regions.set(last.region, (top.regions.get(last.region) || 0) + (c - last.cycles));
        }
        if (top && last) {
            if (last.opcode === 0x40) this.finish(this.stack.pop());     // the instruction after an RTI
            else if (last.opcode === 0x20) top.calls.push(pc);           // just entered a subroutine
            else if (last.opcode === 0x60 && top.calls.length) top.calls.pop();
        }
        if (pc === this.vector) {
            const m = this.cpu;
            this.stack.push({ own: 0, sys: pending(m.sysvia), usr: pending(m.uservia), regions: new Map(), calls: [],
                              nested: this.stack.length > 0 });
        }
        const cur = this.stack[this.stack.length - 1];
        let region = null;
        if (cur) {
            if (pc >= 0xc000 && !(this.cpu.model.isMaster && pc < 0xe000 && (this.cpu.acccon & 0x08))) {
                const sub = cur.calls.length ? cur.calls[cur.calls.length - 1] : null;
                region = sub !== null && sub >= 0xc000 ? `MOS sub &${hex(sub)}` : `MOS &${hex(pc >> 8, 2)}xx (no sub)`;
            } else region = this.regionOf(pc);
        }
        this.last = { opcode, cycles: c, region };
    }
    finish(r) {
        const m = this.cpu;
        const key = describeFlags(r.sys & ~flags(m.sysvia), r.usr & ~flags(m.uservia));
        const k = this.byKey.get(key) || { count: 0, cycles: 0, nested: 0, regions: new Map() };
        k.count++; k.cycles += r.own; k.nested += r.nested ? 1 : 0; this.inIrq += r.own;
        for (const [g, n] of r.regions) k.regions.set(g, (k.regions.get(g) || 0) + n);
        this.byKey.set(key, k);
    }
}
const hex = (n, w = 4) => n.toString(16).toUpperCase().padStart(w, "0");

/** The CPU's cycle counter, exact inside a run (elapsedCycles is only brought up to date between runs). */
export const cpuCycles = (cpu) => cpu.currentCycles + cpu.cycleSeconds * 2000000;

/** A Baron symbol dump's LABELS as a sorted [address, name] list (scope prefixes dropped), and
 *  near(list, a): the nearest label at or below a, within `span` bytes, or null. Labels only:
 *  an assignment is a constant or a variable, not code. */
export function labelIndex(symbolsPath) {
    const doc = JSON.parse(readFileSync(symbolsPath, "utf8"));
    const out = new Map();
    const add = (k, v) => { if (typeof v === "number" && !out.has(v)) out.set(v, k.replace(/^(?:@\d+:\d+\.)+/, "")); };
    if (Number.isInteger(doc.format)) {
        for (const asm of doc.assemblies) for (const sec of asm.sections)
            for (const [k, v] of Object.entries(sec.labels || {})) add(k, v?.value);
    } else for (const syms of Object.values(doc)) for (const [k, v] of Object.entries(syms)) add(k, v);
    return [...out.entries()].sort((a, b) => a[0] - b[0]);
}
export function near(list, a, span = 0x400) {
    let lo = 0, hi = list.length - 1, best = -1;
    while (lo <= hi) { const mid = (lo + hi) >> 1; if (list[mid][0] <= a) { best = mid; lo = mid + 1; } else hi = mid - 1; }
    return best >= 0 && a - list[best][0] < span ? list[best] : null;
}

/** Where a PC's code is: the nearest label below &8000 or in HAZEL, a bank by number and page
 *  in &8000-&BFFF (a label there could be any bank's). Cached by PC and paging. */
export function regionNamer(h) {
    const labels = labelIndex(h.symbolsPath), cache = new Map();
    return (pc) => {
        const c = h.cpu;
        if (pc >= 0x8000 && pc < 0xc000) {
            if (c.model.isMaster && (c.romsel & 0x80) && pc < 0x9000) return `ANDY &${hex(pc >> 8, 2)}xx`;
            return `bank ${c.romsel & 15} &${hex(pc >> 8, 2)}xx`;
        }
        let r = cache.get(pc);
        if (r === undefined) {
            const l = near(labels, pc);
            r = l ? (pc >= 0xc000 ? `HAZEL ${l[1]}` : l[1]) : `&${hex(pc >> 8, 2)}xx`;
            cache.set(pc, r);
        }
        return r;
    };
}

async function main() {
    const { open } = await import("./harness.mjs");
    const { parseKeys, applyKeys } = await import("./keyscript.mjs");
    const args = process.argv.slice(2);
    const opt = (name, dflt) => { const i = args.indexOf(name); if (i < 0) return dflt; const v = args[i + 1]; args.splice(i, 2); return v; };
    const FROM = parseInt(opt("--from", "0"), 10), FIELDS = parseInt(opt("--fields", "1000"), 10);
    const KEYS = opt("--keys", ""), MODEL = opt("--model", null), JSON_OUT = opt("--json", null);
    const [disc] = args;
    if (!disc || !(FIELDS > 0)) {
        console.error("usage: node tools/irqprofile.mjs DISC [--from F] [--fields N] [--keys SPEC] [--model M] [--json OUT.json]");
        process.exit(2);
    }
    const h = await open({ name: "irqprofile", disc });
    h.model = MODEL || (h.define("MASTER") ? "Master" : "B-DFS1.2");
    let sched;
    try { sched = parseKeys(KEYS); } catch (e) { h.die(e.message); }
    await h.boot();
    let f = 0;
    for (; f < FROM; f++) { applyKeys(h.s, sched, f); await h.s.runFrames(1); }

    const cpu = h.cpu;
    const t = new IrqTracker(cpu, regionNamer(h));
    cpu.debugInstruction.add((pc, opcode) => { t.step(pc, opcode, cpuCycles(cpu)); return false; });
    const c0 = cpuCycles(cpu);
    for (let n = 0; n < FIELDS; n++, f++) { applyKeys(h.s, sched, f); await h.s.runFrames(1); }
    const total = cpuCycles(cpu) - c0;

    const pct = (n) => +(100 * n / total).toFixed(2);
    const rows = [...t.byKey.entries()].sort((a, b) => b[1].cycles - a[1].cycles);
    const sources = rows.map(([key, k]) => ({
        serviced: key, count: k.count, nested: k.nested, perField: +(k.count / FIELDS).toFixed(2),
        cycles: k.cycles, meanCycles: Math.round(k.cycles / k.count), pct: pct(k.cycles),
        regions: [...k.regions.entries()].sort((a, b) => b[1] - a[1]).map(([region, n]) => ({ region, cycles: n, pct: pct(n) })),
    }));
    console.error(`${disc}: fields ${FROM}-${FROM + FIELDS} on ${h.model}, ${total} cycles; IRQ vector &${hex(t.vector)}`);
    console.error(`in interrupts: ${t.inIrq} cycles = ${pct(t.inIrq)}%`);
    for (const r of sources) {
        console.error(`\n${r.serviced}: ${r.count} (${r.perField}/field, ${r.nested} nested), ${r.cycles} cycles = ${r.pct}%, mean ${r.meanCycles}`);
        for (const g of r.regions.slice(0, 12)) console.error(`    ${g.region.padEnd(36)} ${String(g.cycles).padStart(9)}  ${g.pct.toFixed(2).padStart(6)}`);
    }
    const report = { disc, from: FROM, fields: FIELDS, keys: KEYS || null, cycles: total, irqVector: `&${hex(t.vector)}`,
                     inInterrupts: t.inIrq, inInterruptsPct: pct(t.inIrq) };
    if (JSON_OUT) writeFileSync(JSON_OUT, JSON.stringify({ ...report, sources }, null, 1));
    const count = sources.reduce((a, r) => a + r.count, 0);
    h.finish({ ...report, sources: sources.map(({ regions, ...r }) => ({ ...r, top: regions.slice(0, 3) })) },
             count > 0, { samples: count });
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) await main();
