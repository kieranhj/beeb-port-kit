// Stryker's Run (Enhanced) for the BBC Master, as its tools/passlock.mjs plays it
// (Stryker's Run 4dcf37a, 2026-10-25): the worked example of a game that needs
// the config's functions. pairlock.mjs with this config reproduces passlock's
// verdict on the same pair and seed, pass for pass (the kit's commit says on which
// builds). Use DEBUG_LIVES builds, so the game never ends.
//
//   node tools/pairlock.mjs examples/pairlock/strykers.mjs CONTROL.ssd TEST.ssd --passes 2000 --seed 1 --screen
//
// What it shows a port that has the same problems:
//   - keys read from the GAME's own table (define controls can change them), once
//     the game has loaded: keyOf
//   - a bank map, so the loop and every label are named from the bank paged in
//   - state that is not a range: the helicopter fuel pair is the title tune's
//     pointer until the player first boards one (stateFn)
//   - a table !BOOT's build stamp fills until play overwrites it, zeroed in both
//     at pass 1, so two builds with different stamps compare equal (onFirstPass)
//   - a double-buffered screen whose newest frame may be waiting for its flip,
//     and a 16K hardware-scrolled ring of which 16,000 bytes are shown (screen)
//   - the boot's timing matched to passlock's frame for frame: SHIFT is released
//     after 49 fields, the title's 1 presses are at its frames
// Not carried over: passlock's --unclobber (a fault of builds before its BUGS #12
// fix, undone in the emulator) and its tracing options.

// the start key: 1, internal key number 48 (row 3, column 0), not a game action
const ONE = 48;
// the game's actions in the order of its `keys` table (negative INKEY numbers)
const ACTIONS = ["A", "Z", "RIGHT", "LEFT", "SHIFT", "DELETE", "CTRL", "P", "RUN"];

export default {
    model: "Master",
    banks: { DATA1: 4, DATA2: 5, DATA3: 6, DATA4: 7, andy_data: "andy", hazel_a: "hazel", hazel_b: "hazel", hazel_c: "hazel" },
    loop: "main_game_loop",
    field: "field_count",
    boot: { shiftFrames: 49, settle: 0 },
    // the title alternates the high scores with the options; 1 starts a game only
    // from the options, so it is pressed four times, 300 fields apart
    start: { presses: [0, 1, 2, 3].map((k) => [2100 + 300 * k, "ONE", 40]), maxFrames: 6000 },
    keyOf(h, name) {
        if (name === "ONE") return ONE;
        const i = ACTIONS.indexOf(name);
        if (i < 0) return undefined;
        if (!h._gameKeys) {
            const t = h.rd(h.need("keys"), 9, "main");
            h._gameKeys = ACTIONS.map((_, j) => ~t[j] & 0x7f);
        }
        return h._gameKeys[i];
    },
    // passlock's generator; with PASSLOCK_CTRL it adds [["CTRL", 0.1]] after these
    script: { hold: [10, 80], gap: [0, 10], groups: [[["RIGHT", 0.8], ["LEFT", 0.5]], [["SHIFT", 0.5]], [["DELETE", 0.15]], [["A", 0.2], ["Z", 0.1]]] },
    onFirstPass(h) { h.wr(h.need("movers_helicopter_fuel_high"), new Array(0x22).fill(0), "main"); },
    state: [
        // every mover and projectile table: movers_type_and_colour to projectiles_ttl's end
        { name: "movers", at: "movers_type_and_colour",
          len: (h) => h.need("projectiles_ttl") * 2 - h.need("projectiles_is_rocket") - h.need("movers_type_and_colour") },
        { name: "score", at: "game_over_text+20", len: 6 },
        { name: "fuel", at: "movers_helicopter_fuel_high", len: 0x22 },
        // the zero-page game variables that live from pass to pass
        ...["screen_start_address_low", "screen_start_address_high", "trigger_offset", "new_movers_offset",
            "helicopter_to_update", "player_y_velocity", "player_jump_direction", "player_helicopter",
            "player_firing_cooldown", "player_helicopter_explosion", "bottom_palette_value", "lives",
            "top_palette_value", "firing_frame", "crtc_start_address_high", "crtc_start_address_low",
            "viewport_left_low", "viewport_left_high", "viewport_right_low", "viewport_right_high",
            "movers_to_update_base", "rnd_seed_low", "rnd_seed_high"].map((n) => ({ name: n, at: n, len: 1 })),
    ],
    stateFn(h) {
        // &97/&98 is the title tune's pointer until the player first takes a helicopter
        const inHeli = h.byte(h.need("player_helicopter"));
        return { helicopter_fuel: inHeli ? [h.byte(h.need("helicopter_fuel_high")), h.byte(h.need("helicopter_fuel_low"))] : [0, 0] };
    },
    screen: {
        at: "&4000", len: 0x4000,
        // the newest frame: the one waiting for its flip if there is one (a pass can
        // start before its frame is shown), else the one ACCCON's D bit shows
        shown(h) {
            const fp = h.sym("flip_pending");
            if (fp !== undefined && (h.byte(fp, "main") & 0x80)) return h.byte(h.need("flip_screen"), "main") ? "shadow" : "main";
            return h.cpu.acccon & 1 ? "shadow" : "main";
        },
        // 16,000 bytes from the screen start are shown; the ring's other 384 never are
        visible(h) {
            const start = h.byte(h.need("screen_start_address_low")) | (h.byte(h.need("screen_start_address_high")) << 8);
            return (i) => ((i + 0x8000 - start) & 0x3fff) < 16000;
        },
    },
    // the relocation proof: build.ps1 -Shift 256 -Define DEBUG_LIVES (the game 256
    // bytes lower, each bank's contents 256 higher) against -Shift 256 -ShiftEnd
    // (the same padding where it moves nothing). The files load through &1900-&58FF
    // and MGAME's start-up code sits at &4000-&46FF until the title clears it, so the
    // screen is compared from frame 1500; the column buffer's writes are traced too
    relocate: { entry: "entry_point", compare: [["&4000", 0x4000]], compareFrom: 1500, playFrom: 3100,
                writes: [["&4000", "&7FFF"], ["&0300", "&03FF"]] },
};
