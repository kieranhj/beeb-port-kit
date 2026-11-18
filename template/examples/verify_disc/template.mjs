// The kit template's loader for examples/verify_disc/verify_disc.mjs: its two loads, both
// through the DFS while it boots - Game (*RUN by !BOOT) and the packed PANEL stream
// (loader.6502's load_stream, to LOADER_STAGE, unpacked by unpack_to) - and no disc after
// install_irq takes the machine over. Every address is a name from the build's symbol dump.
//
//   node examples/verify_disc/verify_disc.mjs build/game.ssd examples/verify_disc/template.mjs
//   node examples/verify_disc/verify_disc.mjs build/game-master.ssd examples/verify_disc/template.mjs
export default {
    files: [
        // Game's bytes at its catalogue load address, before its first instruction runs
        { name: "Game", at: "catalogue", check: "main" },
        // the PANEL stream as it landed, before it is unpacked
        { name: "PANEL", at: "LOADER_STAGE", check: "unpack_to" },
    ],
    windows: [
        // the PANEL load: OSFILE in, unpack called; a deadline to show the margin (the
        // template has no screen waiting on it: 400 fields from the BREAK is arbitrary)
        { name: "PANEL", start: "load_stream", done: "unpack_to", deadline: 400 },
    ],
    phases: [["load", "load_stream"], ["run", "install_irq"]],
    // the DFS's own NMIs while it boots and loads; none once the rupture runs
    discAllowed: (f) => f.phase !== "run",
};
