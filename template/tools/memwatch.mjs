// memwatch.mjs - every write, read and execute at chosen addresses, in ANY harness's machines,
// by phase and by the instruction that made it - without a change to the harness.
//
// beeb-port-kit template, MIT, Kieran Connell 2026. From Stryker's Run's tools/zpwatch.mjs
// (2026-10-18, BUGS #12 there: the port's PRNG state at &92/&93 was also the original's scratch
// in a death routine; a watch over the front end and 30,000 fields of play had found no other
// user, because no harness had died - the watch proves only the paths the harness ran).
//
//   MEMWATCH=70-7f,0d00 [MEMWATCH_PHASES=play@main_loop,front@title] [MEMWATCH_BANKS=DATA1:4,...]
//   [MEMWATCH_OUT=build/memwatch.json] node --import ./tools/memwatch.mjs tools/ANY_HARNESS.mjs ARGS...
//
// It is loaded before the harness with node's --import and patches jsbeeb's MachineSession
// (the class jsbeeb_src.mjs loads, by the same URL, so the same module instance) so that every
// machine the harness gives a disc to (loadDisc) is watched from then on; two machines in a pair
// harness are reported apart.
//
//   MEMWATCH         hex addresses and ranges, comma-separated (a-b inclusive)
//   MEMWATCH_PHASES  NAME@WHERE,...: the phase becomes NAME when the instruction at WHERE runs.
//                    WHERE is a label in that disc's symbol dump (beside it, DISC.symbols.json)
//                    or a hex address (&1234 / 0x1234). Before any, the phase is "boot". Stryker's
//                    Run's were game@start_game,front@give_irq_back: its game, and the front end
//                    from the moment the game handed the interrupt back
//   MEMWATCH_BANKS   SECTION:BANK,...: the SECTIONs whose code runs in a sideways bank, so a PC in
//                    &8000-&BFFF is named from that bank's labels (sections nested inside one
//                    inherit it). Labels in &C000-&DFFF are taken as HAZEL's (a Master's, with
//                    ACCCON's Y bit set; otherwise the PC is the MOS's)
//   MEMWATCH_OUT     the JSON (default build/memwatch.json under the current directory)
//
// Each access is counted by machine, phase, kind and address with the PC of the instruction that
// made it and the nearest label before it in the code paged there: main RAM, the bank ROMSEL
// selects (ANDY on a Master below &9000 when ROMSEL bit 7 is set), HAZEL, or "MOS"/"ROM n".
// Kinds: "write", "read", "exec" (an instruction fetched from a watched address) and
// "harness-write" (the harness's own writeMemory; its readMemory is not counted). jsbeeb reports
// zero-page and stack reads with their address, so reads are counted by address only; writes are
// exact. The fields each phase ran (39,936 cycles each) are kept per machine. The file is written
// on process exit (a harness ending in process.exit still writes it); a summary of every access
// outside "boot" goes to stderr.
//
// A WATCH PROVES ONLY THE PATHS THE HARNESS TOOK. "No access in N fields" is a statement about
// those fields: run it under the harnesses that reach the rare paths (death, game over, the
// front end's every screen, a level's end) before calling an address free.
//
// OWNERS: A REGION THAT ONLY CERTAIN CODE MAY WRITE (from the phX port's hole_watch.mjs,
// 2026-11: its stores lived in the 1-7 rows of a character-row interleave between a fill
// and a last read, and nothing but the store's own code might write there in that time).
// With MEMWATCH_OWNERS set, the watch becomes a CHECK: every CPU write to a watched
// address that passes the filters below is judged, as made by an owner or not, and the
// process exits 1 if any was not - or if no owner wrote at all (the window never opened,
// or the region is not where the owner writes: a watch over nothing is not a pass).
//   MEMWATCH_OWNERS  FROM..TO[@BANK],FROM+N[@BANK],...: the code allowed to write, as PC
//                    ranges (TO exclusive). FROM/TO a label (with +N) or hex. BANK a
//                    sideways bank number, andy or hazel; without it, any paging
//   MEMWATCH_WINDOW  when writes are judged: SYM[:w|:sw]=LO..HI (the symbol's value in
//                    main RAM, a byte, word or signed word, within LO..HI inclusive -
//                    phX's music row), or phase=NAME|NAME (MEMWATCH_PHASES' phases).
//                    Without it, always
//   MEMWATCH_MOD     N:A-B: only addresses whose (address mod N) is in A..B - 8:1-7 is
//                    every byte but the first of each character cell, phX's "holes"
//   MEMWATCH_RAM     main or shadow: in &3000-&7FFF on a Master, only the writes that land
//                    in that RAM (ACCCON's X, or E with the PC in &C000-&DFFF)
//   MEMWATCH_NEED_OWN  0 to pass with no owner write (default 1)
// The judged writes, the owners' count and every foreign writer (PC, label, the window
// symbol's value) are in the JSON under "owners", and on stderr. The harness's own
// writeMemory is never judged.
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";

