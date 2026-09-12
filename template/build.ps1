# Build the beeb-port-kit template -> build/game.ssd
#
#   .\build.ps1            assemble into build/
#   .\build.ps1 -Run       assemble and launch b2 on the image (-Beebjit for beebjit)
#   .\build.ps1 -Release   the build for other people: every DEBUG_ flag off
#   .\build.ps1 -Master    the Master 128 path (MASTER=1) -> build/game-master.ssd
#
# Assembles with Baron (https://github.com/waitingforvsync/baron), not BeebASM:
# ../docs/toolchain-baron.md says why and what changed. The Makefile is the same
# build for everything else, and the two produce the SAME IMAGE, byte for byte:
# both stamp !BOOT through tools/build_stamp.py and compress with the zx02 built
# from tools/zx02src/. A change to the pipeline has to land in both.
#
# WHERE THE TOOLS COME FROM, for each of baron, zx02, b2 and beebjit: the
# environment variable of that name in capitals ($env:BARON ...), then bin\,
# then the PATH. Nothing in this file names a path on one particular machine;
# put yours in local.ps1 beside this file (gitignored), which is run first if
# it exists:
#     $env:BARON = 'C:\...\baron.exe'
#     $env:B2    = 'C:\...\b2.exe'
param([switch]$Run, [switch]$Release, [switch]$Master, [switch]$Beebjit)

$ErrorActionPreference = 'Stop'

$root  = $PSScriptRoot
$local = Join-Path $root 'local.ps1'
if (Test-Path $local) { . $local }

# RELEASE and MASTER are passed on EVERY build, so that a build says what it
# is; a bare baron invocation must pass them too.
$relDef = if ($Release) { 'RELEASE=1' } else { 'RELEASE=0' }
$masDef = if ($Master)  { 'MASTER=1' }  else { 'MASTER=0' }
# The disc title says which build it is, so *CAT tells you without booting;
# INFO on the disc says it in full, and the boot shows it. Host filenames are
# lowercase (b2 refuses a disc called .SSD); the title is a DFS name and is not.
$discTitle = 'GAME' + $(if ($Master) { 'M' } else { '' })

$build   = Join-Path $root 'build'
$stem    = 'game' + $(if ($Master) { '-master' } else { '' })
$raw     = Join-Path $build "$stem-raw.ssd"
$ssd     = Join-Path $build "$stem.ssd"
$listing = Join-Path $build "$stem.lst"

function Find-Tool([string]$name) {
    $fromEnv = [Environment]::GetEnvironmentVariable($name.ToUpper())
    if ($fromEnv) {
        if (-not (Test-Path $fromEnv)) { throw "$($name.ToUpper())=$fromEnv does not exist" }
        return $fromEnv
    }
    $inBin = Join-Path $root "bin\$name.exe"
    if (Test-Path $inBin) { return $inBin }
    $onPath = Get-Command $name -CommandType Application -ErrorAction SilentlyContinue |
        Select-Object -First 1
    if ($onPath) { return $onPath.Source }
    return $null
}

# Baron: pin the version - the language is still moving (sections changed on
# 2026-09-06).
$baron = Find-Tool 'baron'
if (-not $baron) { throw "baron not found: set BARON, put baron.exe in bin\ or on the PATH - releases at https://github.com/waitingforvsync/baron/releases" }

# zx02: the vendored source is the compressor (tools/zx02src/VENDORED.md). Built
# into bin\ here as make builds it, when a C compiler is on the PATH.
$zx02 = Find-Tool 'zx02'
if (-not $zx02) {
    $cc = Get-Command cc, gcc, clang -CommandType Application -ErrorAction SilentlyContinue |
        Select-Object -First 1
    if (-not $cc) { throw "zx02 not found and no C compiler (cc, gcc, clang) to build it from tools\zx02src: set ZX02, or put a zx02.exe built from that source in bin\" }
    New-Item -ItemType Directory -Force -Path (Join-Path $root 'bin') | Out-Null
    $zx02 = Join-Path $root 'bin\zx02.exe'
    $srcs = 'compress', 'optimize', 'memory', 'zx02' | ForEach-Object { Join-Path $root "tools\zx02src\src\$_.c" }
    & $cc.Source -O -o $zx02 @srcs
    if ($LASTEXITCODE -ne 0) { throw "building zx02 failed ($LASTEXITCODE)" }
}

Push-Location $root
try {
    # The !BOOT stamp and the flags, exactly as make writes them: the source's
    # time (SOURCE_DATE_EPOCH, else the last commit), not the clock's.
    & python 'tools\build_stamp.py' build "$stem.config" $relDef $masDef
    if ($LASTEXITCODE -ne 0) { throw "build_stamp.py failed ($LASTEXITCODE)" }

    # Baron resolves INCLUDE and INCBIN relative to the INCLUDING FILE; -o and
    # -p are relative to the working directory, which is why this runs from the
    # project root. -v (the listing) goes to STDOUT and is captured. Baron is
    # silent on success and writes diagnostics to STDERR, so there is nothing to
    # trip $ErrorActionPreference; the exit code is what to check. -o writes the
    # disc image. --opt 3 makes SHIFT+BREAK *EXEC !BOOT, the DEV build's text
    # file (*BASIC, CLS, *TYPE INFO, *RUN Game); a RELEASE is --opt 2, *RUN
    # !BOOT, a stub that prints the same stamp INFO holds and runs Game
    # (boot_stamp.6502, BOOT_RUN).
    $bootOpt = if ($Release) { '2' } else { '3' }
    & $baron -o $raw --title $discTitle --opt $bootOpt -D $relDef -D $masDef -v 'src\main.6502' |
        Out-File -FilePath $listing -Encoding utf8
    if ($LASTEXITCODE -ne 0) {
        Remove-Item $raw -ErrorAction SilentlyContinue
        throw "baron failed ($LASTEXITCODE) - see $listing"
    }

    # Baron's image is NOT bootable: the loader runs the ZX02 depacker over the
    # data it loads, and make_disc.py is what compresses it, moves the catalogue
    # load address to the staging address main.6502 expects and lays the files
    # out in boot access order.
    & python 'tools\make_disc.py' --zx02 $zx02 $raw $ssd
    if ($LASTEXITCODE -ne 0) { throw "make_disc.py failed ($LASTEXITCODE)" }
} finally { Pop-Location }

if ($Release) { "RELEASE build: every DEBUG_ flag off" }
if ($Master)  { "MASTER build: the Master 128 path" }
"Built  $ssd"
"       $raw   baron's own output, uncompressed and NOT bootable"
"       $listing   assembly listing"

# The second emulator, for -Run: b2 by default, beebjit with -Beebjit. b-em is
# no longer used (KC, 2026-09-07). Flags from each tool's own help text:
#   b2      -0 FILE loads drive 0, -b attempts to auto-boot, -c CONFIG picks a
#           saved machine configuration (the model comes from b2's config)
#   beebjit -0 FILE, -autoboot, -master for a Master 128, -swram N per bank
if ($Run) {
    if ($Beebjit) {
        $beebjit = Find-Tool 'beebjit'
        if (-not $beebjit) { throw "beebjit not found: set BEEBJIT or put it on the PATH" }
        $emuArgs = @('-0', $ssd, '-autoboot')
        if ($Master) { $emuArgs += '-master' }
        & $beebjit @emuArgs
    } else {
        $b2 = Find-Tool 'b2'
        if (-not $b2) { throw "b2 not found: set B2 or put it on the PATH" }
        & $b2 -0 $ssd -b
    }
}
