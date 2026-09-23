# Template: Trade Decision Ticket

Used by the Trade Committee and Risk Manager prior to dispatching any order.

---

```text
TRADE DECISION TICKET
============================================================
Ticket ID:              TRD-YYYYMMDD-XXX
Timestamp:              YYYY-MM-DD HH:MM:SS UTC

--- ASSET & STRATEGY ---
Instrument:             [e.g., XAUUSD / EURUSD / BTCUSDT / AAPL / US500]
Direction:              [BUY / SELL]
Strategy Selected:      [e.g., Pullback Continuation / Mean Reversion / Breakout]
Timeframe Alignment:    [HTF: 4H | ITF: 1H | LTF: 15M]
Market Regime:          [e.g., STRONG_UPTREND / RANGE / BREAKOUT]

--- STRATEGY SCORING & ELIMINATION GATES ---
Composite Score:        [e.g., 86.5 / 100] (Threshold: ≥ 75.0 required - PASS)
Structural Quality (S): [Score: 85/100 | Floor S≥50: PASS]
Quant Expectancy (Q):   [Score: 88/100 | Floor Q≥50: PASS]
Regime Alignment (R):   [Score: 90/100 | Floor R≥30: PASS]
Elimination Gate Status:[ALL FACTOR FLOORS CLEARED]

--- PRICING & SCALE-OUT TARGETS ---
Entry Price / Type:     [e.g., 2654.20 / Limit / Market]
Stop Loss (Mandatory):  [e.g., 2647.50] (Distance: XX pips / points / ATR buffer included)
Take Profit 1 (TP1):    [e.g., 2664.00] (1.5R | Close 40% volume -> Move SL to Break-Even)
Take Profit 2 (TP2):    [e.g., 2671.00] (2.5R | Close 40% volume -> Lock SL @ TP1)
Runner Target (TP3):    [e.g., 2685.00 / Structural Trailing Stop on remaining 20%]
Expected Risk/Reward:   [e.g., 1 : 2.50 aggregate]
Invalidation Thesis:    [Specific technical/structural event invalidating setup]

--- RISK & POSITION SIZING ---
Account Equity:         [$XX,XXX.XX]
Risk Percentage:        [e.g., 1.0%]
Risk Amount ($):        [$XXX.XX]
Calculated Position:    [XX.XX Lots / Units / Contracts]
Broker Lot Limits:      [Min: 0.01 | Max: 100.0 | Step: 0.01]
Required Margin:        [$XXX.XX] (% of Free Margin: XX.X%)

--- MULTI-AGENT COMMITTEE CONFLUENCE ---
Technical Assessment:   [Summary of EMAs, RSI, MACD, Volume]
Structure Assessment:   [Summary of HH/HL, BOS, CHoCH, Order Block, FVG]
Macro/Fundamental:      [Macro bias, physical balance / valuation]
News Calendar:          [Clean window; no high-impact release within 30 mins]
Sentiment Assessment:   [COT positioning / Long-Short retail ratio / Funding rate]
Quantitative Score:     [Win Prob: XX% | Expected Value: +$XXX]
Portfolio Exposure:     [Existing Risk: X.X% | Post-Trade Risk: X.X%]
Correlation Check:      [Max correlation with open trades: 0.XX - PASS/FAIL]

--- GOVERNANCE VOTE & VETO ---
Committee Supermajority: [X / 9 APPROVE | Y HOLD | Z REJECT] (Min 7 Required)
Risk Manager Decision:  [PASS / FAIL - UNILATERAL VETO AUTHORITY]

FINAL DECISION:         [EXECUTE / REJECT / HOLD]
Operational Reason:     [Detailed rationale for final execution or rejection]
============================================================
```
