\ ******************************************************************
\ *	keydown.asm - is a key held? Read straight off the System VIA matrix
\ ******************************************************************
\ *	beeb-port-kit, MIT, Kieran Connell 2026. BeebASM syntax, plain 6502.
\ *
\ *	WHAT IT IS. One write and one read that ask the keyboard matrix
\ *	about ONE key we name, with the MOS's own scan stopped for the 26
\ *	cycles it takes. It works with the MOS interrupt gone (irq.asm),
\ *	which OSBYTE &81 does not, and it is 69 cycles JSR to RTS inclusive
\ *	against OSBYTE's 243 - MEASURED, Paradroid 2026-08-26, by a
\ *	breakpoint pair on the JSR and its return differencing
\ *	elapsed_cycles; the OSBYTE figure taken twice by different routes
\ *	(238 and 237 before the glue was subtracted). docs/raster-timing.md.
\ *	Twelve tests a pass cost ~2,175 cycles instead of ~2,900, and the
\ *	single-line scroll flicker it caused went with it.
\ *
\ *	WHERE IT CAME FROM. Paradroid's keydown and Edge's, which are the
\ *	same eleven instructions with different contracts at each end:
\ *	  https://github.com/kieranhj/paradroid-beeb/blob/main/src/main.asm
\ *	    (~2884-2946: X = negative INKEY byte in, Z set if down - the
\ *	    contract of its 49 OSBYTE &81 call sites, kept)
\ *	  https://github.com/kieranhj/edge-beeb/blob/master/src/keyboard.asm
\ *	    (~9-25: X = internal key number in, N set if down)
\ *	Both entry points are here, sharing the body. keydown_int is the
\ *	body; keydown_inkey converts on the way in and out and costs ~20
\ *	cycles more. Delete the one you do not use.
\ *
\ *	HOW IT WORKS. Port A is the slow bus and port B's low nibble is an
\ *	addressable latch that decides who is listening: write (value << 3)
\ *	| line. Line 3 is the keyboard's write-enable, and dropping it stops
\ *	the hardware's free-running column scan so we can drive the matrix
\ *	ourselves. With DDRA = &7F the low seven bits carry the key number
\ *	OUT (PA0-PA3 column, PA4-PA6 row) and PA7 reads the answer back IN.
\ *	The key number is 0-127, so the bit 7 we write is always 0 and PA7
\ *	stays a clean input. KBD_ORA is &FE4F, NO handshake: &FE41 would
\ *	strobe CA2 and confuse the MOS.
\ *
\ *	SEI, AND IT IS THE ONE THING TO WATCH. The MOS owns the slow bus,
\ *	a sound driver drives the same port A from the IRQ, and this
\ *	sequence must not be interleaved by either. PHP/PLP rather than
\ *	SEI/CLI so a caller that was already masked stays masked. The
\ *	masked window is 26 cycles, and a rupture's T1 fires are deadline-
\ *	driven - so that was the risk measured, not the saving: Paradroid's
\ *	pass rate stayed exactly 25.0 Hz and the rupture held.
\ *
\ *	DDRA IS NOT RESTORED, deliberately. The MOS sets DDRA itself in its
\ *	own scan, and a sound driver that shares the port must save and
\ *	restore DDRA/ORA around its own bursts (Paradroid's SndWrOpen/Close
\ *	do, verified against OSBYTE &81 in its tools/sndtest.asm).
\ *
\ *	THE PHANTOM SIXTH KEY. The BBC's matrix has no diodes, so five keys
\ *	held at once can phantom a sixth, and asking about one key at a
\ *	time does not save you from it (Paradroid, KC on hardware
\ *	2026-08-31: Z, X, K, M and L together fired the debug key C). Both
\ *	ports put every debug key behind CTRL for this reason. A phantom
\ *	that lands on a CONTROL is a different matter and nothing here
\ *	prevents it.
\ *
\ *	KEY NUMBERS MUST BE MEASURED, never recalled: they are hardware
\ *	facts and a wrong one is silent. OSBYTE 121 (X = 16 + the lowest
\ *	key to scan, holding the key in a BASIC session) reports the
\ *	internal number; INKEY(-n) reports the negative form. SHIFT (0)
\ *	and CTRL (1) are BELOW OSBYTE 121's floor - the MOS scan will not
\ *	report keys 0-2 - so those two come from INKEY, calibrated on a
\ *	known key: INKEY -98 is Z whose internal number is 97, so internal
\ *	= the INKEY index less one, SHIFT -1 -> 0, CTRL -2 -> 1 (Edge,
\ *	2026-09-06). Edge's thirty-five and Paradroid's are in their
\ *	main.asm files; `*FX229,1` first, or BASIC eats ESCAPE.
\ *
\ *	THE INCLUDER DEFINES: nothing beyond beeb.h.asm's KBD_* symbols.
\ *
\ *	Fork this into your project; keep this header.
\ *	FORKED into beeb-port-kit/template 2026-09-07, unchanged.
\ ******************************************************************

