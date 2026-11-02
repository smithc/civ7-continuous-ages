<#
Crash regression test: an AI-only autoplay game with the installed mod.

Starts Civilization VII through Steam with the game's own automation suite
(-autojson). The suite plays N turns as an observer, then quits the game.
After the game exits (or after the time limit), the script reports new crash
dumps and the [PASS]/[FAIL] lines that the automation writes to the logs.

Usage:  powershell -ExecutionPolicy Bypass -File run_autoplay.ps1 [-Turns 60] [-TimeoutMinutes 60]

Worker mode (parallel games; iterate.py --worker N sets the environment, see gamepool.py):
when CIV7_WORKER is set, the game starts from its executable with the worker's environment
(its own user folders; SteamAppId, so the Steam client serves it without a Steam launch).
The script then follows only its own game process: it writes the process id to
<worker>\game.pid, closes only that game's crash reporter, and reads only that game's
dumps (<pid> in the name) from the real user's CrashDumps folder.
#>
param(
    [int]$Turns = 60,
    [int]$TimeoutMinutes = 60,
    # OBSERVER sees the whole map and the engine waits to show every move.
    # NONE sees nothing, so there is less to show (faster, but you cannot watch).
    [ValidateSet('OBSERVER', 'NONE', '0')][string]$ObserveAs = 'OBSERVER',
    # Suite file in the autoplay folder. ContinuousAgesTransition.json continues through age transitions.
    [string]$Suite = 'ContinuousAgesAutoplay.json',
    # Test parameters to set in the suite's first test, as "Key=Value;Key=Value" (for example "MapSeed=11;GameSeed=11").
    [string]$Set = '',
    # A hang: the game runs, but UI.log and RandCalls.csv have not changed for this many minutes. The runner
    # then closes the game it started and exits with code 4 (iteration 20261031-162612: no log change for
    # 26 minutes at Modern turn 2; the runner waited for the full timeout). 0 turns the check off.
    [int]$StallMinutes = 10,
    # A suite file in another folder (full path) instead of -Suite (the save test plays the previous release's suite).
    [string]$SuiteFile = ''
)

$ErrorActionPreference = 'Stop'
$steam = 'C:\Program Files (x86)\Steam\steam.exe'
$appId = 1295660
$worker = if ($env:CIV7_WORKER) { [int]$env:CIV7_WORKER } else { 0 }
$gameDir = if ($env:CIV7_GAME_DIR) { $env:CIV7_GAME_DIR } else { "C:\Program Files (x86)\Steam\steamapps\common\Sid Meier's Civilization VII" }
$bin = Join-Path $gameDir 'Base\Binaries\Win64'
$realLocal = if ($env:CIV7_REAL_LOCALAPPDATA) { $env:CIV7_REAL_LOCALAPPDATA } else { $env:LOCALAPPDATA }
$userData = Join-Path $env:LOCALAPPDATA "Firaxis Games\Sid Meier's Civilization VII"
$logs = Join-Path $userData 'Logs'
$dumpDirs = @((Join-Path $userData 'packagedDumps'), (Join-Path $userData 'dumps'), (Join-Path $env:LOCALAPPDATA 'CrashDumps'))

# Write the suite with the requested turn count.
$template = if ($SuiteFile) { $SuiteFile } else { Join-Path $PSScriptRoot "autoplay\$Suite" }
$suite = Join-Path $env:TEMP (Split-Path -Leaf $template)
# UTF-8 without a byte-order mark: Windows PowerShell's "-Encoding utf8" adds one,
# and the game ignored a suite file that started with it.
$text = (Get-Content -Raw $template) -replace 'Turns=\d+', "Turns=$Turns" -replace 'ObserveAs=\w+', "ObserveAs=$ObserveAs"
foreach ($kv in ($Set -split ';' | Where-Object { $_ -match '=' })) {
    $key, $value = $kv -split '=', 2
    $pattern = "\b$([regex]::Escape($key))=[^,}]*"
    if ($text -match $pattern) { $text = [regex]::new($pattern).Replace($text, "$key=$value", 1) }
    else { $text = [regex]::new('(Test=\w+)').Replace($text, "`$1, $key=$value", 1) }
}
[System.IO.File]::WriteAllText($suite, $text, (New-Object System.Text.UTF8Encoding $false))

# A crash reporter window left by an earlier run (for example an exit crash) keeps Steam from
# starting the game. The crash is already saved in packagedDumps, so close the window.
# (Worker mode starts no game through Steam, and other workers' reporters are not this run's.)
$reporter = Get-Process -Name 'FiraxisCrashReporter' -ErrorAction SilentlyContinue
if ($worker -eq 0 -and $reporter -and -not (Get-Process -Name 'Civ7_Win64_*' -ErrorAction SilentlyContinue)) {
    Write-Host "Closing a crash reporter left by an earlier run (started $($reporter[0].StartTime))."
    $reporter | Stop-Process -Confirm:$false
    Start-Sleep -Seconds 3
}

