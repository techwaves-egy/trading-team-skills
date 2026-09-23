# Template: Session Status Telemetry

Returned whenever the user issues the `STATUS` command (in chat or via `/status` on Telegram).

---

### Case 1: If Session is NOT YET Configured

```text
TRADING SESSION STATUS: UNCONFIGURED
============================================================
No active trading session is currently running.

To initialize an autonomous trading session, please provide:
1. Target Market(s) (Forex, Gold, Crypto, Stocks, Indices, Commodities, Futures, Multiple)
2. Maximum number of trades (ceiling limit)
3. Trading mode (A. Analysis Only, B. Paper Trading, C. Approval, D. LIVE)
4. Maximum risk per trade (% of equity or fixed $)
5. Maximum daily loss limit (% of equity or fixed $)
6. Mobile Notification preferences (Telegram / Discord)
============================================================
```

---

### Case 2: If Session is ACTIVE / RUNNING

```text
TRADING SESSION STATUS
============================================================
Session ID:             SES-YYYYMMDD-XXX
System Status:          ACTIVE / MONITORING
Current Time (UTC):     YYYY-MM-DD HH:MM:SS

--- CONFIGURATION & CHANNELS ---
Markets Configured:     [e.g., Gold, Crypto, Stocks]
Trading Mode:           [Analysis Only / Paper / Approval / LIVE]
Maximum Trade Limit:    [e.g., 10]
Telegram Dispatch:      🟢 Active (Broadcasting to VIP Signals + Personal DM)

--- TRADE EXECUTION METRICS ---
Trades Executed:        [X]
Trades Remaining:       [Y] (Ceiling: Max - Executed)
Trades Rejected:        [Z] (Logged in Rejection Journal)
Open Active Positions:  [N]

--- RISK & PORTFOLIO EXPOSURE ---
Current Account Equity: [$XXX,XXX.XX]
Total Gross Risk:       [X.XX%] (Limit: 3.00%)
Unrealized P&L:         [+$XXX.XX / -$XXX.XX]
Daily Realized P&L:     [+$XXX.XX / -$XXX.XX]
Daily Drawdown Level:   [X.XX%] (Hard Circuit Breaker Cap: X.XX%)

--- CURRENT REGIMES & ACTIVE SCANS ---
Dominant Regimes:
  - Gold (XAUUSD):      STRONG_UPTREND (1H FVG Retracement)
  - Bitcoin (BTCUSDT):  BREAKOUT (S/R Retest Continuation)
  - NVIDIA (NVDA):      STRONG_UPTREND (Dynamic 20 EMA Pullback)

--- ACTIVE OPEN POSITIONS ---
[Pos #1] BTCUSDT | BUY (LONG)
  - Fill Entry: $79,650.00 | Size: 0.083 BTC ($100.00 Risk)
  - Hard Stop Loss: $78,450.00
  - Next Milestone: TP1 @ $81,450.00 (Close 40% -> Move SL to Break-Even)
  - Status: 🟢 ACTIVE

[Pos #2] XAUUSD | BUY (LONG)
  - Fill Entry: $4,648.50 | Size: 1.11 Lots ($1,000.00 Risk)
  - Hard Stop Loss: $4,639.50
  - Next Milestone: TP1 @ $4,662.00 (Close 40% -> Move SL to Break-Even)
  - Status: 🟢 ACTIVE
============================================================
```