\ ---- keydown_int: X = internal key number; N set if pressed --------
\ Edge's contract. A = &80 (pressed) or 0 on exit; X and Y clobbered.
.keydown_int
{
    txa
    ldx #KBD_LATCH_OFF
    ldy #KBD_LATCH_ON
    php
    sei
    stx KBD_PORTB               ; stop the free-running scan...
    ldx #KBD_DDRA_SCAN
    stx KBD_DDRA
    sta KBD_ORA                 ; ask about this key
    lda KBD_ORA                 ; PA7 is the answer
    sty KBD_PORTB               ; ...and hand it back
    plp
    and #&80                    ; N = pressed
    rts
}

\ ---- keydown_inkey: X = negative INKEY byte; Z set if pressed ------
\ Paradroid's contract, the one every BBC reference and INKEY(-n)
\ speaks. The INKEY byte EOR &FF is the internal key number.
.keydown_inkey
{
    txa
    eor #&ff                    ; INKEY byte -> internal key number
    tax
    jsr keydown_int             ; A = &80 or 0
    eor #&80                    ; Z set = pressed
    rts
}

\ ******************************************************************
\ *	read_joystick - five keys packed into the C64's joystick byte
\ ******************************************************************
\ *	Edge's, as a WORKED EXAMPLE and commented out: it is what a port
\ *	whose original reads a joystick port wants, because the C64's
\ *	$dc00 byte has bit 0 up, 1 down, 2 left, 3 right, 4 fire and a
\ *	CLEAR bit is pressed, so the original's LSR/BCS chain then runs
\ *	unaltered. keydown clobbers X and Y, hence joy_idx.
\ *
\ *	joy_keys is five bytes of ZERO PAGE in Edge (its redefine-keys
\ *	screen writes them): `ldx joy_keys, y` is then zero-page,Y, which
\ *	LDX has and which is a byte shorter than absolute,Y. The five
\ *	defaults are copied in at boot AFTER the zero-page wipe - a wiped
\ *	joy_keys is five controls bound to key 0, which is SHIFT.
\ *
\ *	.read_joystick
\ *	{
\ *	    lda #&ff
\ *	    sta joy
\ *	    lda #4
\ *	    sta joy_idx
\ *	    .loop
\ *	    ldy joy_idx
\ *	    ldx joy_keys, y
\ *	    jsr keydown_int
\ *	    bpl not_pressed
\ *	    ldy joy_idx
\ *	    lda joy
\ *	    and joy_mask, y
\ *	    sta joy
\ *	    .not_pressed
\ *	    dec joy_idx
\ *	    bpl loop
\ *	    rts
\ *	}
\ *
\ *	.joy_mask     EQUB &fe, &fd, &fb, &f7, &ef
\ *	.joy_defaults EQUB KEY_UP, KEY_DOWN, KEY_LEFT, KEY_RIGHT, KEY_FIRE
\ *
\ *	Edge's measured defaults, internal numbers: Z 97, X 66, K 70,
\ *	M 101, L 86. Measure your own.
\ ******************************************************************
