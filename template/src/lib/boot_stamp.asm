\ ******************************************************************
\ *	boot_stamp.asm - a !BOOT that says what build it is
\ ******************************************************************
\ *	beeb-port-kit, MIT, Kieran Connell 2026. BeebASM syntax.
\ *
\ *	WHAT IT IS. Three macros that assemble the disc's !BOOT file with
\ *	the build's own testimony in it: the assembly time from beebasm's
\ *	TIME$, "DEV build" unless RELEASE, one REM per compile flag that is
\ *	on, the version line under RELEASE, then the *RUN. A debug build
\ *	looks like a normal one until the thing you are testing behaves
\ *	oddly; a disc image with no date cannot be matched to a source tree.
\ *	Both ports learned both the hard way, and both now stamp EVERY
\ *	flag that changes what the disc contains (KC's rule), so a build
\ *	cannot lie about itself.
\ *
\ *	WHERE IT CAME FROM.
\ *	  https://github.com/kieranhj/edge-beeb/blob/master/src/main.asm
\ *	    (~1975-2033: one REM per flag, MUSIC_AKL and GFX_CPC stamped
\ *	    OUTSIDE the RELEASE test because they are legal under it)
\ *	  https://github.com/kieranhj/paradroid-beeb/blob/main/src/main.asm
\ *	    (~4500-4591: the DEBUG_ANY fold, ASSERT DEBUG_ANY = 0 under
\ *	    RELEASE, VERSION_LINE in the DEBUG line's seat on a release)
\ *	Edge's shape (a line per flag) is the one here; Paradroid's single
\ *	"REM DEBUG: A B C" line is the same information folded.
\ *
\ *	WHAT WAS MEASURED: nothing electrical. Two facts about the file:
\ *	  - It is a disc file, not code. Edge assembled it inside the code
\ *	    image once and it cost 200 bytes of the tightest region in the
\ *	    build for text nothing executes (its decision 49). Assemble it
\ *	    at a scratch address that exists, that nothing has claimed at
\ *	    assembly time and that it is never loaded to, then put P% back.
\ *	    Paradroid uses &7E00, Edge &2600 (inside its sprite saves).
\ *	  - beebasm's disc option must be 3 (*EXEC), `-opt 3` or the disc
\ *	    builder's equivalent, or the file is never read.
\ *
\ *	THE INCLUDER DEFINES, before this file is included:
\ *	  RELEASE        0 or 1 (both ports pass it on the command line:
\ *	                 beebasm has no IFDEF and refuses a symbol defined
\ *	                 twice, so main.asm cannot carry a default)
\ *	  DEBUG_ANY      the OR of every DEBUG_ flag; the head macro ASSERTs
\ *	                 it is 0 under RELEASE
\ *	  VERSION_LINE   a string, printed under RELEASE (e.g. "v1.0 2026-09-06")
\ *	and then, at a scratch address:
\ *
\ *	  code_p% = P%
\ *	  CLEAR BOOT_STAGE, BOOT_STAGE + 256
\ *	  ORG BOOT_STAGE
\ *	  .bootfile
\ *	  BOOT_STAMP_HEAD "Edge Grinder"
\ *	  BOOT_FLAG DEBUG_COLL,   "DEBUG_COLL: collisions do not kill"
\ *	  BOOT_FLAG DEBUG_TIMING, "DEBUG_TIMING: the frame meter is running"
\ *	  BOOT_FLAG MUSIC_AKL,    "MUSIC_AKL: Arkos replay"    \ legal under RELEASE
\ *	  BOOT_STAMP_TAIL "Edge"
\ *	  .bootfile_end
\ *	  SAVE "!BOOT", bootfile, bootfile_end
\ *	  ASSERT bootfile_end < BOOT_STAGE + 256
\ *	  ORG code_p%
\ *
\ *	BOOT_FLAG emits its line whenever the flag is non-zero, so a flag
\ *	that is legal under RELEASE (a music or artwork variant) is stamped
\ *	by the same macro; the ASSERT on DEBUG_ANY is what keeps DEBUG_
\ *	flags out of a release, not the stamp. Anything with a "*" prefix,
\ *	such as a bank detector to *RUN first (swram_probe.asm), goes
\ *	between BOOT_FLAG and BOOT_STAMP_TAIL as a plain EQUS.
\ *
\ *	Fork this into your project; keep this header.
\ *	FORKED into beeb-port-kit/template 2026-09-07, unchanged.
\ ******************************************************************

\ ---- REM title [DEV build], REM VERSION_LINE under RELEASE ---------
MACRO BOOT_STAMP_HEAD title
IF RELEASE
    ASSERT DEBUG_ANY = 0        ; a release carries no debug at all
    EQUS "REM ", title, 13
    EQUS "REM ", VERSION_LINE, 13
ELSE
    EQUS "REM ", title, " DEV build", 13
ENDIF
ENDMACRO

\ ---- one REM per flag that is on ----------------------------------
MACRO BOOT_FLAG flag, text
IF flag
    EQUS "REM ", text, 13
ENDIF
ENDMACRO

\ ---- REM BUILD <time>, *RUN <file> --------------------------------
MACRO BOOT_STAMP_TAIL runfile
    EQUS "REM BUILD ", TIME$("%d %b %Y %H:%M:%S"), 13
    EQUS "*RUN ", runfile, 13
ENDMACRO
