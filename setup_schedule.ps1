$TaskName = "文献周报推送"

# Remove old task if exists
try {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
} catch {}

$Action = New-ScheduledTaskAction -Execute "g:\vs\med-paper-push\run_weekly.bat" -WorkingDirectory "g:\vs\med-paper-push"
$Trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday -At "09:00"
$Principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive -RunLevel Limited
$Settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew

Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Principal $Principal -Settings $Settings -Description "每周一早9点推送预防医学与营养学文献到飞书、邮箱和Obsidian"

Write-Host "[OK] Scheduled task '$TaskName' registered successfully"