import { resolveJsbeebSrc } from "./jsbeeb_src.mjs";

const spec = process.env.MEMWATCH || "";
const OUT = resolve(process.env.MEMWATCH_OUT || "build/memwatch.json");
const FIELD = 39936;
const watched = new Uint8Array(0x10000);
for (const part of spec.split(",").filter(Boolean)) {
    const [a, b] = part.split("-").map((x) => parseInt(x.replace(/^(&|0x)/i, ""), 16));
    if (!Number.isInteger(a) || (b !== undefined && !Number.isInteger(b))) throw new Error(`MEMWATCH: ${part} is not hex`);
    for (let i = a; i <= (b ?? a); i++) watched[i & 0xffff] = 1;
}
if (!spec) console.error("[memwatch] MEMWATCH is empty: nothing watched");
const bankOf = Object.fromEntries((process.env.MEMWATCH_BANKS || "").split(",").filter(Boolean).map((p) => {
    const [s, b] = p.split(":");
    return [s, parseInt(b, 10)];
}));
const phaseSpec = (process.env.MEMWATCH_PHASES || "").split(",").filter(Boolean).map((p) => {
    const [name, at] = p.split("@");
    if (!name || !at) throw new Error(`MEMWATCH_PHASES: ${p} is not NAME@LABEL`);
    return { name, at };
});

const OWNERS = process.env.MEMWATCH_OWNERS || "";
const WINDOW = process.env.MEMWATCH_WINDOW || "";
const MOD = (() => {
    const t = process.env.MEMWATCH_MOD;
    if (!t) return null;
    const m = /^(\d+):(\d+)(?:-(\d+))?$/.exec(t);
    if (!m) throw new Error(`MEMWATCH_MOD: ${t} is not N:A-B`);
    return { n: +m[1], a: +m[2], b: +(m[3] ?? m[2]) };
})();
const RAM = process.env.MEMWATCH_RAM || "";
if (RAM && RAM !== "main" && RAM !== "shadow") throw new Error(`MEMWATCH_RAM: ${RAM} is not main or shadow`);
const NEED_OWN = process.env.MEMWATCH_NEED_OWN !== "0";
let ownersFailed = false;

