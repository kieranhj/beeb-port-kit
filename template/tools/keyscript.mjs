// keyscript.mjs - keys pressed by field number, for the CLIs that boot a disc and run it
// unattended (video.mjs, irqprofile.mjs, pcprof.mjs).
//
// beeb-port-kit template, MIT, Kieran Connell 2026. From Stryker's Run's tools/playscript.mjs
// (2026-10-25): its keys are BBC keyboard matrix positions pressed with keyDownRaw, which is what
// a game's own matrix scan (keydown_int, OSBYTE &81) reads - no host key map in between, so the
// jsbeeb 2.0 key-type change (jsbeeb_src.mjs's keys()) cannot reach them.
//
// A schedule is a comma-separated list of presses, fields counted from the end of the boot
// (h.boot() returning):
//
//   FIELD:KEY+LEN     KEY down at FIELD, up LEN fields later
//   FIELD:KEY         KEY down at FIELD and held to the end
//   KEY               held from field 0 (the same as 0:KEY)
//
// KEY is a name from NAMES below (SPACE, RETURN, Z, X, LEFT, F0, ...), or an internal key
// number in decimal (row * 16 + column: Z is 97, X 66, as OSBYTE 121 reports them - measure a
// project's own with the beeb-key-numbers skill), or a matrix position COL/ROW.
//
//   import { parseKeys, applyKeys } from "./keyscript.mjs";
//   const sched = parseKeys("X,400:SPACE+10");
//   for (let f = 0; f < N; f++) { applyKeys(h.s, sched, f); await h.s.runFrames(1); }

// Internal key numbers, the BBC Micro's (the same on the Master's main keyboard): the Advanced
// User Guide's table. Z 97, X 66, SHIFT 0 and CTRL 1 were measured on jsbeeb with OSBYTE 121
// (the template's Layer 0, 2026-09-07); Stryker's Run pressed 1 (48), A (65), Z (97), LEFT (25),
// RIGHT (121), DELETE (89), P (55) by matrix position for weeks of harness runs.
export const NAMES = {
    SHIFT: 0, CTRL: 1,
    Q: 16, 3: 17, 4: 18, 5: 19, F4: 20, 8: 21, F7: 22, MINUS: 23, CARET: 24, LEFT: 25,
    F0: 32, W: 33, E: 34, T: 35, 7: 36, I: 37, 9: 38, 0: 39, UNDERSCORE: 40, DOWN: 41,
    1: 48, 2: 49, D: 50, R: 51, 6: 52, U: 53, O: 54, P: 55, LBRACKET: 56, UP: 57,
    CAPSLOCK: 64, A: 65, X: 66, F: 67, Y: 68, J: 69, K: 70, AT: 71, COLON: 72, RETURN: 73,
    SHIFTLOCK: 80, S: 81, C: 82, G: 83, H: 84, N: 85, L: 86, SEMICOLON: 87, RBRACKET: 88, DELETE: 89,
    TAB: 96, Z: 97, SPACE: 98, V: 99, B: 100, M: 101, COMMA: 102, PERIOD: 103, SLASH: 104, COPY: 105,
    ESCAPE: 112, F1: 113, F2: 114, F3: 115, F5: 116, F6: 117, F8: 118, F9: 119, BACKSLASH: 120, RIGHT: 121,
};

/** A key as keyDownRaw wants it, [column, row]; throws on anything it cannot read. */
export function matrixKey(k) {
    const s = String(k).toUpperCase();
    let m = /^(\d+)\/(\d+)$/.exec(s);
    if (m) return [+m[1], +m[2]];
    const n = s in NAMES ? NAMES[s] : /^\d+$/.test(s) ? +s : NaN;
    if (!Number.isInteger(n) || n < 0 || n > 127)
        throw new Error(`key ${k}: not a name in keyscript.mjs NAMES, an internal key number 0-127, or COL/ROW`);
    return [n & 15, n >> 4];
}

/** "X,400:SPACE+10" -> [{ at, key, until }] (until Infinity: held to the end). */
export function parseKeys(spec) {
    if (!spec) return [];
    return String(spec).split(",").filter(Boolean).map((part) => {
        const m = /^(?:(\d+):)?([^+]+)(?:\+(\d+))?$/.exec(part.trim());
        if (!m) throw new Error(`keys: "${part}" is not FIELD:KEY+LEN, FIELD:KEY or KEY`);
        const at = m[1] ? +m[1] : 0;
        return { at, key: matrixKey(m[2]), name: m[2], until: m[3] ? at + +m[3] : Infinity };
    });
}

/** Press and release what the schedule says for field `f` (call before running field f). */
export function applyKeys(s, sched, f) {
    for (const p of sched) {
        if (p.at === f) s.keyDownRaw(p.key);
        if (p.until === f) s.keyUpRaw(p.key);
    }
}
