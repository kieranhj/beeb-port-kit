// range_free.mjs - IS THIS RAM FREE? Two measurements, the game-driving left to you.
//
//   node lib/test/range_free.mjs DISC DRIVER.mjs [MODEL]      (from the kit's root)
//     RANGES=200-3ff,d9f-dff    the ranges to judge (hex, inclusive); default the
//                               MOS low RAM a Master game might take: &0100-&01FF,
//                               &0200-&03FF, &0D9F-&0DFF, and zero page &A0-&A7
//     SYMBOLS=build/x.json      Baron's --symbols dump, to name the PC of each write
//     GAME_BANKS=4,5,6,7        sideways banks whose code is the game's (a write from any
//                               other ROM bank, or from the MOS, is FOREIGN)
//     BREAK=0                   skip the BREAK trials
//     PATTERNS=ff,4c,hash,zero  the fills each BREAK trial tries
//     BLOCK=32                  the BREAK trials' block size
//
// From the 1942 port's tools/measure_lowram.mjs and tools/measure_break.mjs (its
// decision 141's L2: it found 600-odd bytes of the MOS's low RAM it could use).
// "Free" is two things, and each needs its own measurement:
//   1 NOTHING ELSE WRITES IT while the game runs. Every CPU write into the ranges
//     is hooked, from the moment DRIVER says the watch starts until it returns,
//     with the PC (symbolised if SYMBOLS is given) and ROMSEL of each; the stack
//     page reports its low-water mark instead. A write by the GAME is the game's
//     business; a write by anything else (the MOS's IRQ, a ROM, the NMI) means
//     the byte is not yours. The MOS's 100 Hz IRQ writes &02B1-&02BE until
//     IRQ1V is taken (1942, 2026-10-07) - watch from after install_irq.
//   2 BREAK STILL WORKS WITH YOUR VALUES IN IT. The MOS READS some of this RAM
//     at a BREAK. From the state DRIVER leaves, each BLOCK of each range is
//     filled with each PATTERN in turn, BREAK is pressed (jsbeeb's soft reset),
//     and the MOS must print its banner and answer a typed *FX 0 with its
//     version. A block that fails with any pattern is NOT free. &4C is in the
//     patterns because &0287 is a JMP if a BREAK intercept is armed
//     (lib/break.6502) - and NOTE what this cannot see: the MOS JUMPS THROUGH
//     &0288-&0289 rather than reading them, so a fill there "passes" whenever
//     the intercept is not armed (1942 BUGS.md #92). If you arm it, &0287-&0289
//     are not free, whatever this says. A BREAK that clears memory (lib/break.6502)
//     makes the trial pass trivially - test with the clear off.
// THE DRIVER is a module exporting
//     export async function drive(s, ctx)
// s is jsbeeb's MachineSession with the disc in drive 0 and nothing yet run; ctx
// has ctx.startWatch(phaseName) (call it once the game owns the machine),
// ctx.phase(name) (label what follows), ctx.runTo(addr, cycles) and ctx.sym(name).
// Play everything the game can do between startWatch and returning: a range is
// only as free as the run that measured it was long (1942's walked every seam
// kind, both game overs, the pause keys and a stage skip to the wrap).
// Exit code: 0 if no range had a write from outside the game's own code and no
// BREAK trial failed; the JSON says which.
import { readFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const kit = join(here, "..", "..");
const { loadMachineSession } = await import(pathToFileURL(join(kit, "template", "tools", "jsbeeb_src.mjs")).href);

const [disc, driverPath, model = "Master"] = process.argv.slice(2);
if (!disc || !driverPath) { console.error("usage: node lib/test/range_free.mjs DISC DRIVER.mjs [MODEL]"); process.exit(2); }
const RANGES = (process.env.RANGES || "100-1ff,200-3ff,d9f-dff,a0-a7").split(",")
    .map((r) => r.split("-").map((x) => parseInt(x, 16)));
const PATTERNS = (process.env.PATTERNS || "ff,4c,hash,zero").split(",");
const BLOCK = Number(process.env.BLOCK || 32);
const fillOf = { ff: () => 0xff, "4c": () => 0x4c, zero: () => 0, hash: (i) => (i * 73 + 29) & 0xff, a5: () => 0xa5 };

const syms = {};
if (process.env.SYMBOLS) {
    const j = JSON.parse(readFileSync(process.env.SYMBOLS, "utf8"));
    if (j.assemblies) {
        for (const a of j.assemblies) for (const sec of a.sections)
            for (const kind of ["labels", "assignments"]) for (const [k, v] of Object.entries(sec[kind] || {})) syms[k] = v.value;
    } else Object.assign(syms, ...Object.values(j));
}
const labels = Object.entries(syms).filter(([, v]) => Number.isInteger(v) && v >= 0x100 && v < 0x10000).sort((a, b) => a[1] - b[1]);
const symAt = (a) => {
    let lo = 0, hi = labels.length - 1, best = null;
    while (lo <= hi) { const mid = (lo + hi) >> 1; if (labels[mid][1] <= a) { best = labels[mid]; lo = mid + 1; } else hi = mid - 1; }
    return best ? `${best[0]}+${a - best[1]}` : `&${a.toString(16)}`;
};

const MachineSession = await loadMachineSession();
const s = new MachineSession(model, { tube: false });
await s.initialise();
await s.boot(30);
s.loadDisc(resolve(disc));
const cpu = s._machine.processor;
const inRange = (a) => RANGES.findIndex(([lo, hi]) => a >= lo && a <= hi);
const out = { model, ranges: RANGES.map(([lo, hi]) => `${lo.toString(16)}-${hi.toString(16)}`), writes: {}, stackLow: null };
let phase = "-", watching = false;
const GAME_BANKS = (process.env.GAME_BANKS || "4,5,6,7").split(",").map(Number);
// who wrote: the MOS (or a ROM bank that is not the game's) is FOREIGN
const writer = (pc) => {
    const hazel = cpu.model.isMaster && (cpu.acccon & 8);
    if (pc >= 0xE000 || (pc >= 0xC000 && !hazel)) return { who: `mos:&${pc.toString(16)}`, foreign: true };
    if (pc >= 0xC000) return { who: `hazel:${symAt(pc)}`, foreign: false };
    if (pc >= 0x8000) {
        const bank = cpu.romsel & 0xf;
        const game = GAME_BANKS.includes(bank) && !(cpu.romsel & 0x80);
        return { who: `bank${bank}${cpu.romsel & 0x80 ? "+andy" : ""}:${game ? symAt(pc) : "&" + pc.toString(16)}`,
                 foreign: !game && !(cpu.romsel & 0x80) };
    }
    return { who: symAt(pc), foreign: false };
};
cpu.debugWrite.add((addr) => {
    if (!watching) return false;
    const r = inRange(addr);
    if (r < 0) return false;
    if (addr === 0x100 + cpu.s) {          // a push (an interrupt is three): the stack's
        out.stackLow = Math.min(out.stackLow ?? 0x200, addr);
        return false;
    }
    const at = addr.toString(16);
    const e = (out.writes[at] ||= { n: 0, by: {}, phases: [], foreign: false });
    e.n++;
    if (!e.phases.includes(phase)) e.phases.push(phase);
    const w = writer(cpu.pc);
    e.by[w.who] = (e.by[w.who] || 0) + 1;
    if (w.foreign) e.foreign = true;
    return false;
});
const ctx = {
    startWatch(name = "play") { watching = true; phase = name; },
    phase(name) { phase = name; },
    sym(n) { if (!(n in syms)) throw new Error(`no symbol ${n} (SYMBOLS=?)`); return syms[n]; },
    async runTo(addr, cycles = 400_000_000) {
        const id = s.addBreakpoint("execute", addr);
        s.resetBreakpointHits();
        let hit = false;
        for (let c = 0; c < cycles && !hit; c += 4_000_000) { await s.runFor(4_000_000); hit = !!s.hitBreakpoint(); }
        s.removeBreakpoint(id);
        if (!hit) throw new Error(`never reached &${addr.toString(16)} (pc &${cpu.pc.toString(16)})`);
    },
};
const { drive } = await import(pathToFileURL(resolve(driverPath)).href);
await drive(s, ctx);
watching = false;
out.foreign = Object.entries(out.writes).filter(([, e]) => e.foreign).map(([a]) => a);

if (process.env.BREAK !== "0") {
    const state = s.snapshot();
    async function trial(ranges, f) {
        s.restore(state);
        for (const [lo, hi] of ranges) s.writeMemory(lo, Array.from({ length: hi - lo + 1 }, (_, i) => f(i)), { shadow: false });
        s.drainOutput();
        s.reset(false);
        await s.runFrames(150);
        let text = s.drainOutput().screenText || "";
        const banner = /Acorn|BASIC/.test(text);
        await s.type("*FX 0\r");
        await s.runFrames(150);
        text = s.drainOutput().screenText || "";
        return banner && /OS \d\.\d\d/.test(text);
    }
    out.control = await trial([], fillOf.zero);
    out.breakNeeds = [];
    if (out.control) {
        for (const [lo, hi] of RANGES) for (let a = lo; a <= hi; a += BLOCK) {
            const b = Math.min(a + BLOCK - 1, hi), bad = [];
            for (const p of PATTERNS) if (!(await trial([[a, b]], fillOf[p]))) bad.push(p);
            if (bad.length) out.breakNeeds.push({ block: `${a.toString(16)}-${b.toString(16)}`, patterns: bad });
            process.stderr.write(`${a.toString(16)}-${b.toString(16)} ${bad.length ? "NEEDED " + bad.join(",") : "free"}\n`);
        }
    }
}
out.pass = out.foreign.length === 0 && (process.env.BREAK === "0" || (out.control && out.breakNeeds.length === 0));
for (const e of Object.values(out.writes)) e.by = Object.fromEntries(Object.entries(e.by).slice(0, 4));
console.log(JSON.stringify(out, null, 1));
process.exit(out.pass ? 0 : 1);
