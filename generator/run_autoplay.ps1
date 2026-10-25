<#
Crash regression test: an AI-only autoplay game with the installed mod.

Starts Civilization VII through Steam with the game's own automation suite
(-autojson). The suite plays N turns as an observer, then quits the game.
After the game exits (or after the time limit), the script reports new crash
dumps and the [PASS]/[FAIL] lines that the automation writes to the logs.

Usage:  powershell -ExecutionPolicy Bypass -File run_autoplay.ps1 [-Turns 60] [-TimeoutMinutes 60]

Not yet confirmed in this game build: the exact -autojson syntax, whether the
retail build accepts it, and whether the enabled mods are active in the
automation game. Check the first run by watching the screen.
#>
param(
    [int]$Turns = 60,
    [int]$TimeoutMinutes = 60,
    # OBSERVER sees the whole map and the engine waits to show every move.
    # NONE sees nothing, so there is less to show (faster, but you cannot watch).
    [ValidateSet('OBSERVER', 'NONE', '0')][string]$ObserveAs = 'OBSERVER',
    # Suite file in the autoplay folder. ContinuousAgesTransition.json continues through age transitions.
    [string]$Suite = 'ContinuousAgesAutoplay.json'
)

$ErrorActionPreference = 'Stop'
$steam = 'C:\Program Files (x86)\Steam\steam.exe'
$appId = 1295660
$userData = Join-Path $env:LOCALAPPDATA "Firaxis Games\Sid Meier's Civilization VII"
$logs = Join-Path $userData 'Logs'
$dumpDirs = @((Join-Path $userData 'packagedDumps'), (Join-Path $userData 'dumps'), (Join-Path $env:LOCALAPPDATA 'CrashDumps'))

# Write the suite with the requested turn count.
$template = Join-Path $PSScriptRoot "autoplay\$Suite"
$suite = Join-Path $env:TEMP $Suite
# UTF-8 without a byte-order mark: Windows PowerShell's "-Encoding utf8" adds one,
# and the game ignored a suite file that started with it.
$text = (Get-Content -Raw $template) -replace 'Turns=\d+', "Turns=$Turns" -replace 'ObserveAs=\w+', "ObserveAs=$ObserveAs"
[System.IO.File]::WriteAllText($suite, $text, (New-Object System.Text.UTF8Encoding $false))

# A crash reporter window left by an earlier run (for example an exit crash) keeps Steam from
# starting the game. The crash is already saved in packagedDumps, so close the window.
$reporter = Get-Process -Name 'FiraxisCrashReporter' -ErrorAction SilentlyContinue
if ($reporter -and -not (Get-Process -Name 'Civ7_Win64_*' -ErrorAction SilentlyContinue)) {
    Write-Host "Closing a crash reporter left by an earlier run (started $($reporter[0].StartTime))."
    $reporter | Stop-Process -Confirm:$false
    Start-Sleep -Seconds 3
}

$start = Get-Date
Write-Host "Starting autoplay: $Turns turns, suite $suite"
& $steam -applaunch $appId -autojson $suite -bypassStartButton

# Wait for the game process to start, then to exit.
$deadline = $start.AddMinutes($TimeoutMinutes)
$proc = $null
while (-not $proc -and (Get-Date) -lt $start.AddMinutes(3)) {
    Start-Sleep -Seconds 5
    $proc = Get-Process -Name 'Civ7_Win64_*' -ErrorAction SilentlyContinue | Select-Object -First 1
}
if (-not $proc) { Write-Host 'FAIL: the game did not start within 3 minutes.'; exit 2 }
while (-not $proc.HasExited -and (Get-Date) -lt $deadline) { Start-Sleep -Seconds 15; $proc.Refresh() }
$timedOut = -not $proc.HasExited
$minutes = [math]::Round(((Get-Date) - $start).TotalMinutes, 1)

# Report.
$newDumps = foreach ($d in $dumpDirs) {
    if (Test-Path $d) { Get-ChildItem $d -Recurse -File | Where-Object { $_.LastWriteTime -gt $start -and $_.Name -match 'Civ7|submission' } }
}
$results = Get-ChildItem $logs -File | Where-Object { $_.LastWriteTime -gt $start } |
    Select-String -Pattern '\[PASS\]|\[FAIL\]|Autoplay Turn Limit Hit' -SimpleMatch:$false
Write-Host "Run time: $minutes minutes. Timed out: $timedOut"
if ($newDumps) { Write-Host 'CRASH: new dump files:'; $newDumps | ForEach-Object { Write-Host "  $($_.FullName)" } }
if ($results) { Write-Host 'Automation results:'; $results | ForEach-Object { Write-Host "  $($_.Filename): $($_.Line)" } }
else { Write-Host 'No [PASS]/[FAIL] lines found in the logs written during this run.' }
if ($newDumps) { exit 1 } elseif ($timedOut) { exit 3 } else { exit 0 }
