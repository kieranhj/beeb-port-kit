// verify_disc.mjs - a disc loader, watched from the BREAK: every FDC command and NMI by field,
// every file's bytes at home against the disc's own catalogue, every load window against its
// deadline, and the disc only in the fields the design allows it.
//
// beeb-port-kit template, MIT, Kieran Connell 2026. From the phX port, 2026-11 (its
// tools/verify_disc.mjs, which watched a demo that streams seven load windows off a two-sided
// disc behind its static screens, through its own 1770 driver). That tool read phX's own tables
// (file names, homes, windows, deadlines) out of its engine; here they come from a CONFIG module
// (template.mjs beside this is the kit template's, a worked example), so the engine is generic
// and the port's knowledge is in one place. AN EXAMPLE, NOT A TOOL: copy both into the port's
// tools/ and adapt the config - what to adapt is listed below.
//
//   node examples/verify_disc/verify_disc.mjs DISC CONFIG.mjs [FIELDS=600] [--model=...]
//
// From the BREAK (the hooks go on before it: harness.mjs boot({prepare})), field by field (a
// field is a VSync of the 6845, or the config's `entry` label):
//   - every write to the FDC's COMMAND register (the 1770's &FE28 on a Master, &FE84 on a B
//     with a 1770; the 8271's &FE80 on a B with an 8271 - the config's `fdc`, or by model) and
//     every NMI (an instruction at the config's `nmi`, default &0D00, where the DFS - and any
//     port's own driver - puts its NMI code), with the field and the config's phase
//   - 1. THE CATALOGUE: every file the config names is on the disc (both sides of a .dsd)
//   - 2. EVERY BYTE HOME: when the file's `check` label first executes after the boot, its
//        bytes at `at` (a symbol, a number, or "catalogue" for its catalogue load address) in
//        `where` (main, shadow, a bank number, andy) equal the file on the disc
//   - 3. EVERY WINDOW BEFORE ITS DEADLINE: a window opens at `start`, closes at `done`, and
//        must close by `deadline` (fields after the BREAK, or a function of h): the margin in
//        fields, reported, and > 0
//   - 4. THE DISC ONLY WHERE ALLOWED: every field with an NMI or an FDC command must pass the
//        config's discAllowed(field) - phX: the card, black, and three windows behind static
//        screens, never in a part that races the beam (decision 32 there)
// samples = the fields watched. Timing is jsbeeb's FDC (the 1770's: 300 rpm, 6 ms steps, 30 ms
// head settle with E; the 8271's its own): a margin measured here is the emulator's until the
// port's hardware test confirms it.
//
// THE CONFIG (export default { ... }), every key optional but files or windows:
//   files: [{ name, at, where, check }]   (or a function of h returning them)
//   windows: [{ name, start, done, deadline }]
//   phases: [[name, label], ...]   the phase becomes NAME when LABEL executes (before: "boot")
//   discAllowed(f)                 f = {field, phase, nmis, cmds}; default: phase "boot" only
//   entry, nmi, fdc                the field's label, the NMI address, the FDC command register
//   setup(h)                       after open(), before the boot
// WHAT phX's HAD THAT THIS DOES NOT, to add if the port needs it: files unpacked as they land
// (checked at their unpack's start, the depacker's source inside them); held fields (a window
// allowed past its deadline while the screen before it is held); the tunes' READY rows; a
// --restart run through the sequence's end and its warm reload.
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { pathToFileURL } from "node:url";

import { cli, num, open } from "../../tools/harness.mjs";

const { pos, opt } = cli();
const [disc, configPath] = pos;
if (!configPath) { console.error("usage: node examples/verify_disc/verify_disc.mjs DISC CONFIG.mjs [FIELDS]"); process.exit(2); }
const cfg = (await import(pathToFileURL(resolve(configPath)).href)).default;
const N = num(pos[2], 600);
const h = await open({ name: "verify_disc", disc });
h.model = opt.model || (h.define("MASTER") ? "Master" : h.model);
if (cfg.setup) await cfg.setup(h);
const hex = (v, w = 4) => "&" + v.toString(16).toUpperCase().padStart(w, "0");

// ---- the disc image's catalogue (the oracle); a .dsd is two sides, track by track interleaved
const img = readFileSync(disc);
const sides = [];
if (/\.dsd$/i.test(disc)) {
    const tracks = Math.floor(img.length / 5120) || 1;
    for (let s = 0; s < 2; s++) {
        const b = Buffer.alloc(tracks * 2560);
        for (let t = 0; t < tracks; t++) img.copy(b, t * 2560, (2 * t + s) * 2560, (2 * t + s + 1) * 2560);
        sides.push(b);
    }
} else sides.push(img);
const cat = {};
sides.forEach((ssd, side) => {
    for (let k = 0; k < ssd[0x105] >> 3; k++) {
        const o = 8 + 8 * k, a = 0x100 + o;
        const dir = String.fromCharCode(ssd[o + 7] & 0x7f);
        const name = ssd.subarray(o, o + 7).toString("latin1").replace(/ +$/, "");
        const load = ssd[a] | (ssd[a + 1] << 8);
        const len = ssd[a + 4] | (ssd[a + 5] << 8) | (((ssd[a + 6] >> 4) & 3) << 16);
        const start = ssd[a + 7] | ((ssd[a + 6] & 3) << 8);
        const rec = { side, dir, load, start, len, data: ssd.subarray(start * 256, start * 256 + len) };
        cat[`${dir}.${name}`] = rec;
        if (dir === "$" && !cat[name]) cat[name] = rec;
    }
});

