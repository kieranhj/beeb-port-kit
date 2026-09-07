# Build the beeb-port-kit template -> build/GAME.SSD
#
#   .\build.ps1            assemble into build/
#   .\build.ps1 -Run       assemble and launch b2 on the image (-Beebjit for beebjit)
#   .\build.ps1 -Release   the build for other people: every DEBUG_ flag off
#   .\build.ps1 -Master    the Master 128 path (MASTER=1)
#
# Modelled on edge-beeb's build.ps1. tools/build.sh is the same from bash.
param([switch]$Run, [switch]$Release, [switch]$Master, [switch]$Beebjit)

$ErrorActionPreference = 'Stop'

# RELEASE and MASTER are command-line symbols because beebasm has no IFDEF
# and refuses a symbol defined twice, so main.asm cannot carry a default.
# Both are passed on EVERY build; a bare beebasm invocation must pass them too.
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
$padded  = Join-Path $build "$stem-200K.SSD"
$listing = Join-Path $build "$stem.lst"

# beebasm: a local bin\ copy wins; else the shared BEEB\Bin.
$beebasm = Join-Path $root 'bin\beebasm.exe'
if (-not (Test-Path $beebasm)) { $beebasm = 'C:\Users\khcon\OneDrive\BEEB\Bin\beebasm.exe' }
if (-not (Test-Path $beebasm)) { throw "beebasm.exe not found at $beebasm" }

# The second emulator, for -Run: b2 by default, beebjit with -Beebjit. b-em is
# no longer used (KC, 2026-09-07). Flags from each tool's own help text:
#   b2      -0 FILE loads drive 0, -b attempts to auto-boot, -c CONFIG picks a
#           saved machine configuration (the model comes from b2's config)
#   beebjit -0 FILE, -autoboot, -master for a Master 128, -swram N per bank
$b2 = 'C:\Users\khcon\OneDrive\BEEB\b2\b2.exe'
$beebjitExe = 'C:\Users\khcon\OneDrive\BEEB\beebjit_win_0.9.5\beebjit.exe'

if (-not (Test-Path $build)) { New-Item -ItemType Directory -Path $build | Out-Null }

# beebasm resolves INCLUDE and INCBIN relative to the working directory, so it
# runs from the project root. -v (the listing) goes to STDOUT and is captured;
# the progress messages go to STDERR and are deliberately NOT redirected -
# in PowerShell that wraps each line in an ErrorRecord and trips
# $ErrorActionPreference even when the assembly succeeded. Check the exit code.
# -opt 3 makes the disc *EXEC !BOOT on SHIFT+BREAK; main.asm assembles its own
# !BOOT (with the build kind stamped in it) rather than using -boot.
Push-Location $root
try {
    & $beebasm -i 'src\main.asm' -do $raw -opt 3 -title $discTitle -D $relDef -D $masDef -v |
        Out-File -FilePath $listing -Encoding utf8
    if ($LASTEXITCODE -ne 0) { throw "beebasm failed ($LASTEXITCODE) - see $listing" }
} finally { Pop-Location }

# beebasm's image is NOT bootable: the loader runs the ZX0 depacker over the
# data it loads, and make_disc.py is what compresses it, moves the catalogue
# load address to the staging address main.asm expects, lays the files out
# in boot access order and writes the padded 200K copy for emulators.
Push-Location $root
try {
    & python 'tools\make_disc.py' $raw $ssd $padded
    if ($LASTEXITCODE -ne 0) { throw "make_disc.py failed ($LASTEXITCODE)" }
} finally { Pop-Location }

if ($Release) { "RELEASE build: every DEBUG_ flag off" }
if ($Master)  { "MASTER build: the Master 128 path" }
"Built  $ssd"
"       $padded   padded, for jsbeeb"
"       $raw   beebasm's own output, uncompressed and NOT bootable"
"       $listing   assembly listing"

if ($Run) {
    if ($Beebjit) {
        $emuArgs = @('-0', $padded, '-autoboot')
        if ($Master) { $emuArgs += '-master' }
        & $beebjitExe @emuArgs
    } else {
        & $b2 -0 $padded -b
    }
}
