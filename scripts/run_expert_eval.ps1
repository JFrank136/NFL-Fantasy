# Weekly expert-accuracy evaluation (shadow weights). Safe to run any time and as often as
# you like: it only evaluates weeks whose games are all final, upserts on natural keys, and
# never deletes. Running it again after Tuesday's nflverse stat corrections refreshes that
# week in place.
#
# Standalone on purpose -- it is NOT part of scheduled_pull.ps1, so it cannot affect the
# weekly data pull. Register it (e.g. Wednesday 9:00 AM) or call it from the pull script
# once you are happy with it.
$ErrorActionPreference = "Continue"
$PythonExe = "C:\Program Files\Python311\python.exe"
$Root = Split-Path -Parent $PSScriptRoot
$LogDir = Join-Path $env:USERPROFILE "FantasyData\in-season\expert_eval\logs"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$Log = Join-Path $LogDir ("run_{0}.log" -f (Get-Date -Format "yyyyMMdd_HHmmss"))

Set-Location $Root
"[{0}] expert eval start" -f (Get-Date -Format s) | Tee-Object -FilePath $Log -Append
$ok = $false
for ($i = 1; $i -le 3 -and -not $ok; $i++) {
    # network may not be up right after wake-from-sleep (same race the pull script guards against)
    try { $null = Invoke-WebRequest -Uri "https://nflreadr.nflverse.com" -UseBasicParsing -TimeoutSec 15; $ok = $true }
    catch { "network not ready (attempt $i), waiting" | Tee-Object -FilePath $Log -Append; Start-Sleep -Seconds 20 }
}
if (-not $ok) { "giving up: no network" | Tee-Object -FilePath $Log -Append; exit 2 }
& $PythonExe "scripts\run_expert_eval.py" 2>&1 | Tee-Object -FilePath $Log -Append
$code = $LASTEXITCODE
"[{0}] expert eval exit code {1}" -f (Get-Date -Format s), $code | Tee-Object -FilePath $Log -Append
exit $code
