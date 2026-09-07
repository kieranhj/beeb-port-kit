\ ZX02 depacker, wrapped for bench_depack.py: set the two pointers, unpack
\ STREAM to OUT, stop. Assembled by the harness with -D STREAM= and -D OUT=, FROM THE KIT ROOT;
\ the 23-byte prologue is subtracted from the size it reports.

ORG &70
.zxsrc SKIP 2
.zxdst SKIP 2
.zxofs SKIP 1
.zxbit SKIP 1
.zxwrk SKIP 2

INCLUDE "lib/zx02depack.asm"

ORG &2000
.start
  LDA #LO(STREAM) : STA zxsrc
  LDA #HI(STREAM) : STA zxsrc+1
  LDA #LO(OUT)    : STA zxdst
  LDA #HI(OUT)    : STA zxdst+1
  JSR zx_unpack
  STA &FF00           \ stop marker for the harness
  RTS
.zx_unpack
  ZX02_DEPACKER
.end
SAVE "lib/test/bench/build/zx02.bin", start, end
