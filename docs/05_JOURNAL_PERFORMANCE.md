# Trade Journal, Performance Analytics & Audit Standards

The Trading Firm maintains an immutable, chronologically sequenced trade journal and computes institutional performance metrics for continuous strategy refinement and auditability.

---

## 1. Trade Journal Schemas

### A. Executed Trade Telemetry Schema (`trade_log`)

```json
{
  "trade_id": "TRD-20260824-001",
  "session_id": "SES-LIVE-0824",
  "timestamp_signal": "2026-08-24T12:30:15Z",
  "timestamp_entry": "2026-08-24T12:31:02Z",
  "timestamp_exit": "2026-08-24T14:45:22Z",
  "instrument": "XAUUSD",
  "direction": "BUY",
  "strategy_family": "Pullback_Continuation",
  "market_regime": "STRONG_UPTREND",
  "timeframe_structure": {
    "htf": "4H",
    "itf": "1H",
    "ltf": "15M"
  },
  "pricing_and_levels": {
    "signal_price": 2652.40,
    "planned_entry": 2652.50,
    "actual_entry": 2652.55,
    "planned_stop": 2646.50,
    "tp1_target": 2661.50,
    "tp2_target": 2667.50,
    "runner_target": 2680.00,
    "slippage_points": 0.05
  },
  "scale_out_executions": {
    "tp1_actual_close_price": 2661.50,
    "tp1_volume_closed": 0.66,
    "tp2_actual_close_price": 2667.50,
    "tp2_volume_closed": 0.66,
    "runner_exit_price": 2673.20,
    "runner_volume_closed": 0.33,
    "exit_reason": "TP1_HIT_TP2_HIT_RUNNER_TRAILED"
  },
  "risk_and_sizing": {
    "account_equity_at_entry": 100000.00,
    "risk_percent": 1.0,
    "risk_dollars": 1000.00,
    "position_units": 165.28,
    "position_lots": 1.65,
    "planned_rr": 2.50,
    "realized_r": 2.38
  },
  "execution_telemetry": {
    "order_id": "BROKER-ORD-984321",
    "commission_paid": 9.90,
    "swap_fees": 0.00,
    "gross_pnl": 2390.00,
    "net_pnl": 2380.10
  },
  "committee_audit": {
    "committee_votes": "8 APPROVE / 1 HOLD / 0 REJECT",
    "risk_manager_decision": "PASS",
    "strategy_score": 86.5
  }
}
```

### B. Rejected Candidate Audit Schema (`rejection_log`)

```json
{
  "rejection_id": "REJ-20260824-004",
  "session_id": "SES-LIVE-0824",
  "timestamp": "2026-08-24T13:15:00Z",
  "instrument": "EURUSD",
  "direction": "SELL",
  "strategy_evaluated": "Breakout",
  "composite_strategy_score": 62.5,
  "rejection_stage": "RISK_MANAGER_VETO",
  "voting_breakdown": {
    "tech_vote": "APPROVE",
    "structure_vote": "APPROVE",
    "quant_vote": "HOLD (R:R only 1.45)",
    "news_vote": "APPROVE",
    "risk_manager_vote": "REJECT (VETO: Spread-to-stop ratio 22% exceeds 10% limit; US CPI in 20 mins)"
  },
  "action_taken": "DISCARDED_NO_TRADE"
}
```

---

## 2. Quantitative Performance Analytics

At the conclusion of each session (or upon user request via `STATUS`), the Compliance & Performance Analyst computes key statistical measures:

### Core Financial Metrics

* **Net Realized P&L**:
  $$\text{Net P\&L} = \sum \text{Gross Profit} - \sum \text{Gross Loss} - \sum \text{Commissions} - \sum \text{Slippage / Swaps}$$

* **Win Rate ($W$)**:
  $$W = \frac{N_{\text{Wins}}}{N_{\text{Total Trades}}} \times 100\%$$

* **Profit Factor ($PF$)**:
  $$PF = \frac{\sum \text{Profits from Winning Trades}}{\sum |\text{Losses from Losing Trades}|}$$

* **Mathematical Expectancy ($E$)**:
  $$E = (W \times \text{Average Win}) - ((1 - W) \times \text{Average Loss})$$

* **Average R-Multiple ($\bar{R}$)**:
  $$\bar{R} = \frac{1}{N} \sum_{i=1}^{N} \frac{\text{Net P\&L}_i}{\text{Initial Risk Amount}_i}$$

* **Maximum Drawdown ($MDD$)**:
  $$MDD = \max_{t \in [0, T]} \left( \frac{\text{Peak Equity}_t - \text{Trough Equity}_t}{\text{Peak Equity}_t} \right) \times 100\%$$

* **Sharpe Ratio ($SR$)**:
  $$SR = \frac{\bar{R}_p - R_f}{\sigma_p}$$
  *Where $\bar{R}_p$ is the annualized mean portfolio return, $R_f$ is the risk-free rate, and $\sigma_p$ is the standard deviation of excess returns.*

* **Sortino Ratio ($SoR$)**:
  $$SoR = \frac{\bar{R}_p - R_f}{\sigma_d}$$
  *Where $\sigma_d = \sqrt{\frac{1}{N} \sum_{i=1}^N \min(0, R_i - \text{Target})^2}$ measures only downside volatility.*

---

## 3. Behavioral Integrity & Anti-Pattern Detection

The compliance engine scans trade records in real time to detect and block forbidden algorithmic behaviors:

```text
+-------------------------------------------------------------------------------+
|                       PROHIBITED TRADING BEHAVIORS                            |
+-------------------------------------------------------------------------------+
| 1. REVENGE TRADING: Accelerating trade frequency immediately after a loss.    |
| 2. MARTINGALE / POSITION DOUBLING: Increasing size after negative outcomes.  |
| 3. LOSS CHASING: Widening stop loss or removing invalidation levels.         |
| 4. SIGNAL FABRICATION: Generating unverified entries to meet quota.          |
| 5. DATA TAMPERING: Editing historical trade logs or retroactively modifying  |
|    prices to improve apparent track records.                                  |
| 6. OVER-CONFIDENCE BIAS: Declaring 100% certainty or guaranteeing profits.   |
+-------------------------------------------------------------------------------+
```

*Any violation triggers immediate session suspension and alerts the Chief Trading Officer.*