/** An address in an owner or window spec: hex, or a label with an optional +N / -N. */
function addrOf(t, named) {
    const m = /^(.*?)(?:([+-])(&[0-9a-f]+|0x[0-9a-f]+|\d+))?$/i.exec(t.trim());
    const off = m[3] === undefined ? 0 : (m[2] === "-" ? -1 : 1) *
        (/^(&|0x)/i.test(m[3]) ? parseInt(m[3].replace(/^(&|0x)/i, ""), 16) : +m[3]);
    const base = /^(&|0x)[0-9a-f]+$/i.test(m[1]) ? parseInt(m[1].replace(/^(&|0x)/i, ""), 16) : named.get(m[1]);
    if (base === undefined) throw new Error(`[memwatch] no ${m[1]} in the symbols`);
    return base + off;
}
/** MEMWATCH_OWNERS as [{lo, hi (exclusive), bank, text}]. */
function parseOwners(named) {
    return OWNERS.split(",").filter(Boolean).map((t) => {
        const [range, bank] = t.split("@");
        let lo, hi;
        if (range.includes("..")) { const [a, b] = range.split(".."); lo = addrOf(a, named); hi = addrOf(b, named); }
        else {
            const m = /^(.*)\+(&[0-9a-f]+|0x[0-9a-f]+|\d+)$/i.exec(range);
            if (!m) throw new Error(`MEMWATCH_OWNERS: ${t} is not FROM..TO or FROM+N`);
            lo = addrOf(m[1], named);
            hi = lo + (/^(&|0x)/i.test(m[2]) ? parseInt(m[2].replace(/^(&|0x)/i, ""), 16) : +m[2]);
        }
        const b = bank === undefined ? null : bank === "andy" || bank === "hazel" ? bank : +bank;
        return { lo, hi, bank: b, text: t };
    });
}
/** MEMWATCH_WINDOW as a predicate on (cpu, phase). */
function parseWindow(named) {
    if (!WINDOW) return () => true;
    const ph = /^phase=(.+)$/.exec(WINDOW);
    if (ph) { const set = new Set(ph[1].split("|")); return (cpu, phase) => set.has(phase); }
    const m = /^([^:=]+)(?::(w|sw|b))?=(-?[^.]+)\.\.(-?.+)$/.exec(WINDOW);
    if (!m) throw new Error(`MEMWATCH_WINDOW: ${WINDOW} is not SYM[:w|:sw]=LO..HI or phase=NAME|NAME`);
    const a = addrOf(m[1], named), size = m[2] || "b";
    const n = (t) => (t.startsWith("-") ? -n(t.slice(1)) : /^(&|0x)/i.test(t) ? parseInt(t.replace(/^(&|0x)/i, ""), 16) : +t);
    const lo = n(m[3]), hi = n(m[4]);
    const value = (cpu) => {
        const r = cpu.ramRomOs;                     // main RAM (a symbol of the window is main's)
        const v = size === "b" ? r[a] : r[a] | (r[a + 1] << 8);
        return size === "sw" && v >= 0x8000 ? v - 0x10000 : v;
    };
    const f = (cpu) => { const v = value(cpu); return v >= lo && v <= hi; };
    f.value = value;
    return f;
}

const { src } = resolveJsbeebSrc();
const { MachineSession } = await import(`file:///${src}/machine-session.js`);

/** The disc's labels by where their code runs: main RAM, each named bank, HAZEL. */
function symbols(disc) {
    const regions = { ram: [], hazel: [] }, named = new Map();
    try {
        const doc = JSON.parse(readFileSync(disc.replace(/\.[sd]sd$/i, ".symbols.json"), "utf8"));
        const secs = Number.isInteger(doc.format) ? doc.assemblies.flatMap((a) => a.sections) : [];
        const bankFor = (i) => {
            for (let s = secs[i], n = 0; s && n < 16; s = typeof s.parent === "number" ? secs[s.parent] : secs.find((x) => x.name === s.parent), n++)
                if (s.name in bankOf) return bankOf[s.name];
            return null;
        };
        secs.forEach((sec, i) => {
            const bank = bankFor(i);
            for (const kind of ["labels", "assignments", "za_autos"]) for (const [k, v] of Object.entries(sec[kind] || {})) {
                if (!v || typeof v.value !== "number") continue;
                const name = k.replace(/^(?:@\d+:\d+\.)+/, "");
                if (!named.has(name)) named.set(name, v.value);
                if (kind !== "labels") continue;
                const a = v.value;
                const r = a < 0x8000 ? "ram" : a < 0xc000 ? (bank !== null ? String(bank) : null) : a < 0xe000 ? "hazel" : null;
                if (r) (regions[r] ||= []).push([a, name]);
            }
        });
    } catch (e) { console.error(`[memwatch] ${disc}: no symbols (${e.message}): PCs only`); }
    for (const l of Object.values(regions)) l.sort((x, y) => x[0] - y[0]);
    return { regions, named };
}
function near(labels, pc) {
    let lo = 0, hi = labels.length - 1, best = -1;
    while (lo <= hi) { const mid = (lo + hi) >> 1; if (labels[mid][0] <= pc) { best = mid; lo = mid + 1; } else hi = mid - 1; }
    return best >= 0 && pc - labels[best][0] < 0x400 ? `${labels[best][1]}+${pc - labels[best][0]}` : "?";
}
/** What the instruction at `at` is: a label in the code paged there, or whose ROM it is. */
function where(cpu, { regions }, at) {
    const h = `&${at.toString(16)}`;
    if (at < 0x8000) return `${h} (${near(regions.ram, at)})`;
    if (at < 0xc000) {
        const bank = cpu.romsel & 15;
        if (cpu.model.isMaster && (cpu.romsel & 0x80) && at < 0x9000) return `${h} ANDY`;
        return regions[bank] ? `${h} bank ${bank} (${near(regions[bank], at)})` : `${h} ROM ${bank}`;
    }
    if (at < 0xe000 && cpu.model.isMaster && (cpu.acccon & 8)) return `${h} HAZEL (${near(regions.hazel, at)})`;
    return `${h} MOS`;
}

