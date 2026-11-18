// fz_test.mjs - does lib/fzdepack.6502 decode what template/tools/fz.py packs, on a real boot?
// jsbeeb, headless.
//
//   node lib/test/fz_test.mjs [MODEL]     (from the kit's root; MODEL default Master; B-DFS1.2 too)
//
// 1. lib/test/make_stream_data.py writes two FZ streams of synthetic data and their outputs.
// 2. lib/test/fz_test.6502 is assembled and booted: with the IRQ masked it decodes the first to
//    &4000, then copies the second to the end of its own output (+ fz.py's in_place_gap) and
//    decodes it over itself at &6000.
// 3. Both outputs must equal the raw files byte for byte, the bytes after each untouched by the
//    decode (the first) or exactly the stream's leftover (the second), and the pointers left one
//    past the end; the first decode's cycles over its bytes are the cost a byte.
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
const ssd = join(out, "fzt.ssd"), symPath = join(out, "fzt.json");
execFileSync(baron, ["--warn", "2", "-o", ssd, "--title", "FZT", "--opt", "3", "--symbols", symPath,
    join(here, "fz_test.6502")], { stdio: "inherit", cwd: here });
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
const mem = (a, n = 1) => Buffer.from(s.readMemory(a, n, model === "Master" ? { shadow: false } : {}));
const bps = {};
for (const n of ["ft_t0", "ft_t1", "ft_t2", "ft_t3", "ft_done"]) { bps[sym(n)] = n; s.addBreakpoint("execute", sym(n)); }
await s.autoboot();
const at = {};
let before2 = null;
for (let guard = 0; guard < 200 && !at.ft_done; guard++) {
    s.resetBreakpointHits();
    await s.runFor(20_000_000);
    if (!s.hitBreakpoint()) break;
    const what = bps[s._machine.processor.pc];
    if (!what) continue;
    at[what] = s.elapsedCycles;
    if (what === "ft_t2") before2 = mem(sym("FT_SRC2"), info.FZT2_PACKED);
}
const res = { model, depacker_bytes: sym("fz_end") - sym("fz_unpack"), ...info };
if (!at.ft_done) {
    res.error = "never reached ft_done";
    res.pass = false;
} else {
    const raw1 = readFileSync(join(out, "fzt_raw.bin")), raw2 = readFileSync(join(out, "fzt_raw.bin").replace("fzt_raw", "fzt2_raw"));
    const diff = (a, b) => { let n = 0; for (let i = 0; i < b.length; i++) if (a[i] !== b[i]) n++; return n; };
    const got1 = mem(0x4000, raw1.length), got2 = mem(0x6000, raw2.length);
    const e1 = mem(sym("ft_end1"), 4), e2 = mem(sym("ft_end2"), 2);
    res.stream1 = { bad: diff(got1, raw1),
        src_end_ok: (e1[0] | (e1[1] << 8)) === sym("ft_s1") + info.FZT_PACKED,
        dst_end_ok: (e1[2] | (e1[3] << 8)) === 0x4000 + raw1.length,
        cycles: at.ft_t1 - at.ft_t0, cycles_per_byte: +((at.ft_t1 - at.ft_t0) / raw1.length).toFixed(1) };
    res.stream2_in_place = { bad: diff(got2, raw2), copied_ok: before2 && diff(before2, readFileSync(join(out, "fzt2.fz"))) === 0,
        dst_end_ok: (e2[0] | (e2[1] << 8)) === 0x6000 + raw2.length,
        cycles_per_byte: +((at.ft_t3 - at.ft_t2) / raw2.length).toFixed(1) };
    res.pass = res.stream1.bad === 0 && res.stream1.src_end_ok && res.stream1.dst_end_ok &&
        res.stream2_in_place.bad === 0 && res.stream2_in_place.copied_ok && res.stream2_in_place.dst_end_ok;
}
console.log(JSON.stringify(res, null, 1));
process.exit(res.pass ? 0 : 1);
