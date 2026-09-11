# Build the smooth vertical scroll example -> build/vscroll.ssd
#
#   .\build.ps1            assemble into build/
#   .\build.ps1 -Run       assemble and launch b2 on the image
#
# Simpler than the template's own build.ps1 on purpose: this example has no
# data files, so nothing is compressed and Baron's own image is bootable.
# There is no build_time.6502 either - !BOOT is three plain lines.
#
# Tools are found as the template's are: $env:BARON / $env:B2, then the
# template's bin\, then the PATH. Machine paths go in the template's
# gitignored local.ps1 (..\..\local.ps1), which is run first if it exists.
param([switch]$Run)

$ErrorActionPreference = 'Stop'

$root    = $PSScriptRoot
$tmpl    = Join-Path $root '..\..'
$build   = Join-Path $root 'build'
$ssd     = Join-Path $build 'vscroll.ssd'
$listing = Join-Path $build 'vscroll.lst'

$local = Join-Path $tmpl 'local.ps1'
if (Test-Path $local) { . $local }

function Find-Tool([string]$name) {
    $fromEnv = [Environment]::GetEnvironmentVariable($name.ToUpper())
    if ($fromEnv) {
        if (-not (Test-Path $fromEnv)) { throw "$($name.ToUpper())=$fromEnv does not exist" }
        return $fromEnv
    }
    $inBin = Join-Path $tmpl "bin\$name.exe"
    if (Test-Path $inBin) { return $inBin }
    $onPath = Get-Command $name -CommandType Application -ErrorAction SilentlyContinue |
        Select-Object -First 1
    if ($onPath) { return $onPath.Source }
    return $null
}

# Baron: pin the version.
$baron = Find-Tool 'baron'
if (-not $baron) { throw "baron not found: set BARON, put baron.exe in the template's bin\ or on the PATH - releases at https://github.com/waitingforvsync/baron/releases" }

if (-not (Test-Path $build)) { New-Item -ItemType Directory -Path $build | Out-Null }

Push-Location $root
try {
    & $baron -o $ssd --title VSCROLL --opt 3 -v 'src\main.6502' |
        Out-File -FilePath $listing -Encoding utf8
    if ($LASTEXITCODE -ne 0) {
        Remove-Item $ssd -ErrorAction SilentlyContinue
        throw "baron failed ($LASTEXITCODE) - see $listing"
    }

    # Baron writes 16-bit catalogue addresses, and with a second processor
    # attached those mean the PARASITE. There is no make_disc.py step here to
    # fix them, so mark every file as the host's (dfs.to_host).
    & python (Join-Path $tmpl 'tools\dfs.py') host $ssd
    if ($LASTEXITCODE -ne 0) { throw "dfs.py host failed ($LASTEXITCODE)" }
} finally { Pop-Location }

"Built  $ssd"
"       $listing   assembly listing (the zero-page addresses the harness wants)"

if ($Run) {
    $b2 = Find-Tool 'b2'
    if (-not $b2) { throw "b2 not found: set B2 or put it on the PATH" }
    & $b2 -0 $ssd -b
}
