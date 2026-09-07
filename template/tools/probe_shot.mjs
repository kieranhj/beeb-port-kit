// probe_shot.mjs - headless jsbeeb: boot a disc, optionally poke the panel's
// last scanline with a probe pattern, and save the active-area screenshot as
// a PNG that scan_png.py can read character by character.
//
// beeb-port-kit template, MIT, Kieran Connell 2026. It exists because the
// palette switch's phase (T1_TUNE2, decision 4) is a property of WHERE ON A
// SCANLINE a ULA write lands, and the only instrument for that is the
// rendered picture, read by pixel - eyeballing a one-scanline feature in an
// MCP screenshot was wrong by 20 cycles twice (docs/layer-0-toolchain.md).
//
// It drives the same MachineSession class the jsbeeb MCP server uses, so the
// import path below is wherever `npx jsbeeb-mcp` cached it; set JSBEEB_SRC
// to that package's src/ directory if the default is stale, and JSBEEB_MODEL
// to "Master" for the MASTER=1 build.
//
//   node tools/probe_shot.mjs build/GAME-200K.SSD out.png [half|one|ruler]
//     (no mode)  the disc as built
//     half       units 0-39 of the panel's last line logical 1, 40-79 logical 0:
//                shows the first palette group AND the logical-0 group in one frame
//     one        the whole line logical 1
//     ruler      logical 3 every eighth unit, else 0
// Writes out.png and out-b.png, ONE FIELD APART, so both frame-lock parities
// are seen (BUGS.md #1). Prints scroll, field_count and frame_count.
import { writeFileSync } from "node:fs";

const DEFAULT_SRC = "C:/Users/khcon/AppData/Local/npm-cache/_npx/e76f2a7d329553db/node_modules/jsbeeb/src";
const src = (process.env.JSBEEB_SRC || DEFAULT_SRC).split("\\").join("/");
const { MachineSession } = await import(`file:///${src}/machine-session.js`);

const [ssd, out, mode] = process.argv.slice(2);
const PANEL_LAST_LINE = 0x4a00 + 3 * 640 + 7;   // PANEL_ADDR + row 3 + scan 7
const s = new MachineSession(process.env.JSBEEB_MODEL || "B-DFS1.2", { tube: false });
await s.initialise();
await s.boot(30);
s.loadDisc(ssd);
s.keyDown(16); s.reset(true); await s.runFrames(50); s.keyUp(16);   // SHIFT+BREAK, held long enough
await s.runFrames(150);
if (mode) {
    for (let u = 0; u < 80; u++) {
        const v = mode === "ruler" ? ((u % 8 === 0) ? 0xff : 0)
                : mode === "half"  ? (u < 40 ? 0x0f : 0)
                : 0x0f;
        s.writeMemory(PANEL_LAST_LINE + u * 8, [v]);
    }
    await s.runFrames(3);
}
writeFileSync(out, await s.screenshotActive());
await s.runFrames(1);
writeFileSync(out.replace(/\.png$/, "-b.png"), await s.screenshotActive());
console.log("scroll", s.readMemory(0x13, 2), "field_count", s.readMemory(0x0b, 1), "frame_count", s.readMemory(0x15, 2));
process.exit(0);
