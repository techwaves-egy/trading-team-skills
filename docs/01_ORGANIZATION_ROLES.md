# Multi-Agent Organization & Role Specifications

The **AI Autonomous Trading Firm** functions as a coordinated multi-disciplinary organization of 16 specialized roles organized into five functional divisions.

---

## 1. Executive & Governance Division

### 1. Chief Trading Officer (CTO)
* **Mission**: Leads session operations, ensures multi-agent synchronization, and enforces compliance with organizational charters.
* **Responsibilities**:
  - Initializes trading sessions and validates user configuration parameters.
  - Manages session lifecycle state (`ACTIVE`, `PAUSED`, `STOPPED`).
  - Resolves team conflicts using the **Decision Priority Hierarchy**.
  - Coordinates post-session reviews, audit reports, and debriefs.

### 2. Portfolio Manager (PM)
* **Mission**: Manages aggregate capital allocation, sector diversification, and overall portfolio risk.
* **Responsibilities**:
  - Sets net and gross exposure caps across asset classes (Max 3.0% total portfolio risk).
  - Ranks trade candidates across disparate markets to optimize risk-adjusted expected return ($E[R]$).
  - Enforces portfolio-level correlation limits ($\rho > 0.70$) to prevent accidental concentration.

### 3. Trade Committee Quorum Governance
* **Mission**: Multi-disciplinary review council that evaluates trade candidates prior to execution.
* **Composition (9 Voting Specialist Seats)**:
  1. Technical Analyst
  2. Market Structure Analyst
  3. Quant Analyst
  4. Volatility Analyst
  5. Correlation Analyst
  6. Strategy Selection Specialist
  7. Market Regime Analyst
  8. Macro & Fundamental Analyst
  9. News & Sentiment Analyst
* **Voting Precedence & Resolution Rules (Applied in Strict Sequence)**:
  1. **REJECT Check (Highest Precedence)**: If $\ge 3$ members vote `REJECT`, the ticket is **immediately discarded** and logged in the Rejection Journal.
  2. **HOLD Check (Second Precedence)**: If $\ge 2$ members vote `HOLD` (and REJECT $< 3$), the candidate is placed in the **staging queue** for up to 3 intermediate candles awaiting confirmation.
  3. **Supermajority Quorum Check**: If $\ge 7$ out of 9 members vote `APPROVE` (with $< 2$ HOLD and $< 3$ REJECT), the ticket **passes to the Risk Gate**.
  4. **Risk Manager Absolute Veto**: The Risk Manager evaluates the approved ticket independently. A single `FAIL` vetoes the trade regardless of unanimous committee approval.

---

## 2. Market Intelligence Division

### 4. Macro Analyst
* **Scope**: Macroeconomic drivers, monetary policy, and intermarket relationships.
* **Coverage**: Interest rates, central bank forward guidance (Fed, ECB, BOE, BOJ), GDP growth, inflation metrics (CPI, PCE), employment figures (NFP, unemployment rate), and yield curve dynamics.

### 5. Fundamental Analyst
* **Scope**: Asset-specific fundamental valuation.
* **Coverage**:
  - **Equities**: Revenue growth, EPS surprises, balance sheet strength, free cash flow, valuation multiples (P/E, EV/EBITDA).
  - **Commodities / Metals**: Physical supply/demand balances, inventory reports (EIA, API, LME/COMEX stocks), geopolitical supply constraints, cost of production.
  - **Crypto**: On-chain metrics (active addresses, NVT ratio, exchange reserves, miner/validator flows, token unlock schedules).

### 6. Technical Analyst
* **Scope**: Quantitative price action and mathematical indicator synthesis.
* **Coverage**: Multi-timeframe trend alignment, exponential moving averages (20, 50, 200 EMA), momentum oscillators (RSI, MACD, Stochastic), volatility indicators (ATR, Bollinger Bands), and volume-weighted pricing (VWAP, Volume Profile).
* *Rule*: Indicators serve as corroborating evidence, never standalone automated signals.

### 7. Market Structure Analyst
* **Scope**: Price structure, liquidity dynamics, and supply/demand mechanics.
* **Coverage**: Structural high/low sequences (HH, HL, LH, LL), Break of Structure (BOS), Change of Character (CHoCH), Order Blocks, Fair Value Gaps (FVG), liquidity pools (equal highs/lows), and consolidation boundaries.

### 8. Senior Macro & Economic News Analyzer (Advisor to Chief Risk Officer)
* **Mission**: Ingests live macroeconomic calendars (`scripts/news_analyzer.py` via ForexFactory JSON/XML/CSV multi-tier feeds and local caching in `config/economic_calendar.json`), monitors real-time event countdowns, enforces automated high-impact event blackouts ($\pm 30\text{ mins}$ pre/post event), and provides strategic counsel directly to Chief Risk Officer `@wtalaat`.
* **Coverage**:
  - **Inflation & Price Indices**: Consumer Price Index (CPI / Core CPI), Producer Price Index (PPI), Personal Consumption Expenditures (PCE / Core PCE).
  - **Labor & Employment**: Non-Farm Employment Change (NFP), Unemployment Rate, Average Hourly Earnings, Initial Jobless Claims.
  - **Central Bank Monetary Policy**: FOMC Interest Rate Decisions, FOMC Minutes, Fed Chair Powell Press Conferences, ECB Rate Decisions & President Lagarde Speeches.
  - **Macro Activity & Sentiment**: Gross Domestic Product (GDP / Advance GDP), Retail Sales, ISM Manufacturing & Services PMI.
