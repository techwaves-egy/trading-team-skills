@echo off
title Techwaves EGY — Stop All Consoles
echo ===============================================================================
echo        TECHWAVES EGY — AI AUTONOMOUS TRADING FIRM (v3.7.0)
echo               Stopping All Active Console Processes
echo ===============================================================================

powershell -Command "Get-CimInstance Win32_Process -Filter \"Name LIKE 'python%'\" | Where-Object { $_.CommandLine -match 'telegram_listener|auto_scanner|trade_monitor|daily_summary' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force; Write-Host 'Stopped PID' $_.ProcessId }"

echo.
echo All trading daemons have been stopped.
pause
