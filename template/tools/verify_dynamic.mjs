// verify_dynamic.mjs - boot the disc and measure what the build DOES, not
// just what it loaded. AND FAIL if it is not what it should do.
//
// beeb-port-kit template, MIT, Kieran Connell 2026. It exists because a
// change can move every address in the program and still be correct - the
// zero-page allocator does exactly that on any edit - and then byte-identity
// proves nothing and only behaviour will do. It is the harness that gated
// the BeebASM -> Baron move and the zero-page allocator
// (docs/layer-0-toolchain.md, ../../docs/toolchain-baron.md).
//
// UNTIL 2026-10-25 IT PRINTED ITS JSON AND EXITED 0 WHATEVER THE NUMBERS SAID,
// which is 1942's BUGS.md #9 exactly: an oracle there answered a well-formed object
// of zeros, exit 0, for weeks. Every figure is asserted now, and it is built on
// tools/harness.mjs, whose exit-code contract (0 pass, 1 wrong or nothing sampled,
// 2 could not judge) is the one every oracle in a port should keep.
//
// What it measures, in one boot:
//   panel        &4A00 read back after the loader has unpacked it, against
//                src/data/panel.bin byte for byte (and written to PANEL.bin if
//                asked, as before)
//   fields       the IRQ's field counter over 100 frames  (expect 100)
//   frames       the main loop's pass counter over those  (expect 100 / FRAME_LOCK
//                = 50: the 25 Hz lock)
//   scrollIdle   the scroll offset with no key held       (expect 0)
//   scrollAfterX the scroll after 50 fields of X held     (expect 50 / FRAME_LOCK
//                x SCROLL_STEP = 200)
// FRAME_LOCK and SCROLL_STEP are the SPEC, read out of the build's own symbol dump
// (checked against the source by asmConst), so a deliberate change to either moves
// the expectation with it. The figures the kit has recorded on both discs since
// 2026-09-07 are 100/50/0/200.
//
//   node tools/verify_dynamic.mjs DISC [MODEL] [PANEL.bin]
//   node tools/verify_dynamic.mjs DISC SCROLL FIELD FRAME [MODEL] [PANEL.bin]
//
// With no addresses it takes `scroll`, `field_count` and `frame_count` from the dump
// beside the disc (build/game.symbols.json for build/game.ssd), which is the form to
// use: tools/verify_cmds.py prints it. The three-address form is kept for the
// commands already written down in the docs; the addresses are HEX, from
//   python tools/listing.py symbols build/game.symbols.json scroll field_count frame_count
// MODEL is jsbeeb's; without one it is "Master" if the build defines MASTER=1 and
// "B-DFS1.2" otherwise. JSBEEB_SRC overrides where jsbeeb lives, as in probe_shot.mjs.
import { existsSync, readFileSync, writeFileSync } from "node:fs";

import { open } from "./harness.mjs";

const argv = process.argv.slice(2);
const isHex = (t) => /^(?:&|0x)?[0-9A-Fa-f]{1,4}$/.test(t || "");
const [disc] = argv;
const explicit = isHex(argv[1]) && isHex(argv[2]) && isHex(argv[3]);
const rest = argv.slice(explicit ? 4 : 1);
if (!disc) {
    console.error("usage: node tools/verify_dynamic.mjs DISC [SCROLL FIELD FRAME] [MODEL] [PANEL.bin]");
    process.exit(2);
}

const h = await open({ name: "verify_dynamic", disc });
h.model = rest[0] || (h.define("MASTER") ? "Master" : "B-DFS1.2");   // the build says which
const panelOut = rest[1];

const H = (t) => parseInt(t.replace(/^(&|0x)/, ""), 16);
const scroll = explicit ? H(argv[1]) : h.zp("scroll");
const field = explicit ? H(argv[2]) : h.zp("field_count");
const frame = explicit ? H(argv[3]) : h.zp("frame_count");
const FRAME_LOCK = h.asmConst("FRAME_LOCK"), SCROLL_STEP = h.asmConst("SCROLL_STEP");
const PANEL_ADDR = h.asmConst("PANEL_ADDR"), PANEL_BYTES = h.asmConst("PANEL_BYTES");

await h.boot({ field });

// the panel, as the loader left it - "main": on a Master &3000-&7FFF is two banks
const panel = h.rd(PANEL_ADDR, PANEL_BYTES, "main");
if (panelOut) writeFileSync(panelOut, Buffer.from(panel));
const panelSrc = "src/data/panel.bin";
let panelDiff = null;
if (existsSync(panelSrc)) {
    const want = readFileSync(panelSrc);
    panelDiff = want.length === panel.length ? panel.filter((b, i) => b !== want[i]).length : -1;
}

// idle: the field counter runs at 50 Hz, the loop at 50 / FRAME_LOCK
const f0 = h.byte(field), p0 = h.word(frame), s0 = h.word(scroll);
await h.s.runFrames(100);
const f1 = h.byte(field), p1 = h.word(frame), s1 = h.word(scroll);

// X held for 50 fields. The key argument is the HOST key, and its TYPE depends on
// the jsbeeb version - jsbeeb_src.mjs's keys() has the detail and the failure it caused.
h.s.keyDown(h.keys.X);
await h.s.runFrames(50);
h.s.keyUp(h.keys.X);
await h.s.runFrames(2);
const s2 = h.word(scroll);

const got = {
    fields: (f1 - f0 + 256) % 256,
    frames: (p1 - p0 + 65536) % 65536,
    scrollIdle: s1 - s0,
    scrollAfterX: s2 - s1,
};
const want = { fields: 100, frames: 100 / FRAME_LOCK, scrollIdle: 0, scrollAfterX: 50 / FRAME_LOCK * SCROLL_STEP };
const wrong = Object.keys(want).filter((k) => got[k] !== want[k]);
if (panelDiff) wrong.push("panel");
for (const k of wrong) console.error(`verify_dynamic: ${k} is ${got[k] ?? panelDiff}, want ${want[k] ?? 0}`);

h.finish({ ...got, panel: panelDiff === null ? "no src/data/panel.bin to compare"
                         : `${panelDiff} of ${PANEL_BYTES} differ`,
           want, wrong, addresses: { scroll, field, frame } },
         wrong.length === 0, { samples: Object.keys(got).length + (panelDiff === null ? 0 : 1) });
