// verify_vscroll.mjs - THE BUFFER ORACLE for the smooth vertical scroll.
//
// beeb-port-kit template example, MIT, Kieran Connell 2026. Adapted from
// 1942's tools/verify_scroll.mjs, which was itself built to the kit's
// PORTING.md section 6: an oracle is an INDEPENDENT rendering of what the
// thing should hold, diffed at the awkward positions.
//
// It is TWO oracles, because two separate things can be wrong:
//
//   ORACLE A, the strip.  fill_play writes every byte of the 10K ring as a
//     function of its byte OFFSET and nothing else, so the check is a
//     formula, re-derived here from main.6502's comment rather than from its
//     6502. Pass mark: 0 of 10,240.
//
//   ORACLE B, the view.   Given the strip actually read back plus the LIVE
//     scroll position, compute which byte the CRTC must fetch for each of the
//     320 x 120 play pixels, decode MODE 1, and diff against jsbeeb's
//     framebuffer. Pass mark: 0 of 38,400. It fails on a sign error in the
//     direction, an off-by-one in `line`, a wrong R5 pairing, a start address
//     that does not wrap at &8000, or an R8 edge on the wrong line.
//
// It scores the SLIVER separately - the last `line` scanlines of the play
// area, the ones cycle P's vertical total adjust fetches, which exist at all
// only because PLAY_R6 = PLAY_VIS_ROWS + 1. That is the one behaviour this
// frame shape depends on and that Paradroid refused to depend on, so it is
// measured rather than assumed.
//
// It also reports the LIT RUN and the EDGE PHASE:
//   litRun   one unbroken run of 152 scanlines, 320 wide, nothing else lit.
//            The length is itself a test: if the adjust stopped displaying
//            the run would be short by `line` and the number would move with
//            the scroll.
//   edges    the lit width of the first and last two play scanlines. Fire 1's
//            R8 write takes effect immediately, so one landing in displayed
//            time cuts its scanline part-way across and shows here as a short
//            first line. This is the instrument T1_PHASE was measured with.
//
//   node tools/verify_vscroll.mjs DISC CRTC_LIVE LINE_LIVE YPOS [MODEL]
//
// THE **LIVE** POSITION, NOT `ypos`. The main loop computes the next position
// and parks it; the VSync hook takes it FRAME_LOCK fields later (1 here: the
// example runs at 50 Hz), so `ypos` is up to one game tick AHEAD of what is on
// the screen. An oracle fed the
// parked pair scores nearly everything wrong on a correct build (1942, 2026-
// 09-07: 57,284 of 57,344). crtc_live/line_live are what the CRTC was given.
//
// The addresses are HEX and they MOVE on any edit - Baron allocates the zero
// page. Take them from the listing, never from a doc, and never in decimal:
//
//   python ../../tools/listing.py symbols build/vscroll.symbols.json
import { loadMachineSession } from "../../../tools/jsbeeb_src.mjs";
const MachineSession = await loadMachineSession();

// ---- the geometry, from main.6502. Change both or neither. ----------
const BUF_BASE = 0x5800;
const BUF_SIZE = 10240;
const ROW_BYTES = 640;
const PLAY_UNITS = 80;
const PLAY_W = PLAY_UNITS * 4;          // 320 play-pixels
const PLAY_H = 15 * 8;                  // PLAY_VIS_ROWS * 8 = 120
const PANEL_H = 4 * 8;                  // PANEL_ROWS * 8, contiguous below it
const LIT_H = PLAY_H + PANEL_H;         // 152: ONE run, no gaps
const SOLID = [0x00, 0x0f, 0xf0, 0xff]; // solid_bytes: four pixels of 0..3
const MODE1_PHYS = [0, 1, 3, 7];        // the OS's MODE 1 palette: this
                                        // example never writes the ULA
const PHYS_RGB = [
    [0, 0, 0], [255, 0, 0], [0, 255, 0], [255, 255, 0],
    [0, 0, 255], [255, 0, 255], [0, 255, 255], [255, 255, 255],
];
const FB_W = 1024, FB_H = 625;          // jsbeeb's framebuffer: 8 px a CRTC
                                        // character, 2 rows a scanline
const KEY_DOWN = 40;                    // jsbeeb keymap.js keyCodes.DOWN
const RING_LINES = 16 * 8;              // BUF_ROWS * 8: what ypos wraps at
const RATE_FIELDS = 50;                 // FRAME_LOCK = 1, so 50 fields must
                                        // move the view 50 scanlines

