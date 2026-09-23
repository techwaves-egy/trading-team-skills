# Template: Trading Session Completion Report

Delivered upon session termination or when all stop conditions are satisfied.

---

```text
TRADING SESSION COMPLETE
============================================================
Session ID:             SES-YYYYMMDD-XXX
Termination Reason:     [MAX_TRADES_REACHED / DAILY_RISK_LIMIT_REACHED / USER_REQUESTED_STOP / SESSION_EXPIRED]
Duration:               [X hours Y minutes]

--- CONFIGURATION & EXECUTION COUNTS ---
Markets Traded:         [e.g., Gold, Forex, Crypto]
Trading Mode:           [Analysis Only / Paper / Approval / LIVE]
Maximum Trade Cap:      [e.g., 5]
Total Trades Executed:  [X]
Total Trades Rejected:  [Y] (Logged in Rejection Audit Journal)
Remaining Unused Cap:   [Z]

--- FINANCIAL OUTCOMES ---
Starting Equity:        [$XX,XXX.XX]
Ending Equity:          [$XX,XXX.XX]
Gross Profit:           [+$X,XXX.XX]
Gross Loss:             [-$X,XXX.XX]
Commissions & Slippage: [-$XX.XX]
Net Realized P&L:       [+$X,XXX.XX / -$X,XXX.XX] (±X.XX%)
Unrealized Open P&L:    [+$XXX.XX / -$XXX.XX]
Peak Equity / Max DD:   [$XX,XXX.XX / -X.XX%]

--- QUANTITATIVE METRICS ---
Winning Trades:         [A] (Win Rate: XX.X%)
Losing Trades:          [B]
Breakeven Trades:       [C]
Profit Factor:          [X.XX]
Average R-Multiple:     [+X.XX R]
Mathematical Expectancy:[+$XX.XX per trade]
Sharpe Ratio:           [X.XX]
Sortino Ratio:          [X.XX]

--- STRATEGY PERFORMANCE BREAKDOWN ---
- Mean Reversion:       [2 Trades | 2 Wins | Net P&L: +$1,850.00 | Avg R: +2.3R]
- Pullback Continuation:[1 Trade  | 1 Win  | Net P&L: +$610.00   | Avg R: +1.5R]
- Breakout:             [1 Trade  | 1 Loss | Net P&L: -$500.00   | Avg R: -1.0R]

--- REJECTED CANDIDATES AUDIT SUMMARY ---
- Total Candidates Screened: [XX]
- Rejected at Committee:     [YY] (Failed quorum / R:R threshold)
- Rejected at Risk Gate:     [ZZ] (Vetoed for spread/news/correlation overlap)

--- TRADE HIGHLIGHTS ---
Best Trade:             [XAUUSD Short | Net P&L: +$1,250.00 (+2.5R) | Strategy: Mean Reversion]
Worst Trade:            [BTCUSDT Long | Net P&L: -$500.00 (-1.0R) | Strategy: Breakout]

--- AUDIT & POST-MORTEM NOTES ---
[Key lessons, market regime behavior during session, slippage notes, and recommendations for subsequent trading sessions.]
============================================================
```
