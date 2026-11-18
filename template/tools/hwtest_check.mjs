// hwtest_check.mjs - a hardware-test disc in jsbeeb before it goes to a real machine: does it
// run, where do its register writes land, and a screenshot to compare with the photograph.
//
// beeb-port-kit template, MIT, Kieran Connell 2026. From the phX port, 2026-11 (its
// tools/hwtest_check.mjs: a hardware test run here first, so that a photograph of a real
// Master that differs is a fact about the hardware, not about the test).
//
//   node tools/hwtest_check.mjs DISC OUT.png [FIELDS=50] [--settle=420] [--entry=draw_entry]
//        [--field=field_count] [--symbols=FILE] [--first] [--jitter=N] [--varies] [--anypos]
//        [--keys=KeyV,KeyP] [--menu-key=Digit3 --menu-text=REGEX [--back-key=Space]]
//        [--dump=FILE [--dump-field=N]] [--model=Master]
//
// The test alone: boot, settle, then FIELDS fields of the contract verify_frame.mjs checks -
// draw (--entry) entered at one beam position (--jitter: the character may spread N), fields
// 39,936 cycles apart, jsbeeb's frame count +1 a field - and every CRTC data write (&FE01) and
// ULA write (&FE20 control, &FE21 palette; &FE34 ACCCON on a Master) after draw entry, by
// register and value, with the line (from draw entry) and the C0 it landed at, over all fields.
// Every field's writes must be the same (register, value, line, C0) as the first's: a timing
// that walks shows here. --varies: a test whose writes change by design (the frame is still
// checked); --anypos: one that enters draw at more than one position. --first: from the first
// field the counter moves (no settle). --keys: press each jsbeeb key code in turn after the
// settle, OUT-kN.png after each.
//
// A MENU DISC (several tests behind a MODE 7 menu): --menu-text=REGEX must be on the screen
// after the boot (OUT-menu.png), --menu-key starts the test, and after the run --back-key
// (default Space) must bring the menu back (OUT-back.png). --symbols names the test's own dump
// (the disc's is the menu's). Keys are jsbeeb key codes ("Digit3", "KeyA", "Space").
//
// --dump=FILE writes one field's writes as JSON (the last, or --dump-field=N).
import { writeFileSync } from "node:fs";

import { cli, num, open } from "./harness.mjs";

const { pos, opt } = cli();
const [disc, out] = pos;
if (!out) { console.error("usage: node tools/hwtest_check.mjs DISC OUT.png [FIELDS] [--entry=LABEL] [--menu-key=K --menu-text=RE] ..."); process.exit(2); }
const N = num(pos[2], 50), SETTLE = num(opt.settle, 420), JIT = num(opt.jitter, 0);
const h = await open({ name: "hwtest_check", disc, symbols: opt.symbols });
h.model = opt.model || (h.define("MASTER") ? "Master" : h.model);
const FIELD = h.zp(opt.field || "field_count");
const ENTRY = h.need(opt.entry || "draw_entry");
const cycles = () => h.cpu.currentCycles + h.cpu.cycleSeconds * 2000000;
const press = async (k, n = 5) => { h.s.keyDown(k); await h.s.runFrames(n); h.s.keyUp(k); };

const textAt = (a, n, w) => String.fromCharCode(...h.rd(a, n, w).map((b) => b & 0x7f));
const wheres = /master/i.test(h.model) ? ["main", "shadow"] : ["main"];
const menuShown = () => wheres.some((w) => new RegExp(opt["menu-text"]).test(textAt(0x7c00, 1000, w)));
const menu = opt["menu-key"] !== undefined;
if (menu) {
    if (!opt["menu-text"]) h.die("--menu-key needs --menu-text=REGEX: what the menu shows");
    await h.boot({ settle: 150 });
    if (!menuShown()) h.die("the menu is not on the MODE 7 screen after the boot");
    writeFileSync(out.replace(/\.png$/, "-menu.png"), await h.s.screenshot());
    await press(opt["menu-key"]);
    await h.s.runFrames(SETTLE);
} else {
    await h.boot(opt.first ? { settle: SETTLE } : { field: FIELD, settle: SETTLE });
}
if (opt.keys) {
    for (const [i, k] of String(opt.keys).split(",").entries()) {
        await press(k); await h.s.runFrames(10);
        writeFileSync(out.replace(/\.png$/, `-k${i + 1}.png`), await h.s.screenshot());
    }
}