// ---- ORACLE A: what fill_play must have written ---------------------
//   row = offset / 640, unit = (offset MOD 640) / 8, scan = offset MOD 8
//   byte = solid_bytes[(row + scan + unit / 4) AND 3]
//   except unit 0 scan 0, which is &88 - the row seam marker
function expectedStrip() {
    const out = new Uint8Array(BUF_SIZE);
    for (let off = 0; off < BUF_SIZE; off++) {
        const row = Math.floor(off / ROW_BYTES);
        const unit = (off % ROW_BYTES) >> 3;
        const scan = off & 7;
        out[off] = (unit === 0 && scan === 0) ? 0x88 : SOLID[(row + scan + (unit >> 2)) & 3];
    }
    return out;
}

// ---- ORACLE B: which byte the CRTC fetches for a play pixel ---------
// The top visible play line is scanline `line` of the buffer row at the live
// start address; play Y counts down from there and the ring wraps at &8000,
// which is BUF_SIZE bytes on from BUF_BASE.
function playPixel(strip, scroll, line, x, y) {
    const v = line + y;
    const off = (scroll + (v >> 3) * ROW_BYTES + (x >> 2) * 8 + (v & 7)) % BUF_SIZE;
    const b = strip[off];
    const i = x & 3;                    // MODE 1: pixel i is bits 7-i and 3-i
    return (((b >> (7 - i)) & 1) << 1) | ((b >> (3 - i)) & 1);
}

// ---- find the picture in the framebuffer ----------------------------
function litExtent(fb, y) {
    let x0 = -1, x1 = -1;
    for (let x = 0; x < FB_W; x++) {
        const p = (y * FB_W + x) * 4;
        if (fb[p] | fb[p + 1] | fb[p + 2]) { if (x0 < 0) x0 = x; x1 = x; }
    }
    return { x0, w: x1 < 0 ? 0 : x1 - x0 + 1 };
}

function locatePlay(fb) {
    const lit = [];
    for (let y = 0; y < FB_H; y++) lit.push(litExtent(fb, y).w > 0);
    const runs = [];
    for (let y = 0; y < FB_H; y++) {
        if (!lit[y]) continue;
        let e = y;
        while (e + 1 < FB_H && lit[e + 1]) e++;
        runs.push({ y0: y, len: e - y + 1 });
        y = e;
    }
    const play = runs.reduce((a, b) => (b.len > (a?.len ?? 0) ? b : a), null);
    if (!play) throw new Error("no lit rows at all - the display is off");
    let x0 = FB_W, x1 = -1;
    for (let y = play.y0; y < play.y0 + play.len; y++) {
        const e = litExtent(fb, y);
        if (e.w) { if (e.x0 < x0) x0 = e.x0; if (e.x0 + e.w - 1 > x1) x1 = e.x0 + e.w - 1; }
    }
    return { extraRuns: runs.length - 1, y0: play.y0, h: play.len, x0, w: x1 - x0 + 1 };
}

// ---- main -----------------------------------------------------------
const [ssd, crtcA, lineA, yposA, model] = process.argv.slice(2);
if (!ssd || !crtcA || !lineA || !yposA) {
    console.error("usage: node tools/verify_vscroll.mjs DISC CRTC_LIVE LINE_LIVE YPOS [MODEL]");
    process.exit(2);
}
const crtcAddr = parseInt(crtcA, 16), lineAddr = parseInt(lineA, 16), yposAddr = parseInt(yposA, 16);
if (![crtcAddr, lineAddr, yposAddr].every(Number.isInteger)) {
    console.error("the three addresses must be hex, from the listing");
    process.exit(2);
}

const s = new MachineSession(model || "B-DFS1.2", { tube: false });
await s.initialise();
await s.boot(30);
s.loadDisc(ssd);
s.keyDown(16); s.reset(true); await s.runFrames(50); s.keyUp(16);   // SHIFT+BREAK
await s.runFrames(200);                 // let the rupture settle

// The field must still be 312 lines, or nothing else here means anything.
const r = await s.runFrames(100);
const fieldCycles = (r?.cyclesRun ?? 0) / 100;

const want = expectedStrip();
let worstStrip = -1, worstView = -1, worstSliver = -1, sliverPixels = 0;
let worstEdge = null, geomBad = 0;
const seenLine = new Set();

