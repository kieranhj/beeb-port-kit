// watch_icpt.mjs - when does the MOS's BREAK intercept stop being yours?
//
// beeb-port-kit template, MIT, Kieran Connell 2026. From the phX port, 2026-11: its plain
// BREAK became a soft one into the demo's workspace because an overlay loaded into page 2
// overwrote the intercept 196 fields in (verify_break_plain.mjs found that it was gone; this
// found when, and who).
//
//   node tools/watch_icpt.mjs DISC [FIELDS=3000] [--target=SYM] [--n=8] [--model=...]
//
// The intercept is three bytes at &0287 (*FX 247-249: a JMP the MOS calls on every BREAK).
// With --target, also the first N bytes of the code it should jump to (a port's BREAK handler
// is usually copied somewhere low, where the next load can overwrite it too). Every field in
// which either changes is printed with the bytes before and after, the field, and every CPU
// write into them since the last field by PC and label. Exit 1 if --target is given and, at
// the end, &0287 is not JMP target or the target's bytes are not the ones it had when the
// intercept was first armed; 0 otherwise (a report - with no --target nothing is judged).
// For writes to any other address, memwatch.mjs (MEMWATCH=287-289) does the same over any
// harness.
import { cli, num, open } from "./harness.mjs";

const { pos, opt } = cli();
const disc = pos[0];
if (!disc) { console.error("usage: node tools/watch_icpt.mjs DISC [FIELDS] [--target=SYM] [--n=8]"); process.exit(2); }
const N = num(pos[1], 3000), NB = num(opt.n, 8);
const h = await open({ name: "watch_icpt", disc });
h.model = opt.model || (h.define("MASTER") ? "Master" : h.model);
const T = opt.target ? h.need(opt.target) : null;
if (T !== null && T >= 0x3000) h.die(`${opt.target} is ${T.toString(16)}: watch_icpt reads RAM below &3000`);
await h.boot({ settle: 0, shiftFrames: 50 });
const hx = (a) => Array.from(a).map((x) => x.toString(16).padStart(2, "0")).join(" ");
const writes = [];
const label = (pc) => `&${pc.toString(16)} ${h.symAt(pc) ?? ""}`.trim();
h.onWrite(0x287, 0x289, (addr, val, c) => { writes.push(`&${addr.toString(16)}=${val.toString(16)} by ${label(c.pc)}`); return false; }, { afterBoot: false });
if (T !== null) h.onWrite(T, T + NB - 1, (addr, val, c) => { writes.push(`&${addr.toString(16)}=${val.toString(16)} by ${label(c.pc)}`); return false; }, { afterBoot: false });
let a = hx(h.rd(0x287, 3)), b = T === null ? "" : hx(h.rd(T, NB));
let armed = null;                        // the target's bytes when &0287 first became JMP target
const isJmp = () => { const i = h.rd(0x287, 3); return T !== null && i[0] === 0x4c && (i[1] | (i[2] << 8)) === T; };
if (isJmp()) armed = b;
const changes = [];
console.error(`start: &0287 ${a}${T !== null ? `   ${opt.target}: ${b}` : ""}`);
for (let f = 0; f < N; f++) {
    await h.s.runFrames(1);
    const a2 = hx(h.rd(0x287, 3)), b2 = T === null ? "" : hx(h.rd(T, NB));
    if (a2 !== a || b2 !== b) {
        const c = { field: f, icpt: [a, a2], ...(T !== null ? { target: [b, b2] } : {}), writes: writes.splice(0) };
        changes.push(c);
        console.error(`field ${f}: &0287 ${a} -> ${a2}${T !== null ? `   ${opt.target}: ${b} -> ${b2}` : ""}  (${c.writes.slice(0, 6).join("; ")})`);
        a = a2; b = b2;
        if (armed === null && isJmp()) armed = b;
    } else writes.length = 0;
}
const holds = T === null ? null : isJmp() && armed !== null && b === armed;
h.finish({ fields: N, target: opt.target || null, final: { icpt: a, target: T === null ? undefined : b }, armedBytes: armed,
           holds, changes: changes.slice(0, 50) }, holds !== false, { samples: N });
