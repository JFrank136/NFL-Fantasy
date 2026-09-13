# scheduled_pull.ps1
#
# Runs the weekly rankings pull + Vampire weekly_projection refresh with NO
# Claude Code involvement -- this is the OS-level backstop for when the app
# isn't open. Windows Task Scheduler calls this directly. Everything is
# logged to data/scheduled_run_logs/ so a later check (by the in-app
# scheduled task, or by hand) can tell success from failure without having
# watched it run.

$ErrorActionPreference = "Continue"

$PythonExe = "C:\Program Files\Python311\python.exe"
$InSeasonDir = Split-Path -Parent $PSScriptRoot
$VampireDir = Join-Path (Split-Path -Parent $InSeasonDir) "Vampire\matchup-tool"
$LogDir = Join-Path $InSeasonDir "data\scheduled_run_logs"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$LogFile = Join-Path $LogDir ("{0}.log" -f (Get-Date -Format "yyyyMMdd_HHmmss"))
$CredPath = Join-Path $env:LOCALAPPDATA "FantasyInSeasonPull\gmail_cred.xml"

function Log($msg) {
    $line = "[{0}] {1}" -f (Get-Date -Format "o"), $msg
    Write-Output $line
    Add-Content -Path $LogFile -Value $line
}

function Send-FailureEmail($subject, $body) {
    if (-not (Test-Path $CredPath)) {
        Log "No stored Gmail credential at $CredPath -- skipping failure email. See in-season/README.md to set one up."
        return
    }
    try {
        $cred = Import-Clixml -Path $CredPath
        Send-MailMessage -SmtpServer "smtp.gmail.com" -Port 587 -UseSsl -Credential $cred `
            -From $cred.UserName -To $cred.UserName -Subject $subject -Body $body
        Log "Failure email sent to $($cred.UserName)."
    } catch {
        Log "Failed to send failure email: $_"
    }
}

$NotifyStatePath = Join-Path $InSeasonDir "data\notify_state.json"

function Get-NotifyState {
    # Windows PowerShell 5.1's ConvertFrom-Json has no -AsHashtable (that's
    # PS 6+/Core only) -- convert the returned PSCustomObject by hand.
    if (Test-Path $NotifyStatePath) {
        try {
            $obj = Get-Content $NotifyStatePath -Raw | ConvertFrom-Json
            $hash = @{}
            foreach ($prop in $obj.PSObject.Properties) {
                $hash[$prop.Name] = $prop.Value
            }
            return $hash
        } catch {
            Log "WARNING: $NotifyStatePath exists but failed to parse ($_) -- treating as empty state (everything will look like first publish this run)."
            return @{}
        }
    }
    return @{}
}

function Save-NotifyState($state) {
    $state | ConvertTo-Json | Set-Content -Path $NotifyStatePath -Encoding utf8
}

function Send-SuccessEmail($subject, $body) {
    if (-not (Test-Path $CredPath)) {
        Log "No stored Gmail credential at $CredPath -- skipping success email."
        return
    }
    try {
        $cred = Import-Clixml -Path $CredPath
        Send-MailMessage -SmtpServer "smtp.gmail.com" -Port 587 -UseSsl -Credential $cred `
            -From $cred.UserName -To $cred.UserName -Subject $subject -Body $body
        Log "Success email sent to $($cred.UserName)."
    } catch {
        Log "Failed to send success email: $_"
    }
}

