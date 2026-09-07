\ ******************************************************************
\ *	test_lib.asm - proves every file in lib/ assembles together
\ ******************************************************************
\ *	Not a game: dummy hooks, a dummy zero page, every routine and
\ *	every macro instantiated once, both IF branches on. Assemble with
\ *
\ *	  beebasm -i lib/test/test_lib.asm -o lib/test/build/test.bin
\ *	          -D RELEASE=0
\ *
\ *	from the kit's root (and again with -D RELEASE=1 for the other
\ *	branch of the boot stamp). beebasm writes its progress to stderr;
\ *	check the exit code, not the stream.
\ ******************************************************************

CPU 0

\ ---- what the includer must define, all of it -------------------
INCLUDE "lib/beeb.h.asm"

MASTER        = 1               ; loader.asm: load_hazel and unpack_andy
IRQ_UNINSTALL = 1               ; irq.asm: save the MOS's state, uninstall
LOADER_STAGE  = &3000           ; loader.asm: where streams stage
SWR_HAND      = &0A00           ; swram_probe.asm: the five-byte answer
SWR_MAGIC     = &A5
DEBUG_ANY     = 0               ; boot_stamp.asm
VERSION_LINE  = "beeb-port-kit lib test"
DEBUG_DUMMY   = 1               ; a flag to see one BOOT_FLAG line emitted

\ The depackers' zero-page slots, BEFORE anything that uses them -
\ zx02depack.asm's header says why. ZX02 needs all but zxlen; ZX0 needs
\ zxlen too and zxofs as two bytes. A real port instantiates ONE depacker
\ and declares only what that one needs.
ORG &70
.zxsrc  SKIP 2
.zxdst  SKIP 2
.zxofs  SKIP 2
.zxlen  SKIP 2
.zxbit  SKIP 1
.zxwrk  SKIP 2
ASSERT P% <= &100

\ ---- the image ------------------------------------------------
ORG &1900
.test_start

\ the two hooks irq.asm calls
.irq_timer_hook
    CRTC 4, 7                   ; beeb.h.asm's macro, instantiated once
    rts
.irq_vsync_hook
    rts

INCLUDE "lib/zx02depack.asm"
INCLUDE "lib/zx0depack.asm"
INCLUDE "lib/boot_stamp.asm"
INCLUDE "lib/irq.asm"
INCLUDE "lib/keydown.asm"
INCLUDE "lib/loader.asm"

\ zx_unpack is what loader.asm jumps to: the ZX02 depacker, for a new port.
.zx_unpack
    ZX02_DEPACKER

\ Paradroid instantiated the depacker twice; prove a second copy is legal.
.zx_unpack_again
    ZX02_DEPACKER

\ The ZX0 depacker still assembles beside it, for a port that is a ZX0 disc.
.zx0_unpack
    ZX0_DEPACKER

INCLUDE "lib/swram_probe.asm"

\ a caller, so every entry point is referenced at least once
.test_main
    ldx #97 : jsr keydown_int
    ldx #&9e : jsr keydown_inkey
    lda #LO(name) : ldy #HI(name) : ldx #4 : jsr load_bank
    lda #LO(name) : ldy #HI(name) : jsr load_hazel
    lda #0 : ldx #&80 : jsr unpack_andy
    jsr install_irq
    jsr uninstall_irq
    jsr SwrMain
    rts
.name EQUS "Bank0", 13

.test_end

SAVE test_start, test_end

\ ---- !BOOT, at a scratch address --------------------------------
code_p% = P%
BOOT_STAGE = &7E00
CLEAR BOOT_STAGE, BOOT_STAGE + 256
ORG BOOT_STAGE
.bootfile
    BOOT_STAMP_HEAD "Lib test"
    BOOT_FLAG DEBUG_DUMMY, "DEBUG_DUMMY: a flag that is on"
    BOOT_FLAG DEBUG_ANY,   "never printed"
    EQUS "*RUN PARSWR", 13
    BOOT_STAMP_TAIL "Game"
.bootfile_end
ASSERT bootfile_end < BOOT_STAGE + 256
SAVE "lib/test/build/boot.txt", bootfile, bootfile_end    ; to read the stamp back
ORG code_p%

PRINT "test image ", ~test_start, "-", ~test_end, " (", test_end - test_start, " bytes)"
PRINT "!BOOT ", bootfile_end - bootfile, " bytes"
