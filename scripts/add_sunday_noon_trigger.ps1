# add_sunday_noon_trigger.ps1
#
# One-time setup: adds a second trigger to the existing FantasyInSeasonPull
# task -- Sundays at 12:00pm, alongside the existing daily 6:15am trigger --
# so Sunday's midday ranking adjustments (inactives, weather, late news)
# get picked up same-day instead of waiting until Monday 6:15am. Run this
# once, yourself, in an elevated PowerShell prompt (Task Scheduler changes
# need admin rights the same way the original task did).

$TaskName = "FantasyInSeasonPull"
$existingTask = Get-ScheduledTask -TaskName $TaskName -ErrorAction Stop

$existingTriggers = $existingTask.Triggers

# Check if a Sunday noon trigger already exists to prevent duplicate triggers.
# MSFT_TaskWeeklyTrigger.DaysOfWeek is a UInt32 bitmask (Sunday=1, Monday=2,
# Tuesday=4, ...), not a string -- compare with -band, not -eq/-contains.
$SUNDAY_BIT = 1
$sundayNoonExists = $false
foreach ($trigger in $existingTask.Triggers) {
    if ($trigger.CimClassName -eq "MSFT_TaskWeeklyTrigger") {
        $triggerTime = $trigger.StartBoundary
        if ($triggerTime -like "*T12:00:*") {
            if (($trigger.DaysOfWeek -band $SUNDAY_BIT) -eq $SUNDAY_BIT) {
                $sundayNoonExists = $true
                break
            }
        }
    }
}

if ($sundayNoonExists) {
    Write-Output "A Sunday 12:00pm trigger already exists for $TaskName. Exiting without modification."
    exit
}

$sundayNoonTrigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Sunday -At "12:00pm"

# WakeToRun lives on the TASK's Settings, not on an individual trigger --
# there is no such property on a trigger object (setting it throws). The
# task's existing Settings.WakeToRun is already $true, so it automatically
# covers this new trigger too; nothing to do here.

$newTriggers = @($existingTriggers) + @($sundayNoonTrigger)

# This task's Principal has LogonType=Password (a stored Windows credential,
# not "run only when logged on"/S4U) -- Set-ScheduledTask on a Password-type
# task fails with "the user name or password is incorrect" unless you
# re-supply the password, even though the credential itself isn't changing.
# Prompt for it here rather than ever hardcoding it.
$cred = Get-Credential -UserName $existingTask.Principal.UserId -Message "Re-enter your Windows password to update $TaskName's triggers (required because this task stores a password credential -- see LogonType=Password)"
Set-ScheduledTask -TaskName $TaskName -Trigger $newTriggers -User $cred.UserName -Password $cred.GetNetworkCredential().Password

Write-Output "Done. $TaskName now has $($newTriggers.Count) trigger(s):"
(Get-ScheduledTask -TaskName $TaskName).Triggers | ForEach-Object {
    Write-Output "  $($_.CimClass.CimClassName): $($_.StartBoundary) (DaysOfWeek: $($_.DaysOfWeek))"
}
