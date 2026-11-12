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

Hang close: the base game can stop in its turn-start autosave (docs/known-limits.md). The mod's in-game watchdog
(checks/ca-automation.js) then writes a [CA-CHECK][HANG] "detected" record in UI.log after 20 s. The runner reads the
new part of UI.log at each check (every 5 s in worker mode, else 15 s); with such a record (written after the runner
started) it closes the game at once, prints "HANG: the in-game watchdog ..." and exits with code 4, as after a stall
(the report says HANG FAIL; regression.py runs the item once more). The stall check (-StallMinutes) stays for hangs
without the record. A continue from the last autosave was tried and dropped (2026-11-01): after a load the base game
picks volcano and river plots from other candidate lists (RandCalls.csv), so the rest of the game is not the game
of the seed, and the checks write extra "first check after a load" records.

Mod off: after a game update the game turns every mod off once (gamepool.py, MOD_RESET_OPTION). The suite's script
of the mod then cannot load, and the game waits at the main menu. With the line "Cannot determine local path -
fs://game/continuous-ages/..." in the new part of UI.log, and no [CA-CHECK] record of this run so far, the runner
closes the game at once, prints "MOD NOT LOADED: ..." and exits with code 5 (not a hang: iterate.py reports MOD NOT
LOADED, and regression.py does not run the item again). Runs 20261110-113403-w1 and 113404-w2 waited 5 minutes for the
stall check and said "HANG FAIL".
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
# Worker mode: a hang is closed after 5 minutes without a log change, not 10 (a late-game turn takes about 10 s;
# the rare base-game hang in the turn-start autosave, docs/known-limits.md, then costs half the time).
if ($worker -gt 0 -and -not $PSBoundParameters.ContainsKey('StallMinutes')) { $StallMinutes = 5 }
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
    # Hold the game at Normal priority with a Windows job object (priority-class limit): the game sets its own class
    # again and again (AboveNormal; BelowNormal after its window loses the focus), and with several games a
    # BelowNormal game played about half as fast at 100% CPU. The limit needs the "increase scheduling priority"
    # privilege; without it, the wait loop below sets the class every 5 s instead.
    try {
        Add-Type -TypeDefinition @'
using System; using System.Runtime.InteropServices;
public static class CivJob {
    [StructLayout(LayoutKind.Sequential)] struct BASIC { public long PerProcessUserTimeLimit; public long PerJobUserTimeLimit;
        public uint LimitFlags; public UIntPtr MinimumWorkingSetSize; public UIntPtr MaximumWorkingSetSize;
        public uint ActiveProcessLimit; public UIntPtr Affinity; public uint PriorityClass; public uint SchedulingClass; }
    [StructLayout(LayoutKind.Sequential)] struct LUID { public uint Low; public int High; }
    [StructLayout(LayoutKind.Sequential)] struct TOKEN_PRIVILEGES { public uint Count; public LUID Luid; public uint Attributes; }
    [DllImport("kernel32.dll", CharSet = CharSet.Unicode)] static extern IntPtr CreateJobObject(IntPtr a, string name);
    [DllImport("kernel32.dll")] static extern bool SetInformationJobObject(IntPtr job, int cls, ref BASIC info, int len);
    [DllImport("kernel32.dll")] static extern bool AssignProcessToJobObject(IntPtr job, IntPtr process);
    [DllImport("kernel32.dll")] static extern IntPtr GetCurrentProcess();
    [DllImport("advapi32.dll")] static extern bool OpenProcessToken(IntPtr process, uint access, out IntPtr token);
    [DllImport("advapi32.dll", CharSet = CharSet.Unicode)] static extern bool LookupPrivilegeValue(string sys, string name, out LUID luid);
    [DllImport("advapi32.dll")] static extern bool AdjustTokenPrivileges(IntPtr token, bool all, ref TOKEN_PRIVILEGES p, int len, IntPtr prev, IntPtr ret);
    public static string Hold(IntPtr process, uint priorityClass) {
        IntPtr token; LUID luid;
        if (OpenProcessToken(GetCurrentProcess(), 0x28, out token) && LookupPrivilegeValue(null, "SeIncreaseBasePriorityPrivilege", out luid)) {
            TOKEN_PRIVILEGES tp = new TOKEN_PRIVILEGES(); tp.Count = 1; tp.Luid = luid; tp.Attributes = 2;  // SE_PRIVILEGE_ENABLED
            AdjustTokenPrivileges(token, false, ref tp, 0, IntPtr.Zero, IntPtr.Zero);
        }
        IntPtr job = CreateJobObject(IntPtr.Zero, null);
        if (job == IntPtr.Zero) return "CreateJobObject error " + Marshal.GetLastWin32Error();
        BASIC b = new BASIC(); b.LimitFlags = 0x20; b.PriorityClass = priorityClass;  // JOB_OBJECT_LIMIT_PRIORITY_CLASS
        if (!SetInformationJobObject(job, 2, ref b, Marshal.SizeOf(typeof(BASIC)))) return "SetInformationJobObject error " + Marshal.GetLastWin32Error();
        if (!AssignProcessToJobObject(job, process)) return "AssignProcessToJobObject error " + Marshal.GetLastWin32Error();
        return "";  // the job handle stays open while this runner waits; the game keeps the job after that too
    }
}
'@
        $jobError = [CivJob]::Hold($proc.Handle, 0x20)  # NORMAL_PRIORITY_CLASS
        if ($jobError) { Write-Host "Priority job not set ($jobError): the wait loop holds Normal priority every 5 s." }
        else { Write-Host "Game priority held at Normal (job object)." }
    } catch { Write-Host "Priority job not set ($($_.Exception.Message)): the wait loop holds Normal priority every 5 s." }
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
# The in-game watchdog's record: only the new, complete lines of UI.log are read at each check (the game starts the
# file again when it starts: a shorter file is read from the start). Records stamped before the runner's start are
# from an earlier run.
$uiLog = Join-Path $logs 'UI.log'
$uiPos = [long]0
$startLocal = (Get-Date).AddSeconds(-1)
$modLoaded = $false
$modOff = $null
function Find-HangRecord {
    if (-not (Test-Path $uiLog)) { return $null }
    try { $fs = [System.IO.File]::Open($uiLog, 'Open', 'Read', 'ReadWrite, Delete') } catch { return $null }
    try {
        if ($fs.Length -lt $script:uiPos) { $script:uiPos = 0 }
        $count = [int][math]::Min($fs.Length - $script:uiPos, 64MB)
        if ($count -le 0) { return $null }
        $buf = New-Object byte[] $count
        [void]$fs.Seek($script:uiPos, 'Begin')
        $n = $fs.Read($buf, 0, $count)
        $end = [Array]::LastIndexOf($buf, [byte]10, $n - 1)
        if ($end -lt 0) { return $null }
        $script:uiPos += $end + 1
        $text = [System.Text.Encoding]::UTF8.GetString($buf, 0, $end + 1)
    } finally { $fs.Dispose() }
    # The game turned the mod off: the suite's script of the mod cannot load (gamepool.mod_off_line, the same test).
    # Only while no [CA-CHECK] record of this run has come (a mod that loaded writes them from the start).
    $ca = [regex]::Matches($text, '(?m)^\[(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d)\]\s+\[CA-CHECK\]')
    if ($ca.Count -gt 0 -and [datetime]::ParseExact($ca[$ca.Count - 1].Groups[1].Value, 'yyyy-MM-dd HH:mm:ss', $null) -ge $startLocal) {
        $script:modLoaded = $true
    }
    if (-not $script:modLoaded) {
        foreach ($m in [regex]::Matches($text, '(?m)^\[(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d)\]\s+(Cannot determine local path - fs://game/continuous-ages/\S*)')) {
            $at = [datetime]::ParseExact($m.Groups[1].Value, 'yyyy-MM-dd HH:mm:ss', $null)
            if ($at -ge $startLocal) { $script:modOff = "$($m.Groups[1].Value) $($m.Groups[2].Value)"; break }
        }
    }
    foreach ($m in [regex]::Matches($text, '(?m)^\[(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d)\]\s+\[CA-CHECK\]\[HANG\] (\{[^\r\n]*"event":"detected"[^\r\n]*\})')) {
        $at = [datetime]::ParseExact($m.Groups[1].Value, 'yyyy-MM-dd HH:mm:ss', $null)
        if ($at -ge $startLocal) { return "$($m.Groups[1].Value) $($m.Groups[2].Value)" }
    }
    return $null
}
while (-not $proc.HasExited -and [DateTime]::UtcNow -lt $deadline) {
    # Worker mode: check every 5 s, and hold the game at Normal priority. The game sets its own class (AboveNormal, and
    # BelowNormal after its window loses the focus); with several games, a BelowNormal game played about half as fast
    # at 100% CPU, and the rare save hang came from such games (gamepool.WORKER_PRIORITY).
    Start-Sleep -Seconds $(if ($worker -gt 0) { 5 } else { 15 }); $proc.Refresh()
    if ($worker -gt 0 -and -not $proc.HasExited) {
        try { if ($proc.PriorityClass -ne 'Normal') { $proc.PriorityClass = 'Normal' } } catch { }
    }
    if (-not $proc.HasExited) {
        $record = Find-HangRecord
        if ($modOff) {
            Write-Host "MOD NOT LOADED: the game turned the mod off (after a game update?) (UI.log $modOff); closing the game."
            $proc | Stop-Process -Force -Confirm:$false
            Start-Sleep -Seconds 5
            break
        }
        if ($record) {
            Write-Host "HANG: the in-game watchdog found the turn-start autosave stuck (UI.log $record); closing the game."
            $hung = $true
            $proc | Stop-Process -Force -Confirm:$false
            Start-Sleep -Seconds 5
            break
        }
    }
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
$timedOut = -not $hung -and -not $modOff -and -not $proc.HasExited
$minutes = [math]::Round(([DateTime]::UtcNow - $start).TotalMinutes, 1)
# Worker mode: a game past the time limit is closed, so that the worker is free for the next item (without a
# worker the game stays, as before).
if ($worker -gt 0 -and $timedOut) {
    Write-Host "TIMEOUT: the game runs after $TimeoutMinutes minutes; closing the game of worker $worker."
    $proc | Stop-Process -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 5
    $proc.Refresh()
}

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
if ($newDumps) { exit 1 } elseif ($modOff) { exit 5 } elseif ($hung) { exit 4 } elseif ($timedOut) { exit 3 } else { exit 0 }
