// acccon_watch.mjs - every CPU write to a Master's ACCCON (&FE34) over a run, by value and by
// the code that made it; fails on any write that sets IRR, TST or IFJ (bits 7-5).
//
// beeb-port-kit template, MIT, Kieran Connell 2026. From the phX port, 2026-11 (its step B7's
// first finding: an analyser's draw wrote CRTC R0's values, &71-&79, to &FE34).
//
// jsbeeb IGNORES those three bits and a real Master does not: TST maps the OS ROM over reads of
// &FC00-&FEFF (the next read of a VIA or the CRTC reads ROM), IFJ moves &FC00-&FDFF to the
// cartridge port, IRR raises an IRQ that nothing clears. So a stray write there is invisible in
// the emulator and a crash, a hang or a wrong colour on the machine. ITU (bit 4, the internal
// Tube) is the MOS's own state (it writes &18): a write that CHANGES it is listed by the code
// that made it, not failed - it is a question for the port, not a fault.
//
//   node tools/acccon_watch.mjs DISC [FIELDS=3000] [--model=Master] [--control]
//
// The watch starts after the harness's boot (the MOS's own writes are not counted); PRESS_WHEN,
// RUN_UNTIL and JUNK (harness.mjs) apply. A Model B has no ACCCON: &FE34 is unmapped there and
// the run is refused (exit 2). --control: the NEGATIVE CONTROL - after the run, one write of
// ACCCON | &20 is made by the harness itself and must be caught (exit 1): run it once on any
// new build of the tool, so the watch is seen to fail.
//
// A WATCH PROVES ONLY THE PATHS THE RUN TOOK. "No bad write in N fields" is about those fields:
// give FIELDS for the whole demo, or one run per part with RUN_UNTIL.
//
// samples = the fields watched (a run with no ACCCON write at all is a pass: nothing set the
// bits), and the JSON: {fields, writes, values: {hex: n}, ituChanged: {"label value": n},
// nBad, bad: [{val, pc, at, romsel, cycles}] (the first 50)}.
import { cli, num, open } from "./harness.mjs";

const { pos, opt } = cli();
const [disc, nArg] = pos;
if (!disc) { console.error("usage: node tools/acccon_watch.mjs DISC [FIELDS] [--model=Master] [--control]"); process.exit(2); }
const N = num(nArg, 3000);
const h = await open({ name: "acccon_watch", disc, model: opt.model || "Master" });
if (!/master/i.test(h.model)) h.die(`${h.model} has no ACCCON: run this on a Master model`);
await h.boot({ settle: 0 });
if (!h.cpu.model.isMaster) h.die(`${h.model} is not a Master in this jsbeeb`);

const hex = (v, n = 2) => "&" + v.toString(16).toUpperCase().padStart(n, "0");
const values = {}, bad = [], itu = {};
let writes = 0, nBad = 0, ctl = false;
h.onWrite(0xfe34, 0xfe34, (addr, val, ctx) => {
    writes++;
    values[hex(val)] = (values[hex(val)] || 0) + 1;
    const at = `${h.symAt(ctx.pc) || hex(ctx.pc, 4)} ${hex(val)}`;
    if ((val ^ ctx.acccon) & 0x10) itu[at] = (itu[at] || 0) + 1;
    if (val & 0xe0) {
        nBad++;
        if (bad.length < 50) bad.push({ val: hex(val), pc: hex(ctx.pc, 4), at: ctl ? "the --control write" : h.symAt(ctx.pc),
                                        romsel: hex(ctx.romsel), cycles: ctx.cycles });
    }
    return false;
});
for (let f = 0; f < N; f += 100) await h.s.runFrames(Math.min(100, N - f));
if (opt.control) {
    ctl = true;
    h.wr(0xfe34, [h.cpu.acccon | 0x20]);        // IFJ: jsbeeb ignores it, the watch must not
    h.wr(0xfe34, [h.cpu.acccon & 0x1f]);
}
if (opt.control && nBad === 0) console.error("acccon_watch: --control: the harness's own bad write was NOT caught - the watch is broken");
h.finish({ disc, fields: N, writes, values, ituChanged: itu, nBad, bad, control: !!opt.control }, nBad === 0, { samples: N });
