# Changelog — AI Autonomous Trading Firm Skill

All notable changes and architectural upgrades to the AI Autonomous Trading Firm skill are documented in this file.

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