let tEntry = null, field = null;
const samples = [], fields = [];
h.onExec(ENTRY, () => {
    if (field) fields.push(field);
    samples.push({ ...h.crtc(), t: cycles(), fc: h.cpu.video.frameCount });
    tEntry = h.s.elapsedCycles;
    field = [];
    return false;
}, h.gateOf(opt.entry || "draw_entry"));
let reg = 0;
const NAME = { 0xfe01: null, 0xfe20: "ula", 0xfe21: "pal", 0xfe34: "acc" };
h.onWrite(0xfe00, 0xfe34, (a, v, c) => {
    if (a === 0xfe00) reg = v;
    if (tEntry === null || !(a in NAME)) return false;
    const d = c.cycles - tEntry;
    field.push({ key: a === 0xfe01 ? `R${reg}=${v}` : `${NAME[a]}&${v.toString(16).padStart(2, "0")}`,
        line: Math.floor(d / 128), hc: c.hc, d, vc: c.vc, sc: c.sc });
    return false;
});
await h.s.runFrames(N + 1);
if (samples.length < 2) h.die(`${samples.length} entries at ${opt.entry || "draw_entry"} in ${N + 1} fields: is that the draw's entry?`, { where: h.where() });
if (opt.dump) writeFileSync(opt.dump, JSON.stringify(fields[opt["dump-field"] === undefined ? fields.length - 1 : +opt["dump-field"]]));
writeFileSync(out, await h.s.screenshot());

const posn = {}, gaps = {}, fcs = {}, hcs = {};
samples.forEach((s, i) => {
    const p = JIT ? `${s.vc}:${s.sc}` : `${s.vc}:${s.sc}:${s.hc}`;
    posn[p] = (posn[p] || 0) + 1;
    hcs[s.hc] = (hcs[s.hc] || 0) + 1;
    if (i) {
        const g = s.t - samples[i - 1].t; gaps[g] = (gaps[g] || 0) + 1;
        const f = s.fc - samples[i - 1].fc; fcs[f] = (fcs[f] || 0) + 1;
    }
});
const writes = {};
for (const f of fields)
    for (const w of f) {
        const e = writes[w.key] || (writes[w.key] = { c0: {}, lines: new Set() });
        e.c0[w.hc] = (e.c0[w.hc] || 0) + 1;
        e.lines.add(w.line);
    }
const span = (s) => {
    const a = [...s].sort((x, y) => x - y), r = [];
    for (const x of a) { const l = r[r.length - 1]; if (l && l[1] === x - 1) l[1] = x; else r.push([x, x]); }
    return r.map(([a, b]) => (a === b ? `${a}` : `${a}-${b}`)).join(",");
};
// every field's writes the same: register/value and line, and with --jitter=0 the C0 too
const sig = (f) => f.map((w) => `${w.key}@${w.line}${JIT ? "" : `:${w.hc}`}`).join(" ");
const walking = opt.varies ? 0 : fields.filter((f) => sig(f) !== sig(fields[0])).length;
const table = Object.entries(writes).map(([k, e]) => ({ w: k, c0: e.c0, lines: span(e.lines) }));
const hcList = Object.keys(hcs).map(Number);
const onePos = opt.anypos || (Object.keys(posn).length === 1 && Math.max(...hcList) - Math.min(...hcList) <= JIT);
const oneGap = Object.keys(gaps).every((g) => Math.abs(+g - 39936) <= JIT) && Object.keys(gaps).length > 0;
const oneFc = Object.keys(fcs).length === 1 && fcs[1] > 0;
let back = null;
if (menu) {
    await press(opt["back-key"] || "Space");
    await h.s.runFor(8_000_000);   // by cycles: jsbeeb counts frames by C4 = R6, which the
    await h.s.runFrames(2);        // test's leftover CRTC state can make very short
    back = menuShown();
    writeFileSync(out.replace(/\.png$/, "-back.png"), await h.s.screenshot());
    if (!back) console.error("hwtest_check: the back key did not bring the menu back");
}
if (!onePos) console.error(`hwtest_check: draw entered at ${Object.keys(posn).length} beam positions (characters ${span(hcList)})`);
if (!oneGap) console.error("hwtest_check: fields are not all 39,936 cycles apart");
if (!oneFc) console.error("hwtest_check: jsbeeb's frame count does not step by one a field");
if (walking) console.error(`hwtest_check: ${walking} fields' writes differ from the first's`);
h.finish({ positions: posn, entryC0: hcs, fieldCycles: gaps, frameCountSteps: fcs, writes: table, menuBack: back, shot: out },
    onePos && oneGap && oneFc && !walking && back !== false, { samples: samples.length });
