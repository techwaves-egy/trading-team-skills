# Template: Real-Time TP & SL Manual Action Alerts

These structured alerts are dispatched automatically to Telegram and Desktop Chat when an open position reaches milestone profit targets or stop loss invalidation levels.

---

### 🎯 Take Profit 1 (TP1) Manual Action Template

```text
🎯 TAKE PROFIT 1 (TP1) REACHED! — [INSTRUMENT]
━━━━━━━━━━━━━━━━━━━━━━━━━━
Status:      🟢 MILESTONE 1 ACHIEVED (+1.5R GAIN)
Hit Price:   $[PRICE]

👉 ACTION TO TAKE ON YOUR BROKER NOW:
1. Close 40% Volume: Close [XX Lots / Units] at market.
2. Move Stop Loss:   Modify SL to $[ENTRY_PRICE] (BREAK-EVEN / RISK-FREE).

🔒 Guaranteed Outcome: Trade can no longer result in a loss.
🎯 Next Target:        TP2 @ $[TP2_PRICE]
━━━━━━━━━━━━━━━━━━━━━━━━━━
```

---

### 🎯🎯 Take Profit 2 (TP2) Manual Action Template

```text
🎯🎯 TAKE PROFIT 2 (TP2) REACHED! — [INSTRUMENT]
━━━━━━━━━━━━━━━━━━━━━━━━━━
Status:      🟢 MILESTONE 2 ACHIEVED (+2.5R GAIN)
Hit Price:   $[PRICE]

👉 ACTION TO TAKE ON YOUR BROKER NOW:
1. Close 40% Volume: Close another [XX Lots / Units] at market.
2. Lock In Profit:   Move Stop Loss up to $[TP1_PRICE] (LOCK +1.5R PROFIT).
3. Let Runner Ride:  Keep remaining 20% on trailing stop targeting $[RUNNER_PRICE].

💰 Banked: 80% total position profits secured.
━━━━━━━━━━━━━━━━━━━━━━━━━━
```

---

### 🛑 Stop Loss (SL) Invalidation Template

```text
🛑 STOP LOSS HIT — [INSTRUMENT]
━━━━━━━━━━━━━━━━━━━━━━━━━━
Status:         🔴 POSITION CLOSED AT INVALIDATION
Exit Price:     $[PRICE]
Realized Loss:  -$[RISK_DOLLARS] (Pre-calculated bounded risk)

👉 ACTION TO TAKE ON YOUR BROKER NOW:
1. Verify Position Closed: Confirm position is 100% closed on your broker.
2. Purge Pending Orders:   Ensure any attached TP/SL limits are cancelled.

⏳ Cool-Down Protocol Activated:
• Mandatory 30-minute scanning pause on [INSTRUMENT].
• Capital preservation rules enforced.
━━━━━━━━━━━━━━━━━━━━━━━━━━
```
