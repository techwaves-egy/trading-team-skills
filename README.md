# 🏛️ AI Autonomous Trading Firm — Institutional Workspace (v3.8.0)

[![Python 3.10+](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://www.python.org/)
[![MetaTrader 5](https://img.shields.io/badge/MetaTrader-5-darkgreen.svg)](https://www.metatrader5.com/)
[![Security: Anti-Tamper SHA-256](https://img.shields.io/badge/Security-Cryptographic%20Guarded-green.svg)](scripts/skill_integrity_guard.py)
[![Telegram Remote Control](https://img.shields.io/badge/Telegram-Remote%20Approval%20Enabled-0088cc.svg)](scripts/telegram_listener.py)

Institutional multi-agent AI trading organization engineered for live market analysis, automated regime detection, confirmation entry protocols, dynamic ATR volatility floors, 2-strike asset lockouts, dynamic strategy competition, quantitative risk management, order execution, dual In-Chat/Telegram approvals, real-time Take Profit & Stop Loss action guidance, native **MetaTrader 5 direct desktop execution**, and **TradingView webhooks**.

---

## 📋 System Prerequisites

* **Operating System:** Windows 10, Windows 11, or Windows Server 2019/2022 (Required for native MetaTrader 5 Python IPC connector).
* **Python Runtime:** Python 3.10 or higher (64-bit required by MetaTrader5 API).
* **Trading Terminal:** [MetaTrader 5 Desktop](https://www.metatrader5.com/) installed and logged into an active broker account (Demo or Live).
* **Telegram Bot:** A bot created via [@BotFather](https://t.me/BotFather) with an API Bot Token and your personal Telegram Chat ID (obtainable via [@userinfobot](https://t.me/userinfobot)).
* **Version Control:** Git.

---

## 🛠️ Installation & Setup Guide

### Step 1: Clone the Repository
Clone the private repository to your local trading machine:
```bash
git clone https://github.com/techwaves-egy/trading-team-skills.git
cd trading-team-skills
```

### Step 2: Set Up Python Virtual Environment
It is recommended to run within a dedicated virtual environment:
```powershell
# Create virtual environment
python -m venv venv

# Activate virtual environment (Windows PowerShell)
.\venv\Scripts\Activate.ps1

# Upgrade pip and install all required dependencies
pip install --upgrade pip
pip install -r requirements.txt
```

### Step 3: Configure MetaTrader 5 Desktop Terminal
1. Launch your **MetaTrader 5 Desktop** application and log into your broker account.
2. In MT5, navigate to **Tools** > **Options** (or press `Ctrl + O`).
3. Select the **Expert Advisors** tab.
4. Check **"Allow Algorithmic Trading"**.
5. Ensure **"Disable algorithmic trading when account has been changed"** is unchecked if you frequently switch demo/live accounts.
6. Click **OK**. Keep the MetaTrader 5 terminal running in the background.

### Step 4: Configure Telegram & Alert Credentials
Open [`config/alert_config.json`](config/alert_config.json) and set your bot credentials:
```json
{
  "telegram": {
    "enabled": true,
    "bot_token": "YOUR_TELEGRAM_BOT_TOKEN_FROM_BOTFATHER",
    "admin_username": "your_telegram_username",
    "admin_chat_id": "YOUR_PERSONAL_CHAT_ID",
    "allowed_user_ids": [
      "YOUR_PERSONAL_CHAT_ID"
    ],
    "chat_ids": [
      "YOUR_PERSONAL_CHAT_ID",
      "-100XXXXXXXXXX"
    ]
  },
  "settings": {
    "min_strategy_score_to_alert": 75,
    "alert_on_tp_sl_updates": true,
    "alert_on_regime_shifts": true,
    "sound_notification": true
  }
}
```
* **`admin_chat_id` / `admin_username`**: Receives all sensitive administrative alerts, anti-tamper notifications, authorization tokens, and approval confirmations exclusively.
* **`allowed_user_ids`**: Whitelist of Telegram user IDs permitted to issue commands (`/start_session`, `/buy`, `/sell`, `/approve`, `/close`).
* **`chat_ids`**: Channels/groups receiving public trading signals, TP/SL alerts, and daily summaries (e.g. VIP Signals channel).

### Step 5: Antigravity / Agentic IDE Skill Registration
To register this workspace as a native Agent Skill in Antigravity or Claude Code:
1. Ensure the directory is copied or linked into your global skills directory:
   ```powershell
   # Default Antigravity global skills location:
   C:\Users\<username>\.gemini\config\skills\autonomous-trading-firm\
   ```
2. The orchestrator automatically loads [`SKILL.md`](SKILL.md) upon invocation.

### Step 6: Initial Cryptographic Integrity Certification
The firm includes an active Anti-Tamper Security Guard that cryptographically certifies all protected code files:
```powershell
# Generate initial signed SHA-256 manifest
python scripts/skill_integrity_guard.py --authorize
```
You will receive an instant confirmation alert on your Telegram verifying all protected files are signed and certified.

---

## 🚀 Running the Trading Firm

### Option A: One-Click Multi-Console Launcher (Recommended)
Double-click [`launch_all_consoles.bat`](launch_all_consoles.bat) or run from terminal:
```powershell
.\launch_all_consoles.bat
```
This spawns 4 dedicated console windows:
1. **Telegram Listener:** 24/7 interactive two-way remote command handler.
2. **Auto-Scanner Engine:** 15-minute multi-instrument regime scanner.
3. **Trade Monitor:** Real-time MT5 deal tracker with 80/70 Asymmetric Profit Protection.
4. **Daily Summary:** Scheduled 23:59 EEST performance audit dispatcher.

To gracefully stop all active consoles, execute:
```powershell
.\stop_all_consoles.bat
```

### Option B: Standalone Daemon Execution
Run the services independently as needed:
```powershell
# 1. Start Two-Way Telegram Listener
python scripts/telegram_listener.py

# 2. Start Auto-Scanner (specify interval in minutes, e.g. 15)
python scripts/auto_scanner.py 15

# 3. Start Trade Closure & Asymmetric Protection Monitor
python scripts/trade_monitor.py

# 4. Start Daily Summary Scheduled Daemon
python scripts/daily_summary.py --daemon
```

---

## 📱 Telegram Remote Commands Directory

All authorized users listed in `allowed_user_ids` can interact with the firm remotely via Telegram:

| Command | Description | Example |
| :--- | :--- | :--- |
| `/start_session [n] [x]` | Launch autonomous trading session with trade quota and leverage | `/start_session 5 2x` |
| `/trade` | Quick-start default session | `/trade` |
| `/status` | View live account balance, equity, open positions & remaining quota | `/status` |
| `/buy [sym] [vol]` | Direct instant market BUY execution | `/buy XAUUSD 0.02` |
| `/sell [sym] [vol]` | Direct instant market SELL execution | `/sell EURUSD 0.10` |
| `/scan` | Force an immediate market sweep across watchlist | `/scan` |
| `/close` | **Emergency Kill Switch:** Liquidate all open positions instantly | `/close` |
| `/stop` | Pause active auto-scanner and halt new entries | `/stop` |
| `/summary` | Generate on-demand daily performance audit | `/summary` |
| `/weekly` | Generate comprehensive weekly institutional audit | `/weekly` |
| `/integrity` | Verify SHA-256 anti-tamper security status | `/integrity` |
| `/approve [token]` | **Remote Authorization:** Certify pending file modifications | `/approve 94FD` |
| `/reject [token]` | Reject pending modification & maintain execution freeze | `/reject 94FD` |

---

## 🔒 Remote Approval & Anti-Tamper Protocol

If any protected file (`SKILL.md`, `scripts/*.py`, `docs/*.md`) is modified without prior certification:
1. **Execution Lockout:** The firm freezes all trade execution immediately to protect capital.
2. **Security Alert:** An emergency alert is routed **strictly to `@admin_username`** with a unique 4-character authorization token (e.g. `94FD`) and inline action buttons.
3. **Admin Verification:** The administrator reviews the detected hash discrepancies and taps **`[ ✅ Approve Modification ]`** (or replies `/approve <token>`).
4. **Resumption:** The guard cryptographically recalculates and re-signs `config/skill_checksums.json`, lifts the lockout, and broadcasts a green clearance confirmation.

---

## 🏛️ Organizational Structure

The firm operates 16 coordinated specialist roles across 5 operational divisions:

```
├── 1. Executive & Governance:     Chief Trading Officer (CTO), Portfolio Manager, Trade Committee (9-Member Quorum)
├── 2. Market Intelligence:        Macro, Fundamental, Technical, Market Structure, News, Sentiment Analysts
├── 3. Quantitative & Statistical: Quant & Statistical Analyst, Volatility Analyst (ATR Floor Guard), Correlation Analyst
├── 4. Strategy & Regimes:         Market Regime Engine (Bi-Directional Agility), Strategy Selection Specialist
└── 5. Risk & Execution:           Risk Manager (Absolute Veto & 2-Strike Lockout), Execution & Position Management Agent
```

---

## 📂 Repository Layout

```
d:/Techwaves-egy/Trading Team Skills/
├── SKILL.md                               # Master Skill definition (v3.8.0) and primary orchestrator
├── README.md                              # Workspace overview, installation & operation guide
├── requirements.txt                       # Python dependencies
├── CHANGELOG.md                           # Version history
├── launch_all_consoles.bat                # One-click Windows multi-console daemon launcher
├── stop_all_consoles.bat                  # One-click process termination utility
├── config/
│   ├── alert_config.json                  # Multi-chat Telegram & Discord credentials + Admin routing
│   ├── broker_config.json                 # MetaTrader & Broker API configuration
│   ├── skill_checksums.json               # Cryptographically signed SHA-256 security manifest
│   ├── pending_authorizations.json        # Active Telegram remote approval tokens
│   └── session_state.json                 # Live session parameters & risk ceilings
├── scripts/
│   ├── skill_integrity_guard.py           # Anti-tamper cryptographic verification & approval engine
│   ├── telegram_listener.py               # 24/7 interactive two-way Telegram command & callback listener
│   ├── auto_scanner.py                    # Autonomous periodic market sweep engine
│   ├── trade_monitor.py                   # Real-time deal streamer & 80/70 profit protection
│   ├── daily_summary.py                   # Scheduled P&L audit dispatcher (23:59 EEST)
│   ├── mt5_connector.py                   # Direct native MetaTrader 5 terminal connector
│   └── send_alert.py                      # Telegram/Discord multi-channel alerting bridge
├── docs/
│   ├── 01_ORGANIZATION_ROLES.md           # 16-role duties, committee voting precedence, and veto gates
│   ├── 02_REGIME_STRATEGY_ENGINE.md       # 10 regimes, 8 strategies, Confirmation Entry Protocol
│   ├── 03_RISK_ENGINE_POSITION_SIZING.md  # Dynamic ATR Volatility Floor, Hard Dollar Risk Ceilings
│   ├── 04_EXECUTION_LIFECYCLE.md          # 9-state order lifecycle, Dual In-Chat & Telegram Approval flows
│   ├── 05_JOURNAL_PERFORMANCE.md          # Forensic executed & rejection JSON schemas, Sharpe/Sortino math
│   ├── 06_POSITION_MANAGEMENT_RULES.md    # 3-tier scale-out matrix (40/40/20), real-time TP/SL action alerts
│   ├── 07_MARKET_SCAN_UNIVERSE.md         # Master asset watchlists, 5 liquidity filters, trading sessions
│   ├── 08_BROKER_INTEGRATIONS.md          # MT4/5, Interactive Brokers, Binance API & simulated fallback
│   ├── 09_INTER_AGENT_COMMUNICATION.md    # Inter-agent message schemas, sequence flow, and pipeline handoffs
│   ├── 10_NOTIFICATION_CHANNELS.md        # Telegram multi-chat broadcasting, TP/SL alerts, interactive buttons
│   ├── 11_BACKGROUND_MONITORING_DAEMON.md # 24/7 Telegram listeners, periodic sweep engines, mobile commands
│   └── 12_METATRADER_TRADINGVIEW_INTEGRATION.md # Native MT5 connector, TradingView webhooks & Pine script
└── templates/
    ├── SESSION_INTAKE.md                  # Pre-flight 6-parameter questionnaire template
    ├── TRADE_DECISION_TICKET.md           # Candidate evaluation, multi-TP targets, and committee voting
    ├── TP_SL_ACTION_ALERTS.md             # Real-time milestone action guidance templates
    ├── SESSION_STATUS.md                  # Live telemetry dashboard and scale-out position tracker
    └── SESSION_SUMMARY.md                 # End-of-session comprehensive audit report
```

---

## ⏪ Version Control & Rollback Guide

The firm strictly adheres to Git version control. Every modification is cryptographically signed, committed, tagged, and pushed to the private GitHub repository.

### 1. View All Version Milestones & History
```bash
# List all release tags and descriptions
git tag -l -n

# View recent commit history with hashes
git log --oneline -n 10
```

### 2. Available Stable Version Checkpoints
| Tag | Release Date | Description |
| :--- | :--- | :--- |
| `v3.8.2` | 2026-09-24 | Full Persistent Telegram Button Controls, Native Menu, and Engine Restart Broadcast. |
| `v3.8.1` | 2026-09-24 | Remote Telegram Admin Approval, Security Isolation, Market Close Forensic Audit. |
| `v3.8.0-stable` | 2026-09-23 | Baseline stable release with 80/70 Asymmetric Profit Protection & MT5 deal streamer. |

### 3. How to Revert or Roll Back Anytime

#### A. Inspect / Test an Older Version (Detached HEAD)
To temporarily explore or run an older version without altering current branch history:
```bash
git checkout v3.8.0-stable
```
To return back to the latest version:
```bash
git checkout master
```

#### B. Roll Back to a Previous Version on a New Branch
```bash
# Create and switch to a rollback branch based on a stable tag
git checkout -b rollback-v3.8.0 v3.8.0-stable
```

#### C. Fully Reset Master Branch to a Previous Version
If you want to forcefully reset `master` back to a previous tag:
```bash
# Hard reset working directory to stable checkpoint
git reset --hard v3.8.0-stable

# Re-sign the cryptographic security manifest for the restored state
python scripts/skill_integrity_guard.py --authorize

# Force push to private GitHub (if replacing remote master)
git push origin master --force
```

#### D. Safely Undo a Specific Commit
```bash
git revert <commit_hash>
git push origin master
```

---

## ⚖️ License & Confidentiality
Proprietary & Confidential. All rights reserved &copy; TechWaves EGY.
Unauthorized copying, decompiling, redistribution, or modification without cryptographic administrative authorization is strictly prohibited.
