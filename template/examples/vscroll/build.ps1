# Build the smooth vertical scroll example -> build/VSCROLL.SSD
#
#   .\build.ps1            assemble into build/
#   .\build.ps1 -Run       assemble and launch b2 on the image
#
# Simpler than the template's own build.ps1 on purpose: this example has no
# data files, so nothing is compressed and Baron's own image is bootable.
# There is no build_time.6502 either - !BOOT is three plain lines.
param([switch]$Run)

$ErrorActionPreference = 'Stop'

$root    = $PSScriptRoot
$build   = Join-Path $root 'build'
$ssd     = Join-Path $build 'VSCROLL.SSD'
$listing = Join-Path $build 'VSCROLL.lst'

# Baron: a local bin\ copy wins; else the shared BEEB\Bin. Pin the version.
$baron = Join-Path $root '..\..\bin\baron.exe'
if (-not (Test-Path $baron)) { $baron = 'C:\Users\khcon\OneDrive\BEEB\Bin\baron.exe' }
if (-not (Test-Path $baron)) { throw "baron.exe not found - releases at https://github.com/waitingforvsync/baron/releases" }

$b2 = 'C:\Users\khcon\OneDrive\BEEB\b2\b2.exe'

if (-not (Test-Path $build)) { New-Item -ItemType Directory -Path $build | Out-Null }

Push-Location $root
try {
    & $baron -o $ssd --title VSCROLL --opt 3 -v 'src\main.6502' |
        Out-File -FilePath $listing -Encoding utf8
    if ($LASTEXITCODE -ne 0) { throw "baron failed ($LASTEXITCODE) - see $listing" }
} finally { Pop-Location }

"Built  $ssd"
"       $listing   assembly listing (the zero-page addresses the harness wants)"

if ($Run) { & $b2 -0 $ssd -b }