const machines = [];
const orig = MachineSession.prototype.loadDisc;
MachineSession.prototype.loadDisc = function (path, ...rest) {
    const r = orig.call(this, path, ...rest);
    if (this._memwatch) return r;
    const cpu = this._machine.processor, syms = symbols(String(path));
    const m = { disc: String(path), model: this.modelName, phase: "boot", counts: {}, fields: { boot: 0 }, entered: {} };
    this._memwatch = m;
    machines.push(m);
    const switches = new Map();
    for (const { name, at } of phaseSpec) {
        const a = /^(&|0x)/i.test(at) ? parseInt(at.replace(/^(&|0x)/i, ""), 16) : syms.named.get(at);
        if (a === undefined) console.error(`[memwatch] ${m.disc}: no ${at} in its symbols: phase ${name} never starts`);
        else switches.set(a, name);
    }
    let pc = 0, harness = false;
    const count = (kind, addr, at) => {
        const k = `${m.phase} ${kind} &${addr.toString(16)} at ${where(cpu, syms, at)}`;
        m.counts[k] = (m.counts[k] || 0) + 1;
    };
    cpu.debugInstruction.add((at) => {
        pc = at;
        const ph = switches.get(at);
        if (ph !== undefined && ph !== m.phase) { m.phase = ph; m.entered[ph] = (m.entered[ph] || 0) + 1; }
        if (watched[at]) count("exec", at, at);
        return false;
    });
    // the harness's own readMemory/writeMemory go through the same hooks: counted apart
    for (const name of ["readMemory", "writeMemory"]) {
        const fn = this[name];
        this[name] = function (...a) { harness = true; try { return fn.apply(this, a); } finally { harness = false; } };
    }
    cpu.debugWrite.add((addr) => { if (watched[addr]) count(harness ? "harness-write" : "write", addr, pc); return false; });
    if (OWNERS) {
        const owners = parseOwners(syms.named), inWindow = parseWindow(syms.named);
        const o = m.owners = { spec: OWNERS, window: WINDOW || null, mod: process.env.MEMWATCH_MOD || null,
                               ram: RAM || null, judged: 0, own: 0, foreign: {}, firstForeign: null };
        const isOwn = (at) => owners.some(({ lo, hi, bank }) => {
            if (at < lo || at >= hi) return false;
            if (bank === null) return true;
            if (bank === "andy") return !!(cpu.romsel & 0x80) && at < 0x9000;
            if (bank === "hazel") return !!(cpu.acccon & 8);
            return (cpu.romsel & 15) === bank && !(cpu.model.isMaster && (cpu.romsel & 0x80) && at < 0x9000);
        });
        cpu.debugWrite.add((addr) => {
            if (!watched[addr] || harness) return false;
            if (MOD && ((addr % MOD.n) < MOD.a || (addr % MOD.n) > MOD.b)) return false;
            if (RAM && addr >= 0x3000 && addr < 0x8000 && cpu.model.isMaster) {
                const shadow = !!(cpu.acccon & 4) || (!!(cpu.acccon & 2) && pc >= 0xc000 && pc < 0xe000);
                if (shadow !== (RAM === "shadow")) return false;
            }
            if (!inWindow(cpu, m.phase)) return false;
            o.judged++;
            if (isOwn(pc)) { o.own++; return false; }
            const k = `${where(cpu, syms, pc)}${inWindow.value ? ` ${WINDOW.split("=")[0]} ${inWindow.value(cpu)}` : ` phase ${m.phase}`}`;
            o.foreign[k] = (o.foreign[k] || 0) + 1;
            o.firstForeign ??= { addr: `&${addr.toString(16)}`, at: where(cpu, syms, pc), phase: m.phase };
            return false;
        });
    }
    cpu.debugRead.add((addr) => { if (watched[addr] && addr !== pc && !harness) count("read", addr, pc); return false; });
    // the time each phase ran, by the phase at the start of each run
    for (const name of ["runFrames", "runFor"]) {
        const fn = this[name];
        this[name] = async function (...a) {
            const ph = m.phase, c0 = this.elapsedCycles;
            const res = await fn.apply(this, a);
            m.fields[ph] = (m.fields[ph] || 0) + (this.elapsedCycles - c0) / FIELD;
            return res;
        };
    }
    return r;
};

