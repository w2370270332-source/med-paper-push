@echo off
schtasks /create /tn "PaperWeeklyPush" /tr "g:\vs\med-paper-push\run_weekly.bat" /sc weekly /d MON /st 09:00 /f
echo Task registered: %ERRORLEVEL%
