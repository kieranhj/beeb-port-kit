// range_free_example.mjs - a DRIVER for range_free.mjs, and its sanity check.
//
//   node lib/test/break_test.mjs          (builds lib/test/build/brktest.ssd + .json)
//   SYMBOLS=lib/test/build/brktest.json RANGES=200-3ff BLOCK=128 //     node lib/test/range_free.mjs lib/test/build/brktest.ssd lib/test/range_free_example.mjs
//
// break_test.6502 never takes IRQ1V, so the MOS still owns the machine while it
// spins: range_free MUST report foreign writes (the MOS's, &0240-&02CD - &02B6-&02BE
// among them, the clock) and BREAK needing &0200-&02FF, and exit 1. A
// range_free that passes this has stopped measuring. jsbeeb 2.10.2, 2026-10-25:
// 27 foreign bytes, all by the MOS, and the blocks &0200-&027F (every pattern) and
// &0280-&02FF (all but zero) needed by BREAK. A real driver boots the game, calls
// ctx.startWatch() once install_irq has run, and plays everything.
export async function drive(s, ctx) {
    await s.autoboot();
    await ctx.runTo(ctx.sym("bt_ready"));
    ctx.startWatch("spin");
    await s.runFrames(200);
}