// Hold DOWN: one scanline a FIELD at 50 Hz, so 20 fields walk `line` through
// all eight values twice and step the start address across two row boundaries.
s.keyDown(KEY_DOWN);
for (let t = 0; t < 20; t++) {
    await s.runFrames(1);               // one 50 Hz game tick = one field
    const crtc = s.readMemory(crtcAddr, 2).reduce((v, b, i) => v + (b << (8 * i)), 0);
    const scroll = (crtc * 8 - BUF_BASE + BUF_SIZE) % BUF_SIZE;
    const line = s.readMemory(lineAddr, 1)[0];
    const ypos = s.readMemory(yposAddr, 1)[0];
    const strip = Uint8Array.from(s.readMemory(BUF_BASE, BUF_SIZE));

    let stripDiff = 0;
    for (let i = 0; i < BUF_SIZE; i++) if (strip[i] !== want[i]) stripDiff++;

    const fb = s._completeFb8;          // the frame screenshot() would return
    const loc = locatePlay(fb);
    const geomOk = loc.h === LIT_H * 2 && loc.w === PLAY_W * 2 && loc.extraRuns === 0;
    if (!geomOk) geomBad++;

    // THE R8 EDGE shows up in the run's HEIGHT, not in a width: the play
    // pattern contains logical 0, which is black, so "lit" is not the same as
    // "displayed" and a scanline's width is not an instrument. A fire that
    // lands before its target line turns the display on over one of the
    // scanlines that should have been blanked and the run is LONG by one; one
    // that lands in its target's displayed part cuts that line part-way
    // across, which oracle B scores as wrong pixels. Between them they bracket
    // the phase, and that is how T1_PHASE was measured.
    if (!geomOk && !worstEdge) worstEdge = { tick: t, line, litH: loc.h / 2, want: LIT_H };

    let viewDiff = 0, sliverDiff = 0, firstBad = null;
    if (geomOk) {
        for (let y = 0; y < PLAY_H; y++) {
            const inSliver = y >= PLAY_H - line;
            for (let x = 0; x < PLAY_W; x++) {
                const exp = PHYS_RGB[MODE1_PHYS[playPixel(strip, scroll, line, x, y)]];
                const p = ((loc.y0 + y * 2) * FB_W + (loc.x0 + x * 2)) * 4;
                if (fb[p] !== exp[0] || fb[p + 1] !== exp[1] || fb[p + 2] !== exp[2]) {
                    if (!firstBad) firstBad = { x, y, got: [fb[p], fb[p + 1], fb[p + 2]], exp };
                    viewDiff++;
                    if (inSliver) sliverDiff++;
                }
            }
        }
    }

    seenLine.add(line);
    worstStrip = Math.max(worstStrip, stripDiff);
    worstView = Math.max(worstView, geomOk ? viewDiff : PLAY_W * PLAY_H);
    worstSliver = Math.max(worstSliver, sliverDiff);
    sliverPixels += line * PLAY_W;
    console.log(JSON.stringify({
        tick: t, ypos, scroll, line,
        wraps: scroll + (PLAY_H + 8) / 8 * ROW_BYTES > BUF_SIZE,
        strip: `${stripDiff} of ${BUF_SIZE}`,
        litRun: `${loc.w / 2}x${loc.h / 2} at fb ${loc.x0},${loc.y0}` +
                (loc.extraRuns ? ` +${loc.extraRuns} stray lit run(s)` : ""),
        view: geomOk ? `${viewDiff} of ${PLAY_W * PLAY_H}` : "GEOMETRY WRONG",
        sliver: `${sliverDiff} of ${line * PLAY_W}`,
        firstBad,
    }));
}
// THE RATE, measured rather than assumed: with FRAME_LOCK = 1 the hook takes a
// position every field, so 50 fields of a held key move the view 50 scanlines.
// A loop that overran a field would show up here as a smaller number, not as a
// tear - the take only ever happens in vertical blanking.
const rate0 = s.readMemory(yposAddr, 1)[0];
await s.runFrames(RATE_FIELDS);
const rate1 = s.readMemory(yposAddr, 1)[0];
const linesMoved = (rate1 - rate0 + RING_LINES) % RING_LINES;
s.keyUp(KEY_DOWN);

const pass = worstStrip === 0 && worstView === 0 && seenLine.size === 8 &&
             fieldCycles === 39936 && geomBad === 0 && worstEdge === null &&
             linesMoved === RATE_FIELDS;
console.log(JSON.stringify({
    fieldCycles,
    rate: `${linesMoved} scanlines in ${RATE_FIELDS} fields (want ${RATE_FIELDS}: 50 Hz)`,
    linesSeen: [...seenLine].sort((a, b) => a - b),
    worstStrip: `${worstStrip} of ${BUF_SIZE}`,
    worstView: `${worstView} of ${PLAY_W * PLAY_H}`,
    sliverTotal: `${worstSliver} wrong of ${sliverPixels} pixels fetched by the adjust`,
    edgePhase: worstEdge ?? `every field lit ${PLAY_W}x${LIT_H}, one run`,
    pass,
}));
process.exit(pass ? 0 : 1);
