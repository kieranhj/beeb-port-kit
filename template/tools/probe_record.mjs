// probe_record.mjs - record what jsbeeb's 6845 does in ANY disc, one field at a time: no symbols.
//
// beeb-port-kit template, MIT, Kieran Connell 2026. From the phX port, 2026-11 (its step 3:
// watching a shipped demo's technique - a released disc's vertical rupture - run in the
// emulator before writing its own).
//
//   node tools/probe_record.mjs DISC OUT.json FIELD[,FIELD...] [--model=Master] [--settle=50]
//
// Boots DISC (SHIFT+BREAK, held --settle fields) and, for each FIELD (counted in VSyncs from the
// BREAK), records that field: every displayed raster line in order - its bitmap Y, the first
// address fetched, the characters fetched (first and last C0), the scanline (C9) and row (C4)
// counters seen on it - and every CRTC data write (&FE01) with the beam and counters at it:
// [bitmapY, C0, C9, C4, register, value]. OUT.json is the list of fields; one summary line a
// field goes to stdout. A disc with no symbol dump is the point (someone else's demo); a port's
// own build is better watched with its labels (verify_frame.mjs, harness.mjs onWrite).
//
// "Displayed" is every one of jsbeeb's display-enable bits on (video.dispEnabled & 63). Exit 2
// if a field never came (the disc stopped making VSyncs) or nothing was displayed in it.
import { writeFileSync } from "node:fs";

import { cli, num } from "./harness.mjs";
import { keys as keyNames, loadMachineSession, version } from "./jsbeeb_src.mjs";

const { pos, opt } = cli();
const [disc, out, fieldsArg] = pos;
if (!fieldsArg) { console.error("usage: node tools/probe_record.mjs DISC OUT.json FIELD[,FIELD...] [--model=Master]"); process.exit(2); }
const want = fieldsArg.split(",").map(Number).sort((a, b) => a - b);
const MS = await loadMachineSession();
const s = new MS(opt.model || "Master", { tube: false });
await s.initialise();
await s.boot(30);
const cpu = s._machine.processor;
const v = cpu.video;
const K = keyNames();
s.loadDisc(disc);
s.keyDown(K.SHIFT); s.reset(true); await s.runFrames(num(opt.settle, 50)); s.keyUp(K.SHIFT);

let vsyncs = 0, rec = null, vsPrev = false;
const fields = [];
const origSet = v.sysvia.setVBlankInt.bind(v.sysvia);
v.sysvia.setVBlankInt = (on) => {
    if (on && !vsPrev) {
        vsyncs++;
        if (rec) { fields.push(rec); rec = null; }
        if (want.includes(vsyncs)) { rec = { field: vsyncs, lines: [], writes: [] }; L = null; }
    }
    vsPrev = !!on;
    return origSet(on);
};
const origRead = cpu.videoRead.bind(cpu);
let lastY = null, L = null;
cpu.videoRead = (a) => {
    if (rec && (v.dispEnabled & 63) === 63) {
        if (v.bitmapY !== lastY || L === null) {
            lastY = v.bitmapY;
            L = { y: v.bitmapY, a0: a, sc: [], vc: [], n: 0, first: v.horizCounter, last: v.horizCounter };
            rec.lines.push(L);
        }
        L.n++;
        L.last = v.horizCounter;
        if (!L.sc.includes(v.scanlineCounter)) L.sc.push(v.scanlineCounter);
        if (!L.vc.includes(v.vertCounter)) L.vc.push(v.vertCounter);
    }
    return origRead(a);
};
let sel = 0;
cpu.debugWrite.add((addr, val) => {
    if (addr === 0xfe00) sel = val;
    else if (addr === 0xfe01 && rec)
        rec.writes.push([v.bitmapY, v.horizCounter, v.scanlineCounter, v.vertCounter, sel, val]);
    return false;
});
const last = want[want.length - 1];
for (let guard = 0; vsyncs <= last && fields.length < want.length && guard < last * 4 + 400; guard += 10) await s.runFrames(10);
writeFileSync(out, JSON.stringify(fields));
let bad = fields.length < want.length;
for (const f of fields) {
    const rowZero = f.lines.filter((l) => l.vc.length === 1 && l.vc[0] === 0).length;
    const scs = {};
    for (const l of f.lines) { const k = l.sc.join("/"); scs[k] = (scs[k] || 0) + 1; }
    const regs = {};
    for (const w of f.writes) regs[`R${w[4]}`] = (regs[`R${w[4]}`] || 0) + 1;
    if (!f.lines.length) bad = true;
    console.log(JSON.stringify({ field: f.field, displayedLines: f.lines.length, rowZeroLines: rowZero,
        scanlines: scs, crtcWrites: regs, jsbeeb: version() }));
}
if (bad) console.error(`probe_record: ${fields.length} of ${want.length} fields recorded${fields.some((f) => !f.lines.length) ? ", some with nothing displayed" : ""}`);
process.exit(bad ? 2 : 0);
