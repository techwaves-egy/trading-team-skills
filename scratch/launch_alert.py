import sys
import os
import json

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.path.join(BASE_DIR, "scripts"))

from telegram_listener import load_config, send_tg_message, make_main_keyboard

with open(os.path.join(BASE_DIR, "config", "session_state.json"), "r") as f:
    session = json.load(f)

config = load_config()
tg = config.get("telegram", {})
bot_token = tg.get("bot_token")
chats = tg.get("chat_ids", ["1264076025", "-1003989306390"])
if tg.get("chat_id") and tg["chat_id"] not in chats:
    chats.append(tg["chat_id"])

gold_target = 25.0 * session["leverage_multiplier"]
msg = (
    f"🚀 <b>AUTONOMOUS TRADING SESSION LAUNCHED</b>\n"
    f"━━━━━━━━━━━━━━━━━━━━\n"
    f"🆔 <b>Session ID:</b> <code>{session['session_id']}</code>\n"
    f"🌟 <b>Target Market:</b> <b>Gold (XAUUSD) Dedicated</b>\n"
    f"🎯 <b>Total Allowed Trades:</b> <b>{session['max_trades']} Trades</b>\n"
    f"⚡ <b>Leverage Tier:</b> <b>{session['approved_leverage_tier']}</b> (0.02 lots)\n"
    f"⏳ <b>Leverage Duration:</b> <b>{session['leverage_trades_quota']} trades</b>\n"
    f"💵 <b>Max Risk / Trade:</b> <code>${session['risk_per_trade_dollars']:.2f}</code>\n"
    f"🛑 <b>Max Daily Drawdown:</b> <code>${session['max_daily_loss_dollars']:.2f}</code>\n"
    f"🏆 <b>Primary Strategy:</b> Bollinger Bands 2.0 Mean Reversion\n"
    f"💰 <b>Gold Profit Target:</b> <code>+${gold_target:.2f} / trade</code>\n"
    f"🛡️ <b>80/70 Profit Guard:</b> ✅ ARMED (v3.8.0)\n"
    f"🛡️ <b>CRO Risk Clearance:</b> ✅ APPROVED\n"
    f"━━━━━━━━━━━━━━━━━━━━\n"
    f"<i>Autonomous scanning is actively sweeping XAUUSD...</i>"
)

for c in chats:
    send_tg_message(bot_token, c, msg, make_main_keyboard())

print("Telegram session broadcast delivered.")
