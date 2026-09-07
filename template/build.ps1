# Build the beeb-port-kit template -> build/GAME.SSD
#
#   .\build.ps1            assemble into build/
#   .\build.ps1 -Run       assemble and launch b2 on the image (-Beebjit for beebjit)
#   .\build.ps1 -Release   the build for other people: every DEBUG_ flag off
#   .\build.ps1 -Master    the Master 128 path (MASTER=1)
#
# Assembles with Baron (https://github.com/waitingforvsync/baron), not BeebASM:
# ../docs/toolchain-baron.md says why and what changed. Modelled on edge-beeb's
# build.ps1. tools/build.sh is the same from bash.
param([switch]$Run, [switch]$Release, [switch]$Master, [switch]$Beebjit)

$ErrorActionPreference = 'Stop'

# RELEASE and MASTER are passed on EVERY build, so that a build says what it
# is; a bare baron invocation must pass them too. The build timestamp is NOT a
# -D: Baron has no TIME$, and Windows PowerShell cannot hand a quoted string
# with spaces to a native exe intact, so the time goes into a generated source
# file instead (below) - which main.6502 INCLUDEs, and which makes a rebuild
# byte-identical if you keep the file.
$relDef = if ($Release) { 'RELEASE=1' } else { 'RELEASE=0' }
$masDef = if ($Master)  { 'MASTER=1' }  else { 'MASTER=0' }
# The disc title says which build it is, so *CAT tells you without booting;
# !BOOT stamps the same thing where you cannot miss it.
$discTitle = 'GAME' + $(if ($Master) { 'M' } else { '' })

$root    = $PSScriptRoot
$build   = Join-Path $root 'build'
$stem    = 'GAME' + $(if ($Master) { '-MASTER' } else { '' })
$raw     = Join-Path $build "$stem-RAW.SSD"
$ssd     = Join-Path $build "$stem.SSD"
$listing = Join-Path $build "$stem.lst"

# Baron: a local bin\ copy wins; else the shared BEEB\Bin. Pin the version -
# the language is still moving (sections changed on 2026-09-06).
$baron = Join-Path $root 'bin\baron.exe'
if (-not (Test-Path $baron)) { $baron = 'C:\Users\khcon\OneDrive\BEEB\Bin\baron.exe' }
if (-not (Test-Path $baron)) { throw "baron.exe not found at $baron - releases at https://github.com/waitingforvsync/baron/releases" }

# The second emulator, for -Run: b2 by default, beebjit with -Beebjit. b-em is
# no longer used (KC, 2026-09-07). Flags from each tool's own help text:
#   b2      -0 FILE loads drive 0, -b attempts to auto-boot, -c CONFIG picks a
#           saved machine configuration (the model comes from b2's config)
#   beebjit -0 FILE, -autoboot, -master for a Master 128, -swram N per bank
$b2 = 'C:\Users\khcon\OneDrive\BEEB\b2\b2.exe'
$beebjitExe = 'C:\Users\khcon\OneDrive\BEEB\beebjit_win_0.9.5\beebjit.exe'

if (-not (Test-Path $build)) { New-Item -ItemType Directory -Path $build | Out-Null }

# The build stamp, as a source file main.6502 includes. One line, one symbol.
$stamp = Join-Path $build 'build_time.6502'
('BUILD_TIME = "' + (Get-Date -Format 'dd MMM yyyy HH:mm:ss') + '"') |
    Out-File -FilePath $stamp -Encoding ascii

# Baron resolves INCLUDE and INCBIN relative to the INCLUDING FILE (BeebASM used
# the working directory), so where this runs from no longer matters; it still
# runs from the project root so that -o and -p paths read as they do here.
# -v (the listing) goes to STDOUT and is captured, along with the PRINT report.
# Baron is silent on success and writes diagnostics to STDERR, so unlike beebasm
# there is nothing here to trip $ErrorActionPreference; the exit code is still
# what to check. -o writes the disc image, -opt 3 makes it *EXEC !BOOT on
# SHIFT+BREAK, and main.6502 assembles its own !BOOT with the build kind in it.
Push-Location $root
try {
    & $baron -o $raw --title $discTitle --opt 3 -D $relDef -D $masDef -v 'src\main.6502' |
        Out-File -FilePath $listing -Encoding utf8
    if ($LASTEXITCODE -ne 0) { throw "baron failed ($LASTEXITCODE) - see $listing" }
} finally { Pop-Location }

# Baron's image is NOT bootable: the loader runs the ZX02 depacker over the
# data it loads, and make_disc.py is what compresses it, moves the catalogue
# load address to the staging address main.asm expects, lays the files out
# in boot access order and writes the padded 200K copy for emulators.
Push-Location $root
try {
    & python 'tools\make_disc.py' $raw $ssd
    if ($LASTEXITCODE -ne 0) { throw "make_disc.py failed ($LASTEXITCODE)" }
} finally { Pop-Location }

if ($Release) { "RELEASE build: every DEBUG_ flag off" }
if ($Master)  { "MASTER build: the Master 128 path" }
"Built  $ssd"
"       $raw   baron's own output, uncompressed and NOT bootable"
"       $listing   assembly listing"

if ($Run) {
    if ($Beebjit) {
        $emuArgs = @('-0', $ssd, '-autoboot')
        if ($Master) { $emuArgs += '-master' }
        & $beebjitExe @emuArgs
    } else {
        & $b2 -0 $ssd -b
    }
}
