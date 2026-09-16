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

function Send-FailureEmail($subject, $body, [switch]$Html) {
    if (-not (Test-Path $CredPath)) {
        Log "No stored Gmail credential at $CredPath -- skipping failure email. See in-season/README.md to set one up."
        return
    }
    try {
        $cred = Import-Clixml -Path $CredPath
        Send-MailMessage -SmtpServer "smtp.gmail.com" -Port 587 -UseSsl -Credential $cred `
            -From $cred.UserName -To $cred.UserName -Subject $subject -Body $body -BodyAsHtml:$Html
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

function Send-SuccessEmail($subject, $body, [switch]$Html) {
    if (-not (Test-Path $CredPath)) {
        Log "No stored Gmail credential at $CredPath -- skipping success email."
        return
    }
    try {
        $cred = Import-Clixml -Path $CredPath
        Send-MailMessage -SmtpServer "smtp.gmail.com" -Port 587 -UseSsl -Credential $cred `
            -From $cred.UserName -To $cred.UserName -Subject $subject -Body $body -BodyAsHtml:$Html
        Log "Success email sent to $($cred.UserName)."
    } catch {
        Log "Failed to send success email: $_"
    }
}

# A weekly-rankings combo that failed validation with "Pull returned zero
# rows" (src/validate.py) means the source hasn't posted that week's
# rankings yet (Boone/Smyth typically post Thursday) -- that's expected and
# transient, not a scraper break, so it must read differently from a real
# failure (network error, HTML/API shape change, etc).
function Get-ComboState($value) {
    if (-not $value) { return "missing" }
    if ($value -eq "ok") { return "ok" }
    if ($value -eq "not_yet_published") { return "pending" }
    if ($value -match "Pull returned zero rows") { return "pending" }
    return "failed"
}

# Gathers the same underlying status data once, as a plain structure, so the
# plain-text renderer (Build-StatusSummary, used in logs/failure tails) and
# the HTML renderer (Build-StatusSummaryHtml, used in the actual email body)
# can't drift out of sync with each other.
function Get-StatusData($CurrentWeek) {
    $rankingsStatusPath = Join-Path $InSeasonDir "data\last_run_status.json"
    $tradeValuesStatusPath = Join-Path $InSeasonDir "data\last_trade_values_status.json"

    $rankingsStatus = $null
    $rankingsDate = $null
    if (Test-Path $rankingsStatusPath) {
        $rankingsStatus = Get-Content $rankingsStatusPath -Raw | ConvertFrom-Json
        $rankingsDate = ([DateTimeOffset]$rankingsStatus.run_at).ToString("yyyy-MM-dd")
    }

    $tvStatus = $null
    $tvDate = $null
    if (Test-Path $tradeValuesStatusPath) {
        $tvStatus = Get-Content $tradeValuesStatusPath -Raw | ConvertFrom-Json
        $tvDate = ([DateTimeOffset]$tvStatus.run_at).ToString("yyyy-MM-dd")
    }

    # Boone ROS (trade values) isn't split by scoring format -- it's the same
    # pull surfaced under both sections below, per Jared's requested layout.
    # A real failure on any position outranks "not yet published" on others,
    # since that's the one worth his attention.
    $boneRosState = "missing"
    if ($tvStatus) {
        $posStates = $tvStatus.positions.PSObject.Properties | ForEach-Object { Get-ComboState $_.Value }
        if ($posStates -contains "failed") { $boneRosState = "failed" }
        elseif ($posStates -contains "pending") { $boneRosState = "pending" }
        elseif ($posStates.Count -gt 0 -and ($posStates | Where-Object { $_ -ne "ok" }).Count -eq 0) { $boneRosState = "ok" }
    }

    $sections = @()
    foreach ($fmt in @(
        @{ Key = "half-ppr"; Label = "Half PPR" },
        @{ Key = "ppr"; Label = "Full PPR" }
    )) {
        $key = $fmt.Key
        $items = @()

        # Discover weekly-rankings sources dynamically from the combos data
        # (rather than a hardcoded list) so a new source added to
        # pull_week.py's ALL_SOURCES shows up here automatically.
        $sourceNames = @()
        if ($rankingsStatus) {
            foreach ($combo in $rankingsStatus.combos.PSObject.Properties) {
                if ($combo.Name -match "^week\d+/([a-zA-Z0-9_-]+)/$([regex]::Escape($key))$") {
                    $sourceNames += $Matches[1]
                }
            }
        }
        $sourceNames = $sourceNames | Sort-Object -Unique

        foreach ($src in $sourceNames) {
            $srcCombo = "week$CurrentWeek/$src/$key"
            $srcValue = if ($rankingsStatus) { $rankingsStatus.combos.$srcCombo } else { $null }
            $srcState = Get-ComboState $srcValue

            $capturedWeeks = @()
            foreach ($combo in $rankingsStatus.combos.PSObject.Properties) {
                if ($combo.Name -match "^week(\d+)/$([regex]::Escape($src))/$([regex]::Escape($key))$" -and $combo.Value -eq "ok") {
                    $capturedWeeks += [int]$Matches[1]
                }
            }
            $capturedWeeks = $capturedWeeks | Sort-Object

            $label = (Get-Culture).TextInfo.ToTitleCase($src)
            $items += @{
                Label = "$label Weekly Rankings"
                State = $srcState
                Date = if ($srcState -eq "ok") { $rankingsDate } else { $null }
                Weeks = $capturedWeeks
            }
        }

        $items += @{
            Label = "Boone ROS"
            State = $boneRosState
            Date = if ($boneRosState -eq "ok") { $tvDate } else { $null }
            Weeks = @()
        }

        $sections += @{ Label = $fmt.Label; Items = $items }
    }
    return $sections
}

