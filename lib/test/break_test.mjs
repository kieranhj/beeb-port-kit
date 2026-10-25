// break_test.mjs - does lib/break.6502 make BREAK clear RAM? jsbeeb Master, headless.
//
//   node lib/test/break_test.mjs [MODEL]     (from the kit's root; MODEL default Master)
//
// Boots lib/test/break_test.6502 to bt_main, snapshots, and for each case pokes
// bt_mode, runs to bt_ready (&3000-&5FFF full of &A5, the MOS's interrupts on,
// so the system VIA's IER is not 0), presses BREAK - jsbeeb's soft reset, which
// keeps RAM unless the MOS clears it - and reads back:
//   the fill (&3000-&5FFF), the test program itself (&2000 up), &0258 and
//   &0287-&0289, and that the MOS came back: its banner, and a typed *FX 0
//   answering with the OS version.
// The cases and what each MUST do (the MOS 3.20 rule in lib/break.6502):
//   none          no *FX 200: RAM kept                       (the control)
//   fx200         *FX 200,2: cleared
//   fx200+trash   *FX 200,2, then &0258 = 0: KEPT            (the problem)
//   arm+trash     brk_arm, then &0258 = 0: cleared           (the fix)
// Exit code = verdict.
import { readFileSync, mkdirSync } from "node:fs";
import { execFileSync } from "node:child_process";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const model = process.argv[2] || "Master";
const here = dirname(fileURLToPath(import.meta.url));
const kit = join(here, "..", "..");
const { loadMachineSession } = await import(`file:///${join(kit, "template", "tools", "jsbeeb_src.mjs").split("\\").join("/")}`);
const baron = process.env.BARON || join(kit, "template", "bin", process.platform === "win32" ? "baron.exe" : "baron");
const out = join(here, "build");
mkdirSync(out, { recursive: true });
const ssd = join(out, "brktest.ssd"), symPath = join(out, "brktest.json");
execFileSync(baron, ["--warn", "2", "-o", ssd, "--title", "BRKT", "--opt", "3", "--symbols", symPath,
    join(here, "break_test.6502")], { stdio: "inherit" });
const syms = {};
for (const a of JSON.parse(readFileSync(symPath, "utf8")).assemblies)
    for (const sec of a.sections)
        for (const kind of ["labels", "assignments"])
            for (const [k, v] of Object.entries(sec[kind] || {})) syms[k] = v.value;

const MachineSession = await loadMachineSession();
const s = new MachineSession(model, { tube: false });
await s.initialise();
await s.boot(30);
s.loadDisc(ssd);
const mem = (a, n = 1) => Array.from(s.readMemory(a, n, { shadow: false }));
async function runTo(addr, cycles = 200_000_000) {
    const id = s.addBreakpoint("execute", addr);
    s.resetBreakpointHits();
    let hit = false;
    for (let c = 0; c < cycles && !hit; c += 4_000_000) {
        await s.runFor(4_000_000);
        hit = !!s.hitBreakpoint();
    }
    s.removeBreakpoint(id);
    return hit;
}
s.addBreakpoint("execute", syms.bt_main);
await s.autoboot();
s.clearBreakpoints();
if (!(await runTo(syms.bt_main))) { console.log(JSON.stringify({ error: "never reached bt_main" })); process.exit(1); }
const atMain = s.snapshot();

const cases = [
    { name: "none", mode: 0, clears: false },
    { name: "fx200", mode: 2, clears: true },
    { name: "fx200+trash", mode: 2 | 4, clears: false },
    { name: "arm+trash", mode: 1 | 4, clears: true },
];
const res = { model, cases: [] };
for (const c of cases) {
    s.restore(atMain);
    s.writeMemory(syms.bt_mode, [c.mode], { shadow: false });
    if (!(await runTo(syms.bt_ready, 40_000_000))) { c.error = "never reached bt_ready"; res.cases.push(c); continue; }
    const before = { f258: mem(0x258)[0], i287: mem(0x287, 3), ier: s._machine.processor.sysvia?.ier };
    s.drainOutput();
    s.reset(false);                                    // BREAK
    await s.runFrames(150);
    let text = s.drainOutput().screenText || "";
    const banner = /Acorn MOS|Acorn ADFS|BASIC/.test(text);
    await s.type("*FX 0\r");
    await s.runFrames(150);
    text = s.drainOutput().screenText || "";
    const fill = mem(0x3000, 0x3000), prog = mem(syms.bt_main, 64);
    const r = { name: c.name, before,
                fillA5: fill.filter((b) => b === 0xA5).length, fillZero: fill.filter((b) => b === 0).length,
                progZero: prog.every((b) => b === 0), after258: mem(0x258)[0], after287: mem(0x287, 3),
                banner, fx0: (/OS \d\.\d\d/.exec(text) || [null])[0] };
    r.cleared = r.fillZero === fill.length && r.progZero;
    r.kept = r.fillA5 === fill.length;
    r.ok = (c.clears ? r.cleared : r.kept) && banner && !!r.fx0;
    res.cases.push(r);
}
res.pass = res.cases.length === cases.length && res.cases.every((c) => c.ok);
console.log(JSON.stringify(res, null, 1));
process.exit(res.pass ? 0 : 1);
