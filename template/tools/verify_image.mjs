// KIT NOTE (2026-11-14): Isometrikum's crunch gate - memory at two hooks against a golden copy,
// with a mask, while a change only alters how the bytes ARRIVE. Hook names, banks and the mask
// are that project's. docs/cpc-demo-porting.md section 11.
// verify_image.mjs - the crunch's identical-image check (docs/crunch.md, decision 15).
//
// Boots the disc in headless jsbeeb and dumps the machine at two points:
//   enter  the first instruction of bank_main (the boot has handed over to the code bank)
//   loop   the first instruction of main_loop (the demo's own init is done)
// each as main RAM &0000-&7FFF, then the code bank and the plot bank (16K each), 64K in all.
// With --golden PREFIX it compares against PREFIX-enter.bin / PREFIX-loop.bin and lists the
// differing ranges, ignoring what may legitimately differ (MASK below); else it writes OUT-*.bin.
//
// A build that changes only how its bytes ARRIVE (rounds 1-3: generated at runtime, one file,
// another packer) must leave both images identical to master's.
//
//   node tools/verify_image.mjs DISC SYMBOLS.json OUT_PREFIX [MODEL] [--golden PREFIX]
//   NULA=1 on the command line: a VideoNuLA fitted
import { readFileSync, writeFileSync } from "node:fs";
import { loadMachineSession, keys } from "./jsbeeb_src.mjs";

const args = process.argv.slice(2);
const gi = args.indexOf("--golden");
const golden = gi >= 0 ? args.splice(gi, 2)[1] : null;
const [ssd, symsPath, out, modelArg] = args;
const MODEL = modelArg || "B-DFS1.2";
const syms = {};
for (const asm of JSON.parse(readFileSync(symsPath, "utf8")).assemblies)
    for (const sec of asm.sections)
        for (const kind of ["labels", "assignments", "za_autos"])
            for (const [name, v] of Object.entries(sec[kind] || {})) syms[name] ??= v.value;
for (const n of ["bank_main", "main_loop", "code_bank", "plot_bank"])
    if (syms[n] === undefined) { console.error(`no symbol ${n}`); process.exit(2); }

// Ranges of the 64K image (main RAM 0-&7FFF, code bank at &8000, plot bank at &C000) that may
// differ between builds which bring the same demo in differently: the stack page, and the
// loaders' own zero page and staging (main RAM is the screen's from main_loop on, and the demo
// clears what it shows). Each entry says why; keep it short.
const MASK = [
    [0x0002, 0x0006, "master's ZX02 left zxdst/zxwrk here, in demo zero page (pl_sp, rd_zp, rm_zp, ob_zp): written before read (the suite proves it)"],
    [0x000D, 0x000E, "master's ZX02 left zxbit here (demo's mus_hl + 3)"],
    [0x0070, 0x0085, "unShrinkler's zero page and Game's two bank numbers (master had neither)"],
    [0x0090, 0x0100, "the MOS's zero page: dead once bank_main runs"],
    [0x0100, 0x0200, "the stack page"],
    [0x0200, 0x0300, "the MOS's variables: dead once bank_main runs"],
    [0x0900, 0x0A00, "!BOOT's page: master's boot file and its build stamp"],
];
// At `enter` main RAM still holds each boot's own leftovers (master: Game, staged ZX02 streams;
// the crunch: the executable, unShrinkler's workspace), so only LOW and the banks are compared;
// the demo's init clears the rest, and `loop` compares all of it.
const ENTER = [[0x0400, 0x0CD8], [0x8000, 0x10000]];

const MachineSession = await loadMachineSession();
const K = keys();
const s = new MachineSession(MODEL, { tube: false, hasVideoNula: !!process.env.NULA });
await s.initialise();
await s.boot(30);
s.loadDisc(ssd);
s.keyDown(K.SHIFT); s.reset(true); await s.runFrames(50); s.keyUp(K.SHIFT);
const cpu = s._machine.processor;

const snap = () => {
    const cb = s.readMemory(syms.code_bank, 1)[0], pb = s.readMemory(syms.plot_bank, 1)[0];
    const img = new Uint8Array(65536);
    img.set(s.readMemory(0, 0x8000), 0);
    img.set(s.readMemory(0x8000, 0x4000, { bank: cb }), 0x8000);
    img.set(s.readMemory(0x8000, 0x4000, { bank: pb }), 0xC000);
    return { img, cb, pb, cycles: cpu.scheduler.epoch };
};
const shots = {};
let want = "enter";
cpu.debugInstruction.add((addr) => {
    if (want === "enter" && addr === syms.bank_main) {
        const b = s.readMemory(syms.code_bank, 1)[0];
        if (b && (cpu.romsel & 15) === b) { shots.enter = snap(); want = "loop"; }
    } else if (want === "loop" && addr === syms.main_loop && (cpu.romsel & 15) === shots.enter.cb) {
        shots.loop = snap(); want = "done";
    }
    return false;
});
for (let f = 0; f < 6000 && want !== "done"; f += 10) await s.runFrames(10);
if (want !== "done") { console.error(`never reached ${want}`); process.exit(1); }

const masked = (a, k) => MASK.some(([lo, hi]) => a >= lo && a < hi)
    || (k === "enter" && !ENTER.some(([lo, hi]) => a >= lo && a < hi));
const where = (a) => a < 0x8000 ? `&${a.toString(16).padStart(4, "0")}`
    : a < 0xC000 ? `code:&${a.toString(16)}` : `plot:&${(a - 0x4000).toString(16)}`;
let fail = 0;
for (const k of ["enter", "loop"]) {
    const { img, cycles } = shots[k];
    console.log(`${k}: ${(cycles / 2e6).toFixed(2)} s after reset`);
    writeFileSync(`${out}-${k}.bin`, img);
    if (!golden) continue;
    const ref = readFileSync(`${golden}-${k}.bin`);
    const runs = [];
    for (let a = 0; a < 65536; a++) {
        if (masked(a, k) || img[a] === ref[a]) continue;
        const r = runs[runs.length - 1];
        if (r && r[1] >= a - 4) r[1] = a; else runs.push([a, a]);
    }
    const n = runs.reduce((t, [a, b]) => t + b - a + 1, 0);
    console.log(`${k}: ${runs.length ? `DIFFERS in ${runs.length} ranges (${n} bytes)` : "identical"}`);
    for (const [a, b] of runs.slice(0, 40)) console.log(`   ${where(a)}-${where(b)}`);
    if (runs.length) fail = 1;
}
process.exit(fail);
