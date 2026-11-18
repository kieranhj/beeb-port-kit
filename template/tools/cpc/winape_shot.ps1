<#
.SYNOPSIS
WinAPE on a CPC disc, window captures at wall-clock times: the third-party half of the reference's
Layer 1 gate (winape_match.py compares them with cpcboot.py's fields).

.DESCRIPTION
From the phX port, 2026-11 (its tools/winape_shot.ps1): the WinAPE path made a parameter, the
HighDpiAware compatibility layer set here instead of by the caller, the window re-found at
every capture.

Launches WinAPE with the disc (and -Extra, by default /A: autorun), then captures the emulator's
window at each -At second (or every -Every seconds to -Until) after launch, with PrintWindow, so
the window need not be in front. Files OUT\t<ms>.png (ms since launch, from a stopwatch) and
OUT\log.txt (one line a capture: ms, file). WinAPE is closed after the last capture.

WinAPE is a Delphi application: its process's MainWindowHandle is the hidden application window,
so the capture is of the LARGEST VISIBLE window the process owns (looked for at every capture:
WinAPE's splash screen is that window for its first seconds, and the kit's copy re-finds the
emulator's when it closes; phX's found it once). -Size W,H moves that window to (0, 0) and sizes it (SetWindowPos) so the whole picture
is shown unscaled; with the HighDpiAware layer (__COMPAT_LAYER, set for the child unless
-NoHighDpi) Windows does not stretch it on a scaled display. phX used -Size 820,720: the picture
at x 3..771, y 58..596, 2 x 2 window pixels a mode-1 pixel (winape_match.py's default box).

THE MACHINE is WinAPE's own settings, saved in WinAPE.ini beside the exe, not set here. Set them
once in WinAPE's Settings dialog and keep a copy of WinAPE for verification only:
  - a CPC 6128 (the 6128 ROMs, 128K), not a Plus / GX4000 (no ASIC),
  - CRTC type 0 (or whichever type the demo's own test is meant to find, the same as cpcboot
    --crtc-type),
  - no PAL / TV filter, no scanline effect, no stretch or smoothing (the picture's pixels must
    be the Gate Array's colours: winape_match.py quantises WinAPE's 0/99/247 levels),
  - 100% speed (the capture times are wall clock), sound may be off.
(The key names in WinAPE.ini were not written down here: set them by the dialog, then copy the
ini.) Timing is wall clock: a loaded host delays a capture; the ms in the file name is when it
was really taken.

Known defects: a capture is only as exact as the host's scheduling (a few ms); WinAPE's start-up
time before the CPC's reset is not measured (winape_match.py's t0 absorbs it); captures while
the splash screen is up are of the splash (winape_match.py scores them low and skips them); a
dialog larger than the emulator's window would be captured instead of it; when the window
changes and -Size is given the capture waits 300 ms for the resize, so that one is late.

.PARAMETER Disc
The DSK to insert (passed to WinAPE as its first argument).
.PARAMETER Out
The directory for the captures (created).
.PARAMETER At
Capture times in seconds after launch (default 15).
.PARAMETER Every
A capture every this many seconds, to -Until (replaces -At).
.PARAMETER Until
The last capture time for -Every.
.PARAMETER Extra
WinAPE's arguments after the disc (default /A: autorun the disc).
.PARAMETER Size
W,H: move the window to (0, 0) and size it, so the picture is unscaled.
.PARAMETER Exe
WinAPE.exe. Default: $env:WINAPE, else WinApe.exe on the PATH.
.PARAMETER NoHighDpi
Do not set __COMPAT_LAYER=HighDpiAware for WinAPE.

.EXAMPLE
.\winape_shot.ps1 -Disc demo.dsk -Out work\winape\run1 -Every 0.5 -Until 340 -Size 820,720
.EXAMPLE
.\winape_shot.ps1 -Disc demo.dsk -Out work\winape\peek -At 8,25 -Exe 'D:\WinAPE\WinApe.exe'
#>
param([Parameter(Mandatory = $true)][string]$Disc, [Parameter(Mandatory = $true)][string]$Out,
      [double[]]$At = @(15), [double]$Every = 0, [double]$Until = 0,
      [string]$Extra = '/A', [int[]]$Size = @(), [string]$Exe = '', [switch]$NoHighDpi)

if (-not $Exe) { $Exe = $env:WINAPE }
if (-not $Exe) {
  $cmd = Get-Command 'WinApe.exe' -ErrorAction SilentlyContinue
  if ($cmd) { $Exe = $cmd.Source }
}
if (-not $Exe -or -not (Test-Path $Exe)) {
  throw "WinAPE not found: pass -Exe, set `$env:WINAPE, or put WinApe.exe on the PATH"
}
if (-not (Test-Path $Disc)) { throw "no disc: $Disc" }
$Disc = (Resolve-Path $Disc).Path

Add-Type @"
using System;
using System.Runtime.InteropServices;
public class W {
  [DllImport("user32.dll")] public static extern bool PrintWindow(IntPtr h, IntPtr dc, uint f);
  [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
  public struct RECT { public int L, T, R, B; }
  public delegate bool EnumProc(IntPtr h, IntPtr l);
  [DllImport("user32.dll")] public static extern bool EnumWindows(EnumProc f, IntPtr l);
  [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h, out uint pid);
  [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr h);
  [DllImport("user32.dll")] public static extern bool SetWindowPos(IntPtr h, IntPtr after, int x, int y, int w, int ht, uint f);
  public static IntPtr Biggest(uint pid) {
    IntPtr best = IntPtr.Zero; long area = 0;
    EnumWindows((h, l) => { uint p; GetWindowThreadProcessId(h, out p);
      if (p == pid && IsWindowVisible(h)) { RECT r; GetWindowRect(h, out r);
        long a = (long)(r.R - r.L) * (r.B - r.T); if (a > area) { area = a; best = h; } }
      return true; }, IntPtr.Zero);
    return best;
  }
}
"@
Add-Type -AssemblyName System.Drawing
New-Item -ItemType Directory -Force $Out | Out-Null
if ($Every -gt 0) { $At = @(); for ($i = 1; $i * $Every -le $Until + 1e-9; $i++) { $At += $i * $Every } }
$log = Join-Path $Out 'log.txt'
$oldLayer = $env:__COMPAT_LAYER
if (-not $NoHighDpi) { $env:__COMPAT_LAYER = 'HighDpiAware' }
try {
  $p = Start-Process $Exe -ArgumentList "`"$Disc`" $Extra" -PassThru
} finally {
  $env:__COMPAT_LAYER = $oldLayer
}
$sw = [System.Diagnostics.Stopwatch]::StartNew()
$h = [IntPtr]::Zero
foreach ($s in $At) {
  while ($sw.Elapsed.TotalSeconds -lt $s) { Start-Sleep -Milliseconds 5 }
  if ($p.HasExited) { break }
  $nh = [W]::Biggest([uint32]$p.Id)                # every capture: the splash screen goes away
  if ($nh -ne $h) {
    $h = $nh
    if ($Size -and $h -ne [IntPtr]::Zero) {      # the whole picture, unscaled
      [W]::SetWindowPos($h, [IntPtr]::Zero, 0, 0, $Size[0], $Size[1], 0x0014) | Out-Null   # NOZORDER | NOACTIVATE
      Start-Sleep -Milliseconds 300
    }
  }
  if ($h -eq [IntPtr]::Zero) { continue }
  $r = New-Object W+RECT
  [W]::GetWindowRect($h, [ref]$r) | Out-Null
  $w = $r.R - $r.L; $ht = $r.B - $r.T
  if ($w -le 0) { $h = [IntPtr]::Zero; continue }
  $ms = [int]$sw.Elapsed.TotalMilliseconds
  $bmp = New-Object System.Drawing.Bitmap $w, $ht
  $g = [System.Drawing.Graphics]::FromImage($bmp)
  $dc = $g.GetHdc(); [W]::PrintWindow($h, $dc, 2) | Out-Null; $g.ReleaseHdc($dc)   # 2: PW_RENDERFULLCONTENT
  $f = Join-Path $Out ("t{0:000000}.png" -f $ms)
  $bmp.Save($f, [System.Drawing.Imaging.ImageFormat]::Png)
  $g.Dispose(); $bmp.Dispose()
  Add-Content $log "$ms $f"
}
if (-not $p.HasExited) { $p.Kill() }
$n = if (Test-Path $log) { (Get-Content $log).Count } else { 0 }
"captures: $n in $Out"