function Send-SuccessEmailIfWarranted($CurrentWeek, $CsvPath) {
    $state = Get-NotifyState
    $today = Get-Date
    $isGameday = $today.DayOfWeek -in @("Thursday", "Sunday", "Monday")

    $rankingsStatusPath = Join-Path $InSeasonDir "data\last_run_status.json"
    $tradeValuesStatusPath = Join-Path $InSeasonDir "data\last_trade_values_status.json"
    $newlyPublished = @()

    if (Test-Path $rankingsStatusPath) {
        $rankingsStatus = Get-Content $rankingsStatusPath -Raw | ConvertFrom-Json
        foreach ($combo in $rankingsStatus.combos.PSObject.Properties) {
            if ($combo.Value -eq "ok") {
                $key = "rankings:$($combo.Name)"
                if (-not $state.ContainsKey($key)) {
                    $newlyPublished += $combo.Name
                    $state[$key] = "sent"
                }
            }
        }
    }
    if (Test-Path $tradeValuesStatusPath) {
        $tvStatus = Get-Content $tradeValuesStatusPath -Raw | ConvertFrom-Json
        foreach ($pos in $tvStatus.positions.PSObject.Properties) {
            if ($pos.Value -eq "ok") {
                $key = "tradevalue:week${CurrentWeek}:$($pos.Name)"
                if (-not $state.ContainsKey($key)) {
                    $newlyPublished += "trade-values/$($pos.Name)"
                    $state[$key] = "sent"
                }
            }
        }
    }

    Save-NotifyState $state

    if (-not $isGameday -and $newlyPublished.Count -eq 0) {
        Log "Success email skipped -- not a gameday and nothing newly published."
        return
    }

    $reason = if ($isGameday -and $newlyPublished.Count -gt 0) {
        "gameday + first publish of: $($newlyPublished -join ', ')"
    } elseif ($isGameday) {
        "gameday"
    } else {
        "first publish of: $($newlyPublished -join ', ')"
    }
    Log "Sending success email ($reason)."
    Send-SuccessEmail "Fantasy pull OK ($(Get-Date -Format 'yyyy-MM-dd')) -- $reason" `
        "Week $CurrentWeek pull succeeded.`n`nReason for this email: $reason`n`nLog: $LogFile"
}

Log "=== Scheduled pull starting ==="
Log "in-season dir: $InSeasonDir"
Log "Vampire dir:   $VampireDir"

# The task can fire late (WakeToRun) right as the machine wakes from sleep,
# before Wi-Fi/DNS is actually back up -- wait for real connectivity instead
# of immediately burning through every combo as a DNS failure.
$networkReady = $false
for ($i = 1; $i -le 12; $i++) {
    if (Test-Connection -ComputerName "8.8.8.8" -Count 1 -Quiet -ErrorAction SilentlyContinue) {
        $networkReady = $true
        break
    }
    Log "No network connectivity yet (attempt $i/12) -- waiting 10s..."
    Start-Sleep -Seconds 10
}
if (-not $networkReady) {
    Log "=== ABORTED: no network connectivity after 2 minutes of waiting ==="
    Send-FailureEmail "Fantasy pull FAILED: no network" "The daily rankings pull aborted because the machine had no network connectivity 2 minutes after the scheduled task started.`n`nLog: $LogFile"
    exit 1
}
Log "Network connectivity confirmed."

Push-Location $InSeasonDir
try {
    Log "Running pull_week.py..."
    & $PythonExe "scripts\pull_week.py" 2>&1 | ForEach-Object { Log $_ }
    $pullExit = $LASTEXITCODE
    Log "pull_week.py exit code: $pullExit"

    Log "Running pull_trade_values.py..."
    & $PythonExe "scripts\pull_trade_values.py" 2>&1 | ForEach-Object { Log $_ }
    $tradeValuesExit = $LASTEXITCODE
    Log "pull_trade_values.py exit code: $tradeValuesExit"

    $currentWeek = (& $PythonExe -c "import sys; sys.path.insert(0, '.'); from src.season_config import current_week; print(current_week())").Trim()
    $lastWeek = (& $PythonExe -c "import sys; sys.path.insert(0, '.'); from src.season_config import LAST_WEEK; print(LAST_WEEK)").Trim()
    Log "Current active week: $currentWeek (season ends at week $lastWeek)"

    $statusPath = "data\last_run_status.json"
    if (Test-Path $statusPath) {
        $status = Get-Content $statusPath -Raw | ConvertFrom-Json
        $csvPath = Join-Path $InSeasonDir "data\processed\rankings_long.csv"

        # Keep two rolling slots pushed to Vampire -- current week and next
        # week -- so a player's projection stays visible right up until that
        # week has actually passed, per Jared.
        $weeksToPush = @(
            @{ Week = [int]$currentWeek; Slot = "current" }
        )
        if ([int]$currentWeek + 1 -le [int]$lastWeek) {
            $weeksToPush += @{ Week = [int]$currentWeek + 1; Slot = "next" }
        } else {
            Log "No next-week preview to push -- season ends at week $lastWeek."
        }

        foreach ($entry in $weeksToPush) {
            $week = $entry.Week
            $slot = $entry.Slot
            $comboKey = "week$week/draftsharks/half-ppr"
            $comboStatus = $status.combos.$comboKey
            Log "Status for ${comboKey} (slot: ${slot}): $comboStatus"

            if ($comboStatus -eq "ok") {
                Push-Location $VampireDir
                try {
                    Log "Refreshing Vampire weekly_projection ($slot) for week $week..."
                    & node "--env-file=.env" "scripts\refresh-weekly-projection.js" $csvPath $week "half-ppr" $slot 2>&1 | ForEach-Object { Log $_ }
                    Log "refresh-weekly-projection.js ($slot) exit code: $LASTEXITCODE"
                } finally {
                    Pop-Location
                }
            } else {
                Log "Skipping Vampire $slot-slot refresh -- week $week draftsharks/half-ppr did not succeed this run."
            }
        }
    } else {
        Log "WARNING: $statusPath not found after pull_week.py ran -- something is badly wrong (check exit code above)."
    }

    $anyFailure = ($pullExit -ne 0) -or ($tradeValuesExit -ne 0)
    if ($anyFailure) {
        Log "=== FINISHED WITH FAILURES -- see above / status JSON files ==="
        $failedParts = @()
        if ($pullExit -ne 0) { $failedParts += "pull_week.py exited $pullExit" }
        if ($tradeValuesExit -ne 0) { $failedParts += "pull_trade_values.py exited $tradeValuesExit" }
        Send-FailureEmail "Fantasy pull FAILED ($(Get-Date -Format 'yyyy-MM-dd'))" "$($failedParts -join '; ').`n`nFull log: $LogFile`n`nTail of log:`n$(Get-Content $LogFile -Tail 40 | Out-String)"
    } else {
        Log "=== FINISHED OK ==="
        Send-SuccessEmailIfWarranted -CurrentWeek $currentWeek -CsvPath $csvPath
    }
} finally {
    Pop-Location
}

# Propagate real success/failure to the process exit code -- otherwise
# Get-ScheduledTaskInfo's LastTaskResult always shows 0 (this script itself
# ran fine) regardless of whether the pull actually succeeded, which defeats
# using Task Scheduler's own status as a check.
if ($pullExit -ne 0) { exit $pullExit }
exit $tradeValuesExit