* **CRO Advisory Threat Level Protocol**:
  - 🔴 **`RED (CRITICAL NEWS BLACKOUT)`**: High-impact event active or releasing within $\le 30$ mins (or within 15 mins post-event). **Enforcement:** Automated Gate 0.02 blocks all new entries; advises CRO to advance open positions to Server-Side 80/70 SL or exit.
  - 🟡 **`YELLOW (ELEVATED MACRO WATCH)`**: High-impact release in 31–120 mins, or medium-impact release in $\le 30$ mins. **Enforcement:** Restricts batch concurrency to single 0.01 micro-lots; prepares for shutdown countdown.
  - 🟢 **`GREEN (CLEAR SAILING)`**: No high-impact events scheduled within the next 2+ hours. **Enforcement:** Full algorithmic clearance for Bollinger Bands 2.0-$\sigma$ Mean Reversion and standard dynamic batch sizing.
* **Trade Committee Precedence**: Holds unilateral suspension advisory authority to the CRO. If the News Analyzer flags `RED`, the Risk Manager and CRO instantly veto trade generation regardless of technical setups.

### 9. Sentiment Analyst
* **Scope**: Market sentiment and positioning extremes.
* **Coverage**: Commitment of Traders (COT) positioning, retail sentiment ratios (long/short %), Options Put/Call ratios, Crypto Fear & Greed Index, and funding rates.

---

## 3. Quantitative & Statistical Division

### 10. Quantitative Analyst
* **Scope**: Statistical probability, expected value, and return distributions.
* **Coverage**: Historical win rate of identified patterns, profit factor distributions, mathematical expectancy ($E = (\text{Win\%} \times \text{Avg Win}) - (\text{Loss\%} \times \text{Avg Loss})$), and risk/reward optimization.

### 11. Volatility Analyst
* **Scope**: Volatility regime classification and expansion/contraction cycles.
* **Coverage**: Average True Range (ATR), Realized Volatility (RV), Implied Volatility (IV / VIX / GVZ / OVX), Bollinger Band Width (BBW), and historical volatility percentile.

### 12. Correlation Analyst
* **Scope**: Cross-asset and cross-instrument correlation tracking.
* **Coverage**: Rolling 30-day/90-day Pearson correlation matrices. Prevents opening concurrent long positions in highly correlated pairs ($\rho > +0.70$) without adjusted risk discounts.

---

## 4. Strategy & Regime Division

### 13. Market Regime Engine
* **Scope**: Multi-timeframe classification of the prevailing market environment across the **Market $\times$ Timeframe Matrix**.
* **Regimes**: `STRONG_UPTREND`, `WEAK_UPTREND`, `STRONG_DOWNTREND`, `WEAK_DOWNTREND`, `RANGE`, `SIDEWAYS`, `BREAKOUT`, `HIGH_VOLATILITY`, `LOW_VOLATILITY`, `EVENT_DRIVEN`, `UNCERTAIN`.
* *Rule*: If the regime is `UNCERTAIN`, the engine immediately outputs `NO TRADE`.

### 14. Strategy Selection Specialist
* **Scope**: Strategy deployment and strategy competition matrix.
* **Strategy Families**: Trend Following, Pullback/Continuation, Breakout, Momentum, Mean Reversion, Volatility Strategy, Event-Driven, No Trade.
* *Rule*: Automatically determines the winning strategy by calculating competitive fitness scores (0–100) per tradeable instrument. Never queries the user for strategy preference.

---

## 5. Risk, Execution & Operations Division

### 15. Risk Manager (Absolute Veto Authority)
* **Mission**: Capital preservation and strict enforcement of risk guardrails.
* **Authority**: **Absolute Veto Power**. Can reject any candidate regardless of unanimous approval from all other analysts. No agent can override the Risk Manager.
* **Enforcements**: Maximum risk per trade, maximum daily drawdown limit, margin requirements, mandatory stop loss placement with asset-specific ATR buffers, broker order size sanity, and slippage buffer constraints.

### 16. Execution & Position Management Agent
* **Mission**: High-precision trade routing, 24/7 background listener daemons, dual In-Chat/Telegram approval confirmation, real-time Take Profit (TP1/TP2) & Stop Loss manual action dispatching, and active position lifecycle control.
* **Responsibilities**:
  - Live bid/ask spread checks, slippage evaluation, and order construction (Market, Limit, Stop Limit).
  - Manages the 9-state order machine and verifies execution confirmations.
  - Monitors open positions, manages 3-tier scale-outs (TP1: 40% + BE, TP2: 40% + Lock Profit, Runner: 20%), and trails stops.
  - Dispatches immediate step-by-step mobile execution alerts when milestones are reached.
  - Handles broker disconnects, timeouts, and post-session trade journaling.
