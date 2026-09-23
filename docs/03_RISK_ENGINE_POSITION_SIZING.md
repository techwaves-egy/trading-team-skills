# Risk Engine, Position Sizing & ATR Floor Protections (v3.0.0)

The **Risk Manager** holds **Absolute Unilateral Veto Power** over every trade proposal. Capital preservation is the firm's primary objective.

---

## 1. Dynamic ATR Volatility Floor ($\text{SL} \ge 1.5\times\text{ATR}$)

> [!CAUTION]
> **Noise-Out Prevention Rule**: Never place a Stop Loss tighter than the instrument's natural hourly volatility. A tight stop inside ATR noise guarantees random stop-outs.

```text
Minimum Stop Loss Distance = max(Structural Invalidation Point, 1.5 * ATR_14)
```

### ATR Buffer Thresholds by Asset Class:
* **Gold (XAUUSD)**: $1.5\times\text{ATR}_{1H} \approx \mathbf{\$15.00 - \$22.00}$. Minimum stop distance = **\$15.00**.
* **Bitcoin (BTCUSDT)**: $1.5\times\text{ATR}_{1H} \approx \mathbf{\$800.00 - \$1,400.00}$.
* **EURUSD**: $1.5\times\text{ATR}_{1H} \approx \mathbf{25 - 40\text{ pips}}$.
* **Equities / Tech**: $1.5\times\text{ATR}_{1H} \approx \mathbf{1.5\% - 2.5\%}$ of stock price.

---

## 2. Hard Mathematical Dollar Risk Ceiling

To ensure that wider, safer stop losses never risk more than the user's explicit risk budget (e.g., \$5.00, \$50.00, or \$100.00), the firm **scales down lot volume inversely**:

$$\text{Position Volume (Lots)} = \frac{\text{Configured Dollar Risk Budget (\$)}}{\text{Stop Loss Distance in \$} \times \text{Contract Size}}$$

### Worked Example for Gold ($15.00 Stop Distance):
* User sets **\$5.00 Risk Budget**:
  $$\text{Lots} = \frac{\$5.00}{\$15.00 \times 100} = \mathbf{0.01\text{ Micro Lot}} \quad (\text{Max Dollar Risk: } \$5.00 \text{ to } \$15.00)$$
* User sets **\$100.00 Risk Budget**:
  $$\text{Lots} = \frac{\$100.00}{\$15.00 \times 100} = \mathbf{0.06\text{ Lots}} \quad (\text{Max Dollar Risk strictly capped at } \$90.00)$$

---

## 3. Post-Loss Recovery & Cool-Down Protocols

| Condition | Action | Duration |
| :--- | :--- | :--- |
| **Single Loss** | Normal 15-minute analytical pause before next scan. | 15 Minutes |
| **2 Consecutive Losses on Same Asset** | **Mandatory Asset Lockout & Regime Re-evaluation**. | **60 Minutes** |
| **3 Consecutive Losses across Portfolio** | Reduce maximum position sizing by **50%** on subsequent trades. | 4 Hours |
| **Daily Loss Limit Breached ($\ge \text{Max Daily Loss}$)** | **Immediate Daily Circuit Breaker**: Halt all scanning, close discretionary scalps. | Until next 00:00 UTC |

---

## 4. Unilateral Risk Manager Veto Criteria

The Risk Manager executes an **immediate rejection** if any of the following 7 conditions are met:
1. `Dollar Risk > Session Risk Budget`
2. `Stop Loss Distance < 1.5 * ATR`
3. `Reward-to-Risk Ratio < 1 : 2.00`
4. `Spread > 15% of Stop Distance`
5. `High-Impact Macro Event within ±30 Minutes`
6. `Asset under Active 2-Strike Lockout`
7. `Daily Loss Limit Exceeded`
