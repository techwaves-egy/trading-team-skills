# Changelog — AI Autonomous Trading Firm Skill

All notable changes, architectural upgrades, and version tags of the AI Autonomous Trading Firm are recorded in this file.

---

## [v3.8.10] — 2026-09-25

### 🚀 Full User-Configured Batch Concurrency (1x–5x) Across All Markets
* **Configurable Concurrency Restoration (`scripts/auto_scanner.py`, `scripts/mt5_connector.py`)**:
  * Restored user-selected multi-trade batch scaling (`1x` to `5x`) across all universe profiles, including Gold (`XAUUSD`).
  * Harmonized scanner iteration and connector anti-stacking filters to respect `concurrent_batch_size` from `session_state.json`.

---

## [v3.8.9] — 2026-09-25

### ⏱️ Trade Holding Duration Telemetry
* **Trade Duration Telemetry (`scripts/trade_monitor.py`)**:
  * Added trade holding duration calculation to all MT5 trade closure alerts and journal logs.
  * Correlates exit deals (`entry == 1`) with entry deals (`entry == 0`) by position ticket to report exact elapsed time in `⏱️ Xh Ym (X hours, Y mins)`.

---

## [v3.8.8] — 2026-09-25

### 🔄 Self-Healing MT5 Deal Streamer
* **Auto-Reconnecting MT5 IPC Pipe (`scripts/trade_monitor.py`)**:
  * Implemented `ensure_mt5_connected()` inside the deal streaming loop to detect silent MT5 IPC disconnects.
  * Recovers connection automatically within 3 seconds, eliminating dropped closure alerts.
  * Retroactively audited and broadcasted missing `$49.98` TP notifications for tickets `#10415140330` and `#10415140337`.

---

## [v3.8.7] — 2026-09-25

### 🕯️ Closed-Candle Reversal Confirmation
* **False Breakout Filter (`scripts/auto_scanner.py`)**:
  * Replaced inspection of live forming bars (`bars[-1]`) with confirmed closed bars (`bars[-2]`).
  * Implemented `check_bollinger_confirmation()` requiring confirmed candlestick rejection after Bollinger Band breach before firing market orders.

---

## [v3.8.6] — 2026-09-25

### ⚡ Batch Concurrency Gate Alignment
* **Anti-Stacking Gate Update (`scripts/mt5_connector.py`)**:
  * Upgraded anti-stacking gate to allow concurrent execution up to active `concurrent_batch_size`.

---

## [v3.8.5] — 2026-09-25

### 🛠️ Pre-Flight AlgoTrading Permission Validation
* **MT5 Error 10027 Handler (`scripts/mt5_connector.py`)**:
  * Added pre-flight check for `terminal_info().trade_allowed`.
  * Generates immediate diagnostic alert when MT5 AlgoTrading button is disabled.

---

## [v3.8.4] — 2026-09-25

### 🧙 3-Step Telegram Interactive Wizard (`/wizard`)
* **Interactive Setup Flow (`scripts/telegram_listener.py`)**:
  * 3-step inline button wizard for Universe selection, Batch Concurrency (`1x`–`5x`), and Daily Rounds.
  * Dynamic session state generation with independent `$25.00` TP tracking per trade.

---

## [v3.8.3] — 2026-09-24

### 🎯 Sequential Multi-Trade Target Architecture
* **Fixed Per-Trade Target**:
  * Standardized fixed `$25.00` target per trade ticket with 80/70 Asymmetric Profit Protection tracking each ticket independently.

---

## [v3.8.2] — 2026-09-24

### 📱 Full Telegram Button Control & Engine Restart Broadcast
* **Persistent Custom Mobile Keyboard (`scripts/telegram_listener.py`)**:
  * Implemented permanent custom reply keyboard (`make_reply_keyboard()`) docked at the bottom of Telegram, providing instant zero-typing access to `/status`, `/scan`, `/start_session`, `/summary`, `/buy`, `/sell`, `/integrity`, and `/close`.
  * Added natural language and emoji button text mapping in `process_update()` so all tapped buttons immediately trigger their corresponding firm commands.
* **Native Telegram Bot Command Menu (`setMyCommands`)**:
  * Automatically registers official slash commands with Telegram Bot API on startup, equipping the mobile and desktop client with the native `[/]` menu.
* **Engine Online & Restart Alert Dispatcher**:
  * Added `send_engine_restart_alert()` triggered automatically on listener startup, dispatching live account telemetry, open exposure status, active background daemons, and security certification directly to Administrator `@wtalaat`.