function Build-StatusSummary($CurrentWeek) {
    $lines = @()
    foreach ($section in Get-StatusData $CurrentWeek) {
        $lines += "$($section.Label):"
        foreach ($item in $section.Items) {
            $weeksNote = if ($item.Weeks.Count -gt 0) { " -- weeks captured: $($item.Weeks -join ', ')" } else { "" }
            $dateStr = if ($item.Date) { " ($($item.Date))" } else { "" }
            $line = switch ($item.State) {
                "ok"      { "  [x] $($item.Label)$dateStr$weeksNote" }
                "pending" { "  [ ] $($item.Label) -- not yet published$weeksNote" }
                "failed"  { "  [ ] $($item.Label) -- FAILED (see log)$weeksNote" }
                default   { "  [ ] $($item.Label) -- no data$weeksNote" }
            }
            $lines += $line
        }
        $lines += ""
    }
    return ($lines -join "`n").TrimEnd()
}

function Build-StatusSummaryHtml($CurrentWeek) {
    $stateStyle = @{
        ok      = @{ Icon = "&#9989;"; Color = "#2f9e44"; Text = "Refreshed" }
        pending = @{ Icon = "&#8987;";  Color = "#e8890c"; Text = "Not yet published" }
        failed  = @{ Icon = "&#10060;"; Color = "#e03131"; Text = "FAILED" }
        missing = @{ Icon = "&#9679;";  Color = "#adb5bd"; Text = "No data" }
    }

    $html = ""
    foreach ($section in Get-StatusData $CurrentWeek) {
        $html += "<h3 style=`"margin:20px 0 6px;font-size:14px;color:#212529;border-bottom:2px solid #1c7ed6;padding-bottom:4px;`">$($section.Label)</h3>"
        $html += "<table style=`"width:100%;border-collapse:collapse;font-size:13px;`">"
        foreach ($item in $section.Items) {
            $style = $stateStyle[$item.State]
            $detail = if ($item.State -eq "ok" -and $item.Date) { $item.Date } else { $style.Text }
            if ($item.Weeks.Count -gt 0) { $detail += " &middot; weeks $($item.Weeks -join ', ')" }
            $html += "<tr style=`"border-bottom:1px solid #f1f3f5;`">"
            $html += "<td style=`"padding:6px 8px 6px 0;width:20px;`">$($style.Icon)</td>"
            $html += "<td style=`"padding:6px 0;color:#212529;`">$($item.Label)</td>"
            $html += "<td style=`"padding:6px 0 6px 12px;color:$($style.Color);text-align:right;white-space:nowrap;`">$detail</td>"
            $html += "</tr>"
        }
        $html += "</table>"
    }
    return $html
}

function New-EmailHtml($title, $subtitle, $accentColor, $bodyHtml, $footerText) {
    return @"
<div style="font-family:-apple-system,'Segoe UI',Arial,sans-serif;max-width:520px;margin:0 auto;color:#212529;">
  <div style="border-top:4px solid $accentColor;padding-top:14px;">
    <h2 style="margin:0 0 2px;font-size:18px;">$title</h2>
    <p style="margin:0;color:#868e96;font-size:12px;">$subtitle</p>
  </div>
  $bodyHtml
  <p style="margin-top:22px;padding-top:10px;border-top:1px solid #f1f3f5;color:#adb5bd;font-size:11px;">$footerText</p>
</div>
"@
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
    $summaryHtml = Build-StatusSummaryHtml -CurrentWeek $CurrentWeek
    $htmlBody = New-EmailHtml `
        "&#127944; Fantasy Pull -- Week $CurrentWeek" `
        "$(Get-Date -Format 'dddd, MMMM d') &middot; $reason" `
        "#2f9e44" `
        $summaryHtml `
        "Log: $LogFile"
    Send-SuccessEmail -Html "Fantasy pull OK ($(Get-Date -Format 'yyyy-MM-dd')) -- $reason" $htmlBody
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

    Log "Running push_to_supabase.py..."
    & $PythonExe "scripts\push_to_supabase.py" 2>&1 | ForEach-Object { Log $_ }
    Log "push_to_supabase.py exit code: $LASTEXITCODE"

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
        $summaryHtml = Build-StatusSummaryHtml -CurrentWeek $currentWeek
        $logTail = (Get-Content $LogFile -Tail 40 | Out-String) -replace '&', '&amp;' -replace '<', '&lt;' -replace '>', '&gt;'
        $bodyHtml = @"
        <p style="font-size:13px;color:#e03131;font-weight:600;">$($failedParts -join '; ')</p>
        $summaryHtml
        <p style="margin:16px 0 4px;font-size:12px;color:#868e96;">Tail of log ($LogFile):</p>
        <pre style="background:#f8f9fa;border:1px solid #f1f3f5;border-radius:4px;padding:10px;font-size:11px;overflow-x:auto;white-space:pre-wrap;">$logTail</pre>
"@
        $htmlBody = New-EmailHtml "&#10060; Fantasy Pull FAILED" (Get-Date -Format 'dddd, MMMM d') "#e03131" $bodyHtml "Full log: $LogFile"
        Send-FailureEmail -Html "Fantasy pull FAILED ($(Get-Date -Format 'yyyy-MM-dd'))" $htmlBody
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
