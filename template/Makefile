.POSIX:
# ===========================================================================
# Makefile - the template's build, on any POSIX make.
#
#   make            assemble and build build/game.ssd (debug flags on)
#   make release    the build for other people: every DEBUG_ flag off
#   make master     the Master 128 path: build/game-master.ssd
#   make run        build, then launch an emulator (autodetected, or EMU=)
#   make clean      remove build/;  make distclean also removes bin/zx02
#   make help       this list
#
# build.ps1 is the same build for Windows without make, and the two produce
# the SAME IMAGE - not the same files bar a timestamp: both stamp !BOOT with
# tools/build_stamp.py and compress with the same zx02. Check with
#   python tools/dfs.py compare build/game.ssd other/game.ssd
# A change to the pipeline has to land in both.
#
# WHAT IT ASSUMES. baron and python come from $PATH unless overridden; the
# ZX02 compressor is BUILT, not assumed, from the source vendored in
# tools/zx02src/ (its VENDORED.md says why). Nothing here writes a `.exe`
# suffix - the platforms that need one supply it:
#
#   PYTHON=python3   BARON=baron   ZX02=bin/zx02   CC=cc   EMU=
#
# An override of ZX02 must name an EXISTING file: it is a prerequisite, and
# only the default has a rule to build it.
#
# THE RULES THIS FOLLOWS are the kit's docs/build-portability.md, each one
# learned from paradroid-beeb issue #3. The two that are easiest to break:
#
#   - `.POSIX:` above is load-bearing. POSIX runs every recipe line under
#     `sh -e`; OpenBSD's make does, GNU make only does with `.POSIX:`. Without
#     it GNU make hides the failure a BSD make reports. So in a recipe an
#     expected non-zero exit is caught as `cmd || rc=$$?`, never with
#     `cmd; rc=$$?` - under -e the shell exits before the `rc=` runs.
#   - No GNU extensions: no $(wildcard), no ifeq, no `%` rules, no `&:`, no
#     `-include`. Every source is listed below; a file main.6502 INCLUDEs
#     that is missing from SRC is a build that silently goes stale.
# ===========================================================================

PYTHON ?= python3
BARON  ?= baron
ZX02   ?= bin/zx02
EMU    ?=

# POSIX's default CC is c99, which MSYS2 (for one) does not have; every
# platform this has been near has cc. `make CC=clang` still wins.
CC = cc

# Passed to baron with -D on every build, so that a build says what it is.
# Set by the `release` and `master` targets through a recursive make.
RELEASE = 0
MASTER  = 0
# The disc's boot option, 2 on every build: SHIFT+BREAK *RUNs !BOOT, the
# stub boot_stamp.6502 assembles, which prints the build stamp and runs the
# game. Never 3: an *EXEC boot writes into DFS's &1100-&1900 (lib/loader.6502
# has the contract) and needs a language ROM to type into.
BOOTOPT = 2
STEM    = game
TITLE   = GAME

# NOT overridable: main.6502 INCLUDEs "../build/build_time.6502".
BUILD   = build
RAW     = $(BUILD)/$(STEM)-raw.ssd
SSD     = $(BUILD)/$(STEM).ssd
LST     = $(BUILD)/$(STEM).lst
CONFIG  = $(BUILD)/$(STEM).config

# Host filenames are lowercase (b2 refuses a disc called .SSD - "unknown
# extension"). The names INSIDE the image - !BOOT, Game, PANEL and the disc
# title - are DFS catalogue entries and keep their case.

SRC = \
  src/main.6502 src/rupture.6502 \
  src/lib/beeb.h.6502 src/lib/boot_stamp.6502 src/lib/irq.6502 \
  src/lib/keydown.6502 src/lib/loader.6502 src/lib/zx02depack.6502 \
  src/data/panel.bin

DISCTOOLS = tools/make_disc.py tools/dfs.py tools/zx02.py

ZX02SRC = \
  tools/zx02src/src/compress.c tools/zx02src/src/optimize.c \
  tools/zx02src/src/memory.c tools/zx02src/src/zx02.c

.PHONY: all debug release master run clean distclean help

# The stamp runs first and on its own, then a second make builds the image.
# That split is the point: build_stamp.py rewrites $(CONFIG) only when the
# time or a flag changed, and the second make judges by that file's mtime.
# A stamp in the same graph would have to run every time, and make counts a
# target whose recipe RAN as updated - so everything would rebuild, always.
all:
	@$(PYTHON) tools/build_stamp.py $(BUILD) $(STEM).config \
	    RELEASE=$(RELEASE) MASTER=$(MASTER)
	@$(MAKE) $(SSD)

debug: all

release:
	@$(MAKE) RELEASE=1 all
	@echo "RELEASE build: every DEBUG_ flag off"

master:
	@$(MAKE) MASTER=1 STEM=game-master TITLE=GAMEM all
	@echo "MASTER build: the Master 128 path"

# Only reached when $(CONFIG) is missing and the image was asked for by
# name (`make build/game.ssd`); `all` always stamps first.
$(CONFIG):
	$(PYTHON) tools/build_stamp.py $(BUILD) $(STEM).config \
	    RELEASE=$(RELEASE) MASTER=$(MASTER)

# Baron's own image. NOT bootable: the loader expects a compressed PANEL.
# A failed assembly removes it, so a half-written image never looks current.
$(RAW): $(SRC) $(CONFIG)
	$(BARON) -o $(RAW) --title $(TITLE) --opt $(BOOTOPT) \
	    -D RELEASE=$(RELEASE) -D MASTER=$(MASTER) -v src/main.6502 \
	    > $(LST) || { rm -f $(RAW); exit 1; }

# The image that boots. make_disc.py writes it through a temporary file and
# prints its SHA256 - the number to compare with another machine's.
$(SSD): $(RAW) $(DISCTOOLS) $(ZX02)
	$(PYTHON) tools/make_disc.py --zx02 $(ZX02) $(RAW) $(SSD)

# The compressor. `-O` is c99's own option, so any cc accepts it. The linker
# adds `.exe` where the platform wants one, and make finds it without being
# told.
bin/zx02: $(ZX02SRC) tools/zx02src/src/zx02.h
	mkdir -p bin
	$(CC) -O -o bin/zx02 $(ZX02SRC)

# b2 and beebjit take their flags from each tool's own help text; any other
# emulator gets the image as its only argument.
run: all
	@emu="$(EMU)"; \
	if [ -z "$$emu" ]; then \
	    for e in b2 beebjit b-em; do \
	        if command -v $$e >/dev/null 2>&1; then emu=$$e; break; fi; \
	    done; \
	fi; \
	case "$$emu" in \
	'') echo "run: no emulator on PATH (b2, beebjit, b-em) - set EMU=" >&2; \
	    exit 1 ;; \
	*b2*) $$emu -0 $(SSD) -b ;; \
	*beebjit*) $$emu -0 $(SSD) -autoboot ;; \
	*) $$emu $(SSD) ;; \
	esac

clean:
	rm -rf $(BUILD)

# bin/ also holds any baron you put there; only the compressor is ours.
distclean: clean
	rm -f bin/zx02

help:
	@echo "make            build/game.ssd, debug flags on"
	@echo "make release    every DEBUG_ flag off"
	@echo "make master     build/game-master.ssd, the Master 128 path"
	@echo "make run        build, then b2/beebjit/b-em from PATH, or EMU="
	@echo "make clean      remove build/ (distclean: and bin/zx02)"
	@echo "overrides:      PYTHON BARON ZX02 CC EMU"