* **Quick Buy/Sell Inline Callbacks**:
  * Added `cb_buy_gold` and `cb_sell_gold` callbacks on the inline menu for 1-tap market entries.

---

## [v3.8.1] — 2026-09-24

### 🔒 Remote Telegram Approval & Security Isolation
* **Remote File Modification Approval Engine (`scripts/telegram_listener.py`, `scripts/skill_integrity_guard.py`)**:
  * Added two-way interactive remote approval for code alterations. When an uncertified file change is detected, an emergency alert with an authorization token and inline `[ Approve ]` / `[ Reject ]` buttons is dispatched.
  * Enforced strict administrator identity gating (`is_admin`): only `@wtalaat` (`1264076025`) can authorize code modifications or lift the execution lockout.
* **Isolated Admin Security Routing (`config/alert_config.json`, `scripts/send_alert.py`)**:
  * Created `send_admin_telegram()` routing all security alerts, authorization tokens, and approval confirmations strictly to `@wtalaat`, isolating them completely from public channels/supergroups.
* **Executive Market Close Forensic Audit (`scripts/daily_summary.py`)**:
  * Upgraded `daily_summary.py` to compile forensic market close reports with all closed trades, entry/exit prices, durations, exit triggers (TP, SL, 80/70 Asymmetric), win/loss streaks, ROI %, and overnight open exposure checks.
  * Dispatched directly to Telegram Admin at market close (21:55 UTC) and on-demand via `/summary`.
* **Installation & Deployment Standard (`README.md`, `requirements.txt`)**:
  * Added production-ready `requirements.txt` and complete end-to-end installation, terminal setup, and daemon configuration documentation.

---

## [v3.8.0] — 2026-09-23

### 🛡️ 80/70 Asymmetric Profit Protection & Multi-Console Infrastructure
* **80/70 Asymmetric Profit Protection Engine (`scripts/trade_monitor.py`)**:
  * Monitors live open position floating profit against target.
  * When a trade reaches 80% of its profit target, tightens the profit floor to guarantee capturing at least 70% of peak gains if momentum falters.
* **Real-Time MT5 Deal Streamer**:
  * Continuously polls MT5 deal history and streams instantaneous closed-trade notifications to Telegram.
* **Two-Way Interactive Mobile Controller (`scripts/telegram_listener.py`)**:
  * 24/7 background listener supporting remote session launches (`/start_session`), live telemetry (`/status`), instant execution (`/buy`, `/sell`), and emergency liquidation (`/close`).
* **Cryptographic Anti-Tamper Security Guard (`scripts/skill_integrity_guard.py`)**:
  * Implements SHA-256 integrity validation on all protected skill and engine components, preventing unauthorized modifications from running against live accounts.
* **One-Click Multi-Console Launchers**:
  * Created `launch_all_consoles.bat` and `stop_all_consoles.bat` for Windows daemon management.

---

## [v3.0.0] — 2026-08-26

### 🛡️ Institutional Risk & Anti-Cascade Architecture
* **Dynamic ATR Volatility Floor (`docs/03_RISK_ENGINE_POSITION_SIZING.md`)**:
  * Enforces minimum stop loss distance of $1.5\times\text{ATR}$ (e.g. $\ge \$15.00$ on Gold) to eliminate noise-out stop runs.
  * Inverse lot scaling mathematically guarantees Dollar Risk is capped to exact user budgets (e.g. \$5.00, \$50.00, \$100.00).
* **Anti-Falling-Knife & Confirmation Entry Protocol (`docs/02_REGIME_STRATEGY_ENGINE.md`)**:
  * Eliminates blind limit order catching on falling supports.
  * Mandates 5M/15M candle close + Change of Character (CHoCH) structural confirmation before order triggers.
* **2-Strike Asset Lockout Rule**:
  * Automatically freezes an instrument for 60 minutes after 2 consecutive stop-outs, preventing cascading drawdown.
* **Bi-Directional Trend Agility**:
  * Dynamically flips regimes to `STRONG_DOWNTREND` upon 1H support breakdown, actively hunting Short / Sell opportunities instead of stubbornly buying.

---

## [v2.8.0] — 2026-08-26
* Added live MetaTrader 5 direct desktop execution engine (`scripts/mt5_connector.py`) and TradingView webhook bridge (`scripts/tradingview_bridge.py`).

---

## [v2.0.0] — 2026-08-25
* Added real-time TP1/TP2 milestone alerts and step-by-step manual execution guidance in `scripts/send_alert.py`.

---

## [v1.0.0] — 2026-08-24
* Initial release of the AI Autonomous Trading Firm skill.
