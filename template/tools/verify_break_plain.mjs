// verify_break_plain.mjs - a plain BREAK (no SHIFT) mid-run leaves a machine you can use.
//
// beeb-port-kit template, MIT, Kieran Connell 2026. From the phX port, 2026-11 (its decision
// 59, after KC's report on a real Master: after a BREAK out of the demo the DFS could not be
// selected until *FX 200,2 and BREAK - the demo's workspace had overwritten its own BREAK
// intercept 196 fields in, and a plain BREAK was a soft one into the demo's leftovers).
//
//   node tools/verify_break_plain.mjs DISC [B,B,...=300,900] [--icpt=SYM] [--banner=A|B|C]
//        [--title=TITLE] [--model=B-DFS1.2|Master] [--shots=DIR]
//
// For each break point B (fields after the boot) a fresh machine runs the disc to B and takes a
// plain BREAK (a soft reset, no key held). Then:
//   - --icpt=SYM: the MOS's BREAK intercept (&0287, *FX 247-249) must still be JMP SYM at B -
//     a port that turns a BREAK into a power-on one does it there, and a port that overwrites
//     page 2 loses it (phX's Ovl5 did)
//   - the MODE 7 screen after the reset must show every --banner string (default: the MOS's
//     banner, a DFS and BASIC - "BBC Computer|DFS|BASIC" on a B, "Acorn MOS|DFS|BASIC" on a
//     Master), and BASIC's prompt
//   - *CAT, typed, must list the disc: its title (--title, default the disc image's own) and
//     !BOOT - the DFS can be used, which is the point
// verify_break.mjs is SHIFT+BREAK, which reboots the disc whatever the intercept says, and so
// cannot see any of this. --shots=DIR saves a screenshot of each machine after *CAT.
import { readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";

import { cli, open } from "./harness.mjs";

const { pos, opt } = cli();
const disc = pos[0];
if (!disc) { console.error("usage: node tools/verify_break_plain.mjs DISC [B,B,...] [--icpt=SYM] [--banner=A|B] [--title=T]"); process.exit(2); }
const points = (pos[1] || "300,900").split(",").map(Number);

// the disc's own title: sector 0's first 8 bytes and sector 1's first 4 (side 0 of a .dsd)
const img = readFileSync(disc);
const title = opt.title || (img.subarray(0, 8).toString("latin1") + img.subarray(0x100, 0x104).toString("latin1"))
    .replace(/\0.*$/s, "").trim();

const results = [];
let ok = true, last;
for (const B of points) {
    const h = last = await open({ name: "verify_break_plain", disc });
    h.model = opt.model || (h.define("MASTER") ? "Master" : h.model);
    const master = /master/i.test(h.model);
    const banner = String(opt.banner || (master ? "Acorn MOS|DFS|BASIC" : "BBC Computer|DFS|BASIC")).split("|");
    await h.boot({ settle: 0, shiftFrames: 50 });
    await h.s.runFrames(B);
    const screen = () => {
        // the MODE 7 screen where the CRTC says it is (R12/R13), in main RAM
        const v = h.cpu.video, start = 0x7c00 | (((v.regs[12] << 8) | v.regs[13]) & 0x3ff);
        const m = h.rd(0x7c00, 1024, "main"), lines = [];
        for (let r = 0; r < 25; r++) {
            let l = "";
            for (let c = 0; c < 40; c++) {
                const b = m[(start - 0x7c00 + r * 40 + c) & 0x3ff] & 127;
                l += b >= 32 && b < 127 ? String.fromCharCode(b) : " ";
            }
            if (l.trim()) lines.push(l.trim());
        }
        return lines;
    };
    let armed = null;
    if (opt.icpt) {
        const icpt = h.rd(0x287, 3), want = h.need(opt.icpt);
        armed = icpt[0] === 0x4c && (icpt[1] | (icpt[2] << 8)) === want;
    }
    h.s.reset(false);
    await h.s.runFrames(150);
    const after = screen();
    await h.s.type("*CAT\r");
    await h.s.runFrames(300);
    const cat = screen();
    if (opt.shots) writeFileSync(join(opt.shots, `break_${B}.png`), await h.s.screenshot());
    const missing = banner.filter((b) => !after.some((l) => l.includes(b)));
    const prompt = after.some((l) => l === ">");
    const listed = cat.some((l) => l.includes(title)) && cat.some((l) => l.includes("!BOOT"));
    const good = armed !== false && missing.length === 0 && prompt && listed;
    if (!good) ok = false;
    results.push({ field: B, armed, bannerMissing: missing, prompt, catListsDisc: listed, screen: after, ok: good });
}
last.finish({ title, results }, ok, { samples: results.length });
