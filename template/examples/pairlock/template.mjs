// The template's own game for pairlock.mjs / passbench.mjs / lockstep.mjs /
// tracediff.mjs (tools/passplay.mjs says what each field is). Every address is a
// name from build/game.symbols.json.
//
//   node tools/pairlock.mjs examples/pairlock/template.mjs build/game.ssd build/game.ssd
//
// The template has no game to speak of: a strip that Z and X scroll, at 25 Hz. Its
// game state is the scroll offset and the pass counter; its "screen" the strip.
export default {
    loop: "main_loop",                  // a pass: one main_loop (FRAME_LOCK = 2 fields)
    field: "field_count",
    boot: { shiftFrames: 50, settle: 0 },
    start: { presses: [], maxFrames: 400 },   // no title: the loop starts by itself
    keys: { LEFT: "KEY_LEFT", RIGHT: "KEY_RIGHT" },    // internal numbers, from the dump
    script: { hold: [5, 40], gap: [0, 10], groups: [[["RIGHT", 0.6], ["LEFT", 0.6]]] },
    state: [
        { name: "scroll", at: "scroll", len: 2 },
        { name: "frame_count", at: "frame_count", len: 2 },
        { name: "crtc_park", at: "crtc_park", len: 2 },
    ],
    screen: { at: "BUF_BASE", len: "BUF_SIZE", shown: () => "main" },
    // the relocation proof (lockstep.mjs, tracediff.mjs): build.ps1 -Shift 256 and
    // its control, -Shift 256 -ShiftEnd
    relocate: { entry: "main", compare: [["BUF_BASE", "BUF_SIZE"], ["PANEL_ADDR", "PANEL_BYTES"]], compareFrom: 60 },
};
