// verify_frame_hooks.mjs - a worked example of tools/verify_frame.mjs --hooks: a demo's sequence.
//
// beeb-port-kit template, MIT, Kieran Connell 2026. From the phX port, 2026-11, where the same
// judgments were written into verify_frame itself, by part name; here they are the shape to
// copy into a port's own tools/ and adapt. Every export is optional.
//
//   HOOK_PART=cur_part HOOK_ROW=row HOOK_DISC_PARTS=0,5 \
//     node tools/verify_frame.mjs build/demo.ssd 3000 --from-first --hooks=examples/verify_frame_hooks.mjs
//
// The build's names come from the environment so the example runs on any build: HOOK_PART a
// byte (the part on screen), HOOK_ROW an optional signed word (the sequence's clock: phX's music
// row), HOOK_DISC_PARTS the parts behind which the disc may run (phX: the card and black; its
// load windows were also row ranges, which discAllowed() would test the same way).
//
// What to adapt:
//   key()        the phase a field is judged in. phX split one part (the Clown) by its own
//                phase byte too, because each of its phases had its own frame
//   steady()     a phase whose field is several CRTC frames (phX's Balls: 4) has that many
//                steady positions
//   firstOk()    a phase change normally enters where the last phase's frame left the 6845;
//                exempt a phase whose last field deliberately makes a different frame (phX:
//                the analyser's and the outro's last fields made the plain frame)
//   discAllowed() where the design lets the disc run (phX decision 32: only behind static
//                screens), and nowhere else
let P, R, DISC;
const s16 = (w) => (w >= 0x8000 ? w - 0x10000 : w);

export function setup(h) {
    P = h.need(process.env.HOOK_PART || "cur_part");
    R = h.sym(process.env.HOOK_ROW || "row");
    DISC = new Set((process.env.HOOK_DISC_PARTS || "").split(",").filter(Boolean).map(Number));
}
export const tag = (h) => ({ part: h.byte(P, "main"), row: R === undefined ? null : s16(h.word(R, "main")) });
export const key = (s) => `part${s.part}`;
export const steady = () => 1;
export const firstOk = () => false;
export const discAllowed = (s) => DISC.has(s.part) || (s.row !== null && s.row < 0);
export function report(samples) {
    const parts = {};
    for (const s of samples) parts[s.part] = (parts[s.part] || 0) + 1;
    const rows = samples.filter((s) => s.row !== null).map((s) => s.row);
    return { parts, rows: rows.length ? { first: rows[0], last: rows[rows.length - 1] } : null };
}
