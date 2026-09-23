# Multi-Channel Mobile Trade Notifications (Telegram & Discord)

The AI Autonomous Trading Firm includes automated notification bridges to dispatch real-time trade signals, **step-by-step Take Profit (TP1/TP2) milestone action instructions**, Stop Loss alerts, and risk notices directly to your mobile device via **Telegram** and **Discord**.

---

## 1. Real-Time Milestone Action Messages

When you are executing trades manually or managing open positions from your phone, the firm sends real-time action alerts so you never have to guess what to do:

### 🎯 Take Profit 1 (TP1) Reached Alert
```text
🎯 TAKE PROFIT 1 (TP1) REACHED! — XAUUSD (Gold)
━━━━━━━━━━━━━━━━━━━━━━━━━━
Status:      🟢 MILESTONE 1 ACHIEVED (+1.5R GAIN)
Hit Price:   $4,662.00

👉 ACTION TO TAKE ON YOUR BROKER NOW:
1. Close 40% Volume: Close 0.44 Lots at market.
2. Move Stop Loss:   Modify SL to $4,648.50 (BREAK-EVEN / RISK-FREE).

🔒 Guaranteed Outcome: Trade can no longer result in a loss.
🎯 Next Target:        TP2 @ $4,671.00
━━━━━━━━━━━━━━━━━━━━━━━━━━
```

### 🎯🎯 Take Profit 2 (TP2) Reached Alert
```text
🎯🎯 TAKE PROFIT 2 (TP2) REACHED! — XAUUSD (Gold)
━━━━━━━━━━━━━━━━━━━━━━━━━━
Status:      🟢 MILESTONE 2 ACHIEVED (+2.5R GAIN)
Hit Price:   $4,671.00

👉 ACTION TO TAKE ON YOUR BROKER NOW:
1. Close 40% Volume: Close another 0.44 Lots at market.
2. Lock In Profit:   Move Stop Loss up to $4,662.00 (LOCK +1.5R PROFIT).
3. Let Runner Ride:  Keep remaining 20% on trailing stop targeting $4,685.00.

💰 Banked: 80% total position profits secured.
━━━━━━━━━━━━━━━━━━━━━━━━━━
```

### 🛑 Stop Loss (SL) Hit Alert
```text
🛑 STOP LOSS HIT — BTCUSDT (Bitcoin)
━━━━━━━━━━━━━━━━━━━━━━━━━━
Status:         🔴 POSITION CLOSED AT INVALIDATION
Exit Price:     $78,450.00
Realized Loss:  -$100.00 (Pre-calculated bounded risk)

👉 ACTION TO TAKE ON YOUR BROKER NOW:
1. Verify Position Closed: Confirm position is 100% closed on your broker.
2. Purge Pending Orders:   Ensure any attached TP/SL limits are cancelled.

⏳ Cool-Down Protocol Activated:
• Mandatory 30-minute scanning pause on BTCUSDT.
• Capital preservation rules enforced.
━━━━━━━━━━━━━━━━━━━━━━━━━━
```

---

## 2. Automated Multi-Destination Broadcast

The dispatcher broadcasts simultaneously to all configured Chat IDs in [`config/alert_config.json`](file:///d:/Techwaves-egy/Trading%20Team%20Skills/config/alert_config.json):
* **VIP Channels & Supergroups** (e.g. `-1003989306390`)
* **Personal Direct Chats** (e.g. `2226998`)

---

## 3. Testing Milestone & Action Alerts

To test how milestone action messages appear on your phone:

```bash
# Test initial trade candidate alert with approval buttons
python scripts/send_alert.py --test

# Test Take Profit 1 (TP1) Manual Action Alert
python scripts/send_alert.py --test-tp1

# Test Stop Loss (SL) Invalidation Alert
python scripts/send_alert.py --test-sl
```
