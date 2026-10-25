// sfx50_test.mjs - does lib/sfx50.6502 play what sfx50.py fitted? jsbeeb, headless.
//
//   node lib/test/sfx50_test.mjs [MODEL]     (from the kit's root; MODEL default Master; B-DFS1.2 too)
//
// 1. py/beeb_port_kit/sfx50.py fits the two effects of py/tests/data/sfx50_capture_sample.json
//    (Stryker's Run's MOS capture: a noise burst and a falling tone) into
//    lib/test/build/sfx50_data.6502, and says field by field what its ramps play (play()).
// 2. lib/test/sfx50_test.6502 is assembled with it and booted: irq.6502 owns IRQ1V, its vsync
//    hook runs sfx_tick, and both effects are requested at once (chip channels 1 and 3).
// 3. Every SN76489 write is logged with its cycle; the chip's registers are replayed and read
//    at each vsync hook entry, so field k's state is what tick k wrote. From the first tick
//    after the requests, each channel must be exactly the model's (period or noise control,
//    amplitude) every field, then silent; the other two channels silent throughout. Also printed:
//    how far the ramps are from the MOS's own samples (the fit, not the driver).
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
const python = process.env.PYTHON || "python";
const out = join(here, "build");
mkdirSync(out, { recursive: true });

// 1. the data and the model; 2. the disc; 3. the chip, field by field. Once as fitted, once --pad-end.
const PY = `
import json, sys
from beeb_port_kit import sfx50
pad = sys.argv[3] == "1"
eff = sfx50.load(sys.argv[1])
text, size = sfx50.render(eff, "sfx50_capture_sample.json", "sfx50_data.6502", pad_end=pad)
open(sys.argv[2], "w", newline=chr(10)).write(text)
res = []
for name, ch, what, w in eff:
    s, rs = sfx50.fit(w, ch, pad_end=pad)
    res.append({"name": name, "ch": ch, "ramps": rs, "play": sfx50.play(rs), "mos": s})
print(json.dumps({"size": size, "effects": res}))
`;
const MachineSession = await loadMachineSession();

async function variant(pad) {
    const m = JSON.parse(execFileSync(python, ["-c", PY, join(kit, "py", "tests", "data", "sfx50_capture_sample.json"),
        join(out, "sfx50_data.6502"), pad ? "1" : "0"], { cwd: join(kit, "py") }).toString());
    const ssd = join(out, "sfxtest.ssd"), symPath = join(out, "sfxtest.json");
    execFileSync(baron, ["--warn", "2", "-o", ssd, "--title", "SFXT", "--opt", "3", "--symbols", symPath,
        join(here, "sfx50_test.6502")], { stdio: "inherit" });
    const syms = {};
    for (const a of JSON.parse(readFileSync(symPath, "utf8")).assemblies)
        for (const sec of a.sections)
            for (const kind of ["labels", "assignments"])
                for (const [k, v] of Object.entries(sec[kind] || {})) syms[k] = v.value;

    const s = new MachineSession(model, { tube: false });
    await s.initialise();
    await s.boot(30);
    s.loadDisc(ssd);
    const cpu = s._machine.processor;
    const cyc = () => cpu.currentCycles + cpu.cycleSeconds * 2000000;
    const chip = cpu.soundChip, poke = chip.poke.bind(chip);
    const writes = [], vsyncs = [];
    let idleAt = null;
    chip.poke = (v) => { writes.push([cyc(), v]); return poke(v); };
    cpu.debugInstruction.add((pc) => {
        if (pc === syms.irq_vsync_hook) vsyncs.push(cyc());
        else if (pc === syms.st_idle && idleAt === null) idleAt = cyc();
        return false;
    });
    await s.autoboot();
    for (let f = 0; f < 600 && (idleAt === null || vsyncs.filter((t) => t > idleAt).length < 120); f++) await s.runFrames(1);
    if (idleAt === null) return { pad, error: "never reached st_idle", pass: false };

    // the chip's registers at each vsync entry: field k = the state after tick k's writes
    const regs = { t: [0x3ff, 0x3ff, 0x3ff], n: 0, att: [15, 15, 15, 15] };
    let latch = null, wi = 0;
    const ticks = vsyncs.filter((t) => t > idleAt);
    const fields = [];
    for (let k = 1; k < ticks.length; k++) {
        while (wi < writes.length && writes[wi][0] < ticks[k]) {
            const [c, v] = writes[wi++];
            if (c < ticks[0]) continue;
            if (v & 0x80) {
                const ch = (v >> 5) & 3, vol = v & 0x10;
                latch = { ch, vol };
                if (vol) regs.att[ch] = v & 15;
                else if (ch === 3) regs.n = v & 7;
                else regs.t[ch] = (regs.t[ch] & 0x3f0) | (v & 15);
            } else if (latch && !latch.vol && latch.ch < 3) regs.t[latch.ch] = (regs.t[latch.ch] & 15) | ((v & 63) << 4);
        }
        fields.push(JSON.parse(JSON.stringify(regs)));
    }
    // the driver silences a channel in the tick that outputs its last field: the chip holds
    // play[0 .. n-2] at the field boundaries, then silence from field n-1
    const res = { pad, data_bytes: m.size, fields: fields.length, effects: [] };
    let bad = 0;
    for (const e of m.effects) {
        const heard = e.play.length - 1;
        const r = { name: e.name, ch: e.ch, ramps: e.ramps.length, mos_fields: e.mos.length, heard, wrong: 0, first: null, after_silent: true };
        for (let k = 0; k < fields.length; k++) {
            const f = fields[k];
            const got = [e.ch === 3 ? f.n : f.t[e.ch], 15 - f.att[e.ch]];
            if (k < heard) {
                const p = e.ch === 3 ? e.play[k][0] & 7 : e.play[k][0] & 0x3ff;
                if (got[0] !== p || got[1] !== e.play[k][1]) { r.wrong++; r.first ??= { field: k, got, want: [p, e.play[k][1]] }; }
            } else if (got[1] !== 0) r.after_silent = false;
        }
        let dp = 0, da = 0;
        e.mos.forEach(([p, a], k) => { if (k < heard) { dp = Math.max(dp, Math.abs(e.play[k][0] - p)); da = Math.max(da, Math.abs(e.play[k][1] - a)); } });
        r.heard_against_mos = { max_period: dp, max_amplitude: da, mos_fields_cut: Math.max(0, e.mos.length - heard) };
        if (r.wrong || !r.after_silent || fields.length < e.play.length + 5) bad++;
        res.effects.push(r);
    }
    res.others_silent = [0, 2].every((ch) => fields.every((f) => f.att[ch] === 15));
    res.chip_writes = writes.filter(([c]) => c >= ticks[0]).length;
    res.pass = !bad && res.others_silent && res.effects.length === 2;
    return res;
}

const runs = [await variant(false), await variant(true)];
const pass = runs.every((r) => r.pass) && runs[1].effects.every((e) => e.heard_against_mos.mos_fields_cut === 0);
console.log(JSON.stringify({ model, runs, pass }, null, 1));
process.exit(pass ? 0 : 1);