# UTC times: local time goes back one hour when daylight saving time ends (2026-11-01, 02:00): a run then
# found no log newer than its start and said "COULD NOT RUN" (iteration 20261101-015922, run time -58.9 minutes).
$start = [DateTime]::UtcNow
$deadline = $start.AddMinutes($TimeoutMinutes)
$proc = $null
if ($worker -gt 0) {
    Write-Host "Starting autoplay in worker ${worker}: $Turns turns, suite $suite"
    $proc = Start-Process -FilePath (Join-Path $bin 'Civ7_Win64_DX12_FinalRelease.exe') -WorkingDirectory $bin -PassThru `
        -ArgumentList @('-autojson', "`"$suite`"", '-bypassStartButton')
    @{ pid = $proc.Id; started = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds() } | ConvertTo-Json -Compress |
        Set-Content -Encoding ascii (Join-Path $env:CIV7_WORKER_DIR 'game.pid')
} else {
    Write-Host "Starting autoplay: $Turns turns, suite $suite"
    & $steam -applaunch $appId -autojson $suite -bypassStartButton
    # Wait for the game process to start.
    while (-not $proc -and [DateTime]::UtcNow -lt $start.AddMinutes(3)) {
        Start-Sleep -Seconds 5
        $proc = Get-Process -Name 'Civ7_Win64_*' -ErrorAction SilentlyContinue | Select-Object -First 1
    }
}
if (-not $proc) { Write-Host 'FAIL: the game did not start within 3 minutes.'; exit 2 }
Write-Host "Game process: $($proc.Id)"
# Wait for the game to exit.
$hung = $false
$watched = @((Join-Path $logs 'UI.log'), (Join-Path $logs 'RandCalls.csv'))
while (-not $proc.HasExited -and [DateTime]::UtcNow -lt $deadline) {
    Start-Sleep -Seconds 15; $proc.Refresh()
    if ($StallMinutes -gt 0 -and -not $proc.HasExited) {
        $last = ($watched | Where-Object { Test-Path $_ } | ForEach-Object { (Get-Item $_).LastWriteTimeUtc } | Measure-Object -Maximum).Maximum
        if ($last -and $last -gt $start -and ([DateTime]::UtcNow - $last).TotalMinutes -ge $StallMinutes) {
            Write-Host "HANG: no change in UI.log or RandCalls.csv for $StallMinutes minutes (last at $($last.ToLocalTime())); closing the game."
            $hung = $true
            $proc | Stop-Process -Confirm:$false
            Start-Sleep -Seconds 5
            break
        }
    }
}
$timedOut = -not $hung -and -not $proc.HasExited
$minutes = [math]::Round(([DateTime]::UtcNow - $start).TotalMinutes, 1)

# Worker mode: this game's crash reporter stays after the game exits (also without a crash). Give it up to 30
# seconds to finish a crash package by itself, then close it. Other workers' reporters stay.
if ($worker -gt 0 -and $proc.HasExited) {
    $until = [DateTime]::UtcNow.AddSeconds(30)
    do {
        $mine = @(Get-CimInstance Win32_Process -Filter "Name='FiraxisCrashReporter.exe' and ParentProcessId=$($proc.Id)")
        if ($mine.Count -gt 0) { Start-Sleep -Seconds 3 }
    } while ($mine.Count -gt 0 -and [DateTime]::UtcNow -lt $until)
    foreach ($r in $mine) {
        Stop-Process -Id $r.ProcessId -Force -ErrorAction SilentlyContinue
        Write-Host "Closed the crash reporter of this game (process $($r.ProcessId))."
    }
}

# Report.
$newDumps = @(foreach ($d in $dumpDirs) {
    if (Test-Path $d) { Get-ChildItem $d -Recurse -File | Where-Object { $_.LastWriteTimeUtc -gt $start -and $_.Name -match 'Civ7|submission' } }
})
# Worker mode: Windows Error Reporting writes to the real user's CrashDumps folder, for every game: only this
# game's dumps (its process id is in the name) belong to this run.
$realDumps = Join-Path $realLocal 'CrashDumps'
if ($worker -gt 0 -and (Test-Path $realDumps)) {
    $newDumps += @(Get-ChildItem $realDumps -File | Where-Object { $_.LastWriteTimeUtc -gt $start -and $_.Name -like "Civ7*.$($proc.Id).dmp" })
}
$results = Get-ChildItem $logs -File | Where-Object { $_.LastWriteTimeUtc -gt $start } |
    Select-String -Pattern '\[PASS\]|\[FAIL\]|Autoplay Turn Limit Hit' -SimpleMatch:$false
Write-Host "Run time: $minutes minutes. Timed out: $timedOut"
if ($newDumps) { Write-Host 'CRASH: new dump files:'; $newDumps | ForEach-Object { Write-Host "  $($_.FullName)" } }
if ($results) { Write-Host 'Automation results:'; $results | ForEach-Object { Write-Host "  $($_.Filename): $($_.Line)" } }
else { Write-Host 'No [PASS]/[FAIL] lines found in the logs written during this run.' }
if ($newDumps) { exit 1 } elseif ($hung) { exit 4 } elseif ($timedOut) { exit 3 } else { exit 0 }
