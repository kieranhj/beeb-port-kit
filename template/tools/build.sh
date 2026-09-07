#!/bin/sh
# The same build as build.ps1, from bash (Git Bash on Windows, or a Unix host
# with a baron on the path). Same names and disc titles as build.ps1. Flags
# come from the environment:
#   RELEASE=1 MASTER=1 sh tools/build.sh
# BUILD_TIME is stamped into !BOOT (Baron has no TIME$) through the generated
# build/build_time.6502 that main.6502 includes; set it in the environment to
# get a byte-identical rebuild. Run from the project root - Baron resolves
# INCLUDE/INCBIN relative to the including file, but -o/-p are relative to cwd.
set -e
R=${RELEASE:-0}; M=${MASTER:-0}
BARON=${BARON:-/c/Users/khcon/OneDrive/BEEB/Bin/baron.exe}
[ -x bin/baron.exe ] && BARON=bin/baron.exe
T=${BUILD_TIME:-$(date '+%d %b %Y %H:%M:%S')}
STEM=GAME; TITLE=GAME
[ "$M" = 1 ] && { STEM=$STEM-MASTER; TITLE=${TITLE}M; }
mkdir -p build
printf 'BUILD_TIME = "%s"\n' "$T" > build/build_time.6502
"$BARON" -o build/$STEM-RAW.SSD --title "$TITLE" --opt 3 \
    -D RELEASE=$R -D MASTER=$M -v src/main.6502 > build/$STEM.lst
python tools/make_disc.py build/$STEM-RAW.SSD build/$STEM.SSD