const files = (typeof cfg.files === "function" ? cfg.files(h) : cfg.files || []).map((f) => ({ ...f }));
const windows = (typeof cfg.windows === "function" ? cfg.windows(h) : cfg.windows || []).map((w) => ({ ...w }));
if (!files.length && !windows.length) h.die("the config names no files and no windows: nothing to judge");
const master = /master/i.test(h.model);
const FDC = cfg.fdc !== undefined ? h.addr(cfg.fdc) : num(opt.fdc, master ? 0xfe28 : 0xfe80);
const NMI = cfg.nmi !== undefined ? h.addr(cfg.nmi) : 0x0d00;
const allowed = cfg.discAllowed || ((f) => f.phase === "boot");

let field = 0, phase = "boot";
const fields = [];
let nmiNow = 0, cmdNow = [];
const closeField = () => { fields.push({ field, phase, nmis: nmiNow, cmds: cmdNow }); nmiNow = 0; cmdNow = []; field++; };
const label = (pc) => h.symAt(pc) ?? hex(pc);

await h.boot({ settle: 0, shiftFrames: 50, prepare: (h) => {
    // the field clock: the 6845's VSync, or the config's entry label
    if (cfg.entry) h.onExec(h.need(cfg.entry), () => { closeField(); return false; }, { ...h.gateOf(cfg.entry), afterBoot: false });
    else {
        const via = h.cpu.video.sysvia, set = via.setVBlankInt.bind(via);
        let lvl = false;
        via.setVBlankInt = (on) => { if (on && !lvl) closeField(); lvl = !!on; return set(on); };
    }
    h.onExec(NMI, () => { nmiNow++; return false; }, { anyBank: true, afterBoot: false });
    h.onWrite(FDC, FDC, (a, v) => { cmdNow.push(hex(v, 2)); return false; }, { afterBoot: false });
    for (const [name, lab] of cfg.phases || [])
        h.onExec(h.need(lab), () => { phase = name; return false; }, { ...h.gateOf(lab), afterBoot: false });
    for (const f of files) {
        const c = cat[f.name];
        if (!c || !f.check) continue;
        h.onExec(h.need(f.check), () => {
            if (f.result) return false;
            const at = f.at === "catalogue" ? c.load : h.addr(f.at);
            const where = f.where ?? "main";
            const mem = h.rd(at, c.len, (at >= 0x3000 && at < 0x8000) || (at >= 0x8000 && at < 0xc000) ? where : undefined);
            let wrong = 0, first = -1;
            for (let j = 0; j < c.len; j++) if (mem[j] !== c.data[j]) { wrong++; if (first < 0) first = j; }
            f.result = { field, at: hex(at), bytes: c.len, wrong, ...(wrong ? { firstWrong: `+${first}` } : {}) };
            return false;
        }, { ...h.gateOf(f.check), afterBoot: false });
    }
    for (const w of windows) {
        h.onExec(h.need(w.start), () => { if (w.open === undefined) w.open = field; return false; }, { ...h.gateOf(w.start), afterBoot: false });
        h.onExec(h.need(w.done), () => { if (w.open !== undefined && w.closed === undefined) w.closed = field; return false; }, { ...h.gateOf(w.done), afterBoot: false });
    }
} });
await h.s.runFrames(N);

// 1, 2: the catalogue and the bytes
let ok = true;
const fileReport = files.map((f) => {
    const c = cat[f.name];
    const good = !!c && (!f.check || (f.result && f.result.wrong === 0));
    if (!good) ok = false;
    return { name: f.name, onDisc: !!c, ...(c ? { side: c.side, sectors: Math.ceil(c.len / 256) } : {}),
             check: f.check || null, ...(f.result || (f.check ? { never: `${f.check} never ran` } : {})), ok: good };
});
// 3: the windows
const winReport = windows.map((w) => {
    const dead = typeof w.deadline === "function" ? w.deadline(h) : w.deadline;
    const margin = w.closed === undefined || dead === undefined ? null : dead - w.closed;
    const good = w.closed !== undefined && (margin === null || margin > 0);
    if (!good) ok = false;
    return { name: w.name, opened: w.open ?? null, closed: w.closed ?? null, fields: w.closed !== undefined ? w.closed - w.open : null,
             deadline: dead ?? null, margin, ok: good };
});
// 4: the disc where allowed
const discFields = fields.filter((f) => f.nmis || f.cmds.length);
const outside = discFields.filter((f) => !allowed(f));
if (outside.length) ok = false;
const tally = (xs) => { const o = {}; for (const x of xs) o[x] = (o[x] || 0) + 1; return o; };
h.finish({ fdc: hex(FDC), nmi: hex(NMI), files: fileReport, windows: winReport,
           disc: { fields: discFields.length, byPhase: tally(discFields.map((f) => f.phase)),
                   nmis: discFields.reduce((a, f) => a + f.nmis, 0), commands: discFields.reduce((a, f) => a + f.cmds.length, 0),
                   outside: outside.length, firstOutside: outside[0] ?? null },
           phaseAtEnd: phase }, ok, { samples: fields.length });
