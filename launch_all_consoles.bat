@echo off
title Techwaves EGY — Autonomous Trading Firm Launcher
echo ===============================================================================
echo        TECHWAVES EGY — AI AUTONOMOUS TRADING FIRM (v3.7.0)
echo                  Launching All Daemons in Dedicated Consoles
echo ===============================================================================

cd /d "%~dp0"

echo [1/4] Launching Two-Way Telegram Listener Console...
start "Telegram Listener [Techwaves EGY]" cmd.exe /k "title Telegram Listener && python scripts/telegram_listener.py"

echo [2/4] Launching Auto-Scanner Engine Console (15-min interval)...
start "Auto Scanner [Techwaves EGY]" cmd.exe /k "title Auto Scanner && python scripts/auto_scanner.py 15"

echo [3/4] Launching Real-Time MT5 Trade Closure Monitor Console...
start "Trade Monitor [Techwaves EGY]" cmd.exe /k "title Trade Monitor && python scripts/trade_monitor.py"

echo [4/4] Launching Daily and Weekend Summary Daemon Console...
start "Daily Summary [Techwaves EGY]" cmd.exe /k "title Daily Summary && python scripts/daily_summary.py --daemon"

echo.
echo ===============================================================================
echo   All 4 trading firm consoles have been launched in separate windows!
echo   You can monitor live streaming output across each dedicated window.
echo ===============================================================================
