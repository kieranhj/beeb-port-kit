// verify_dynamic.mjs - boot the disc and measure what the build DOES, not
// just what it loaded.
//
// beeb-port-kit template, MIT, Kieran Connell 2026. It exists because a
// change can move every address in the program and still be correct - the
// zero-page allocator does exactly that on any edit - and then byte-identity
// proves nothing and only behaviour will do. It is the harness that gated
// the BeebASM -> Baron move and the zero-page allocator
// (docs/layer-0-toolchain.md, ../../docs/toolchain-baron.md).
//
// What it measures, in one boot:
//   panel        &4A00 read back after the loader has unpacked it, written
//                to a file so the caller can diff it against the source
//   fields       the IRQ's field counter over 100 frames  (expect 100)
//   frames       the main loop's pass counter over those  (expect 50: the
//                25 Hz lock, FRAME_LOCK = 2)
//   scrollIdle   the scroll offset with no key held       (expect 0)
//   scrollAfterX the scroll after 50 fields of X held     (expect 200: 25
//                passes of SCROLL_STEP = 8)
//
//   node tools/verify_dynamic.mjs DISC SCROLL FIELD FRAME [MODEL] [PANEL.bin]
//
// The three addresses are hex, and they are ARGUMENTS because Baron allocates
// them and moves them whenever the code changes. Take them from the listing,
// never from a doc:
//
//   python tools/listing.py symbols build/game.symbols.json scroll field_count frame_count
//
// MODEL is jsbeeb's ("B-DFS1.2" by default, "Master" for the MASTER=1 disc).
// JSBEEB_SRC overrides where jsbeeb lives, as in probe_shot.mjs.
//
// It prints one line of JSON, so a build script can assert on it:
//   {"fields":100,"frames":50,"scrollIdle":0,"scrollAfterX":200}
// A BRK anywhere after the boot prints no JSON: it throws "BRK at &xxxx" and
// exits non-zero, because counters read after a crash are not a measurement.
import { writeFileSync } from "node:fs";

import { loadMachineSession, keys, trapBrk } from "./jsbeeb_src.mjs";
const MachineSession = await loadMachineSession();
const K = keys();   // jsbeeb 2.0 changed keyDown from a number to a code string

const [ssd, scrollA, fieldA, frameA, model, panelOut] = process.argv.slice(2);
if (!ssd || !scrollA || !fieldA || !frameA) {
    console.error("usage: node tools/verify_dynamic.mjs DISC SCROLL FIELD FRAME [MODEL] [PANEL.bin]");
    process.exit(2);
}
const scroll = parseInt(scrollA, 16), field = parseInt(fieldA, 16), frame = parseInt(frameA, 16);

const s = new MachineSession(model || "B-DFS1.2", { tube: false });
await s.initialise();
await s.boot(30);
const run = trapBrk(s);
s.loadDisc(ssd);
s.keyDown(K.SHIFT); s.reset(true); await run(50); s.keyUp(K.SHIFT);  // SHIFT+BREAK, held
await run(150);

const rd = (a, n) => s.readMemory(a, n).reduce((v, b, i) => v + (b << (8 * i)), 0);
if (panelOut) writeFileSync(panelOut, Buffer.from(s.readMemory(0x4a00, 2560)));

// idle: the field counter runs at 50 Hz, the loop at 25 (FRAME_LOCK = 2)
const f0 = rd(field, 1), p0 = rd(frame, 2), s0 = rd(scroll, 2);
await run(100);
const f1 = rd(field, 1), p1 = rd(frame, 2), s1 = rd(scroll, 2);

// X held for 50 fields: 25 passes of SCROLL_STEP = 8 -> 200. The key argument
// is the HOST key, not a BBC key number, and its TYPE depends on the jsbeeb
// version - jsbeeb_src.mjs's keys() has the detail and the failure it caused.
s.keyDown(K.X);
await run(50);
s.keyUp(K.X);
await run(2);
const s2 = rd(scroll, 2);

console.log(JSON.stringify({
    fields: (f1 - f0 + 256) % 256,
    frames: p1 - p0,
    scrollIdle: s1 - s0,
    scrollAfterX: s2 - s1,
}));
process.exit(0);