process.on("exit", () => {
    const out = { watched: spec, phases: process.env.MEMWATCH_PHASES || null, machines: machines.map((m) => ({
        disc: m.disc, model: m.model, entered: m.entered,
        fields: Object.fromEntries(Object.entries(m.fields).map(([k, v]) => [k, Math.round(v)])),
        ...(m.owners ? { owners: m.owners } : {}),
        accesses: Object.fromEntries(Object.entries(m.counts).sort()) })) };
    for (const m of machines) {
        if (!m.owners) continue;
        const o = m.owners, nf = Object.values(o.foreign).reduce((a, b) => a + b, 0);
        o.pass = nf === 0 && (o.own > 0 || !NEED_OWN);
        if (!o.pass) ownersFailed = true;
        console.error(`[memwatch] owners ${m.disc}: ${o.judged} writes judged, ${o.own} by the owners, ${nf} by others` +
            (o.own === 0 && NEED_OWN ? " - NO OWNER WROTE: did the window open? (MEMWATCH_NEED_OWN=0 if that is right)" : ""));
        for (const [k, v] of Object.entries(o.foreign).slice(0, 40)) console.error(`  FOREIGN ${k}: ${v}`);
    }
    try {
        mkdirSync(dirname(OUT), { recursive: true });
        writeFileSync(OUT, JSON.stringify(out, null, 1));
    } catch (e) { console.error(`[memwatch] could not write ${OUT}: ${e.message}`); }
    for (const m of out.machines) {
        const e = Object.entries(m.accesses), later = e.filter(([k]) => !k.startsWith("boot "));
        console.error(`[memwatch] ${m.disc} (${m.model}): fields ${Object.entries(m.fields).map(([k, v]) => `${k} ${v}`).join(", ")}; ` +
            `${e.length - later.length} distinct accesses at boot (in the file), ${later.length} after${later.length ? ":" : ""}`);
        for (const [k, v] of later.slice(0, 80)) console.error(`  ${k}: ${v}`);
        if (later.length > 80) console.error(`  ... ${later.length - 80} more in the file`);
    }
    console.error(`[memwatch] -> ${OUT}`);
    // the owners' verdict overrides a harness's exit 0 (process.exit inside an 'exit'
    // listener exits at once with the new code); a harness's own 1 or 2 stands
    if (ownersFailed && !process.exitCode) {
        console.error("[memwatch] OWNERS CHECK FAILED: exit 1");
        process.exit(1);
    }
});
