// zx02stream_test.mjs - does lib/zx02stream.6502 decode a ZX02 stream into a ring, a few bytes at
// a time from the main loop and an interrupt, exactly? jsbeeb, headless.
//
//   node lib/test/zx02stream_test.mjs [MODEL]   (from the kit's root; MODEL default Master; B-DFS1.2 too)
//
// 1. lib/test/make_stream_data.py packs two streams of synthetic data with zx02 -m 1024.
// 2. lib/test/zx02stream_test.6502 is assembled and booted (its header has the two phases).
// 3. Phase 1's output - everything the reader took out of the 1K ring, both streams in a row -
//    must equal the raw data byte for byte, with the interrupt's units and the busy flag both
//    seen to happen; phase 2 times stream A alone in 4- and 32-byte units (IRQ off).
// Also, in a debugInstruction hook: every write the decoder makes into the ring must land in a
//    slot the reader has finished with and ZS_GAP bytes clear of the reader (the room rule).
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

const info = JSON.parse(execFileSync(python, [join(here, "make_stream_data.py"), out, "1024"]).toString());
const ssd = join(out, "zst.ssd"), symPath = join(out, "zst.json");
execFileSync(baron, ["--warn", "2", "-o", ssd, "--title", "ZST", "--opt", "3", "--symbols", symPath,
    join(here, "zx02stream_test.6502")], { stdio: "inherit", cwd: here });
const syms = {};
for (const a of JSON.parse(readFileSync(symPath, "utf8")).assemblies)
    for (const sec of a.sections)
        for (const kind of ["labels", "assignments"])
            for (const [k, v] of Object.entries(sec[kind] || {})) syms[k] = v.value;
const sym = (n) => { if (syms[n] === undefined) throw new Error(`no symbol ${n}`); return syms[n]; };

const MachineSession = await loadMachineSession();
const s = new MachineSession(model, { tube: false });
await s.initialise();
await s.boot(30);
s.loadDisc(ssd);
const cpu = s._machine.processor;
const mem = (a, n = 1) => Buffer.from(s.readMemory(a, n, model === "Master" ? { shadow: false } : {}));
const RING = sym("ZS_RING"), SIZE = sym("ZS_PAGES") * 256, GAP = sym("ZS_GAP"), MIRROR = sym("ZS_MIRROR");
const READ = sym("zt_read"), W = sym("zs_w");

// the room rule, checked at every store the decoder makes (zs_put's STA (zs_w),Y)
const putPc = sym("zs_put");
let puts = 0, intrusions = 0, firstIntrusion = null, phase1 = true;
cpu.debugInstruction.add((pc) => {
    if (pc !== putPc || !phase1) return false;
    const rd = cpu.readmem(READ) | (cpu.readmem(READ + 1) << 8);
    const w = cpu.readmem(W) | (cpu.readmem(W + 1) << 8);
    const free = (rd - w - 1 + SIZE) % SIZE;        // slots the decoder may write, from w on
    puts++;
    if (free <= GAP) { intrusions++; firstIntrusion ??= { put: puts, read: rd, w }; }
    return false;
});
const bps = {};
for (const n of ["phase2", "zt_t1", "zt_t2"]) { bps[sym(n)] = n; s.addBreakpoint("execute", sym(n)); }
await s.autoboot();
const at = {};
for (let guard = 0; guard < 400 && !at.zt_t2; guard++) {
    s.resetBreakpointHits();
    await s.runFor(20_000_000);
    if (!s.hitBreakpoint()) break;
    const what = bps[cpu.pc];
    if (!what) continue;
    at[what] = s.elapsedCycles;
    if (what === "phase2") phase1 = false;
}
const res = { model, decoder_bytes: sym("zt_old") - sym("zs_state"), ...info };
if (!at.zt_t2) {
    res.error = `never reached zt_t2 (pc ${cpu.pc.toString(16)})`;
    res.pass = false;
} else {
    const raw = readFileSync(join(out, "zst_raw.bin"));
    const w16 = (a) => { const b = mem(a, 2); return b[0] | (b[1] << 8); };
    const outEnd = w16(sym("zt_out1"));
    const got = mem(sym("ZT_OUT"), raw.length);
    let bad = 0, firstBad = null;
    for (let i = 0; i < raw.length; i++) if (got[i] !== raw[i]) { bad++; firstBad ??= i; }
    res.phase1 = { bytes_out: outEnd - sym("ZT_OUT"), want: raw.length, bad, firstBad,
        reads: w16(sym("zt_reads")), irq_units: w16(sym("zt_irqruns")), irq_blocked_by_busy: w16(sym("zt_blocked")),
        ring_puts: puts, gap_intrusions: intrusions, firstIntrusion };
    const ring = mem(RING, SIZE + MIRROR);
    res.mirror_ok = ring.subarray(SIZE).equals(ring.subarray(0, MIRROR));
    res.phase2 = { unit4_cycles_per_byte: +((at.zt_t1 - at.phase2) / info.ZST_A_LEN).toFixed(1),
        unit32_cycles_per_byte: +((at.zt_t2 - at.zt_t1) / info.ZST_A_LEN).toFixed(1) };
    res.pass = bad === 0 && res.phase1.bytes_out === raw.length && res.phase1.irq_units > 0 &&
        res.phase1.irq_blocked_by_busy > 0 && intrusions === 0 && puts === raw.length && res.mirror_ok;
}
console.log(JSON.stringify(res, null, 1));
process.exit(res.pass ? 0 : 1);
