#!/usr/bin/env python3
"""
CLI helper to launch an autonomous trading session.
Usage: python scripts/start_session.py [max_trades] [leverage_tier] [quota]
"""
import sys
import os
import json
from datetime import datetime, timezone

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.path.join(BASE_DIR, "scripts"))

from telegram_listener import start_trading_session, load_config, send_tg_message, make_main_keyboard

def main():
    max_trades = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 5
    leverage = sys.argv[2] if len(sys.argv) > 2 else "2x"
    quota = int(sys.argv[3]) if len(sys.argv) > 3 and sys.argv[3].isdigit() else max_trades

    session = start_trading_session(max_trades, leverage, quota)
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
        f"🎯 <b>Total Allowed Trades:</b> <b>{session['max_trades']} Trades</b>\n"
        f"⚡ <b>Leverage Tier:</b> <b>{session['approved_leverage_tier']}</b> ({0.01 * session['leverage_multiplier']:.2f} lots)\n"
        f"⏳ <b>Leverage Duration:</b> <b>{session['leverage_trades_quota']} trades</b>\n"
        f"🏆 <b>Strategy:</b> Bollinger Bands 2.0 Mean Reversion\n"
        f"💰 <b>Gold Profit Target:</b> <code>+${gold_target:.2f} / trade</code>\n"
        f"🛡️ <b>CRO Risk Clearance:</b> ✅ APPROVED\n"
        f"🤖 <b>Daemons:</b> Scanner & Real-Time Deal Streamer Active\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"<i>Live scanning is actively monitoring EURUSD & Gold...</i>"
    )

    for c in chats:
        send_tg_message(bot_token, c, msg, make_main_keyboard())

    print(f"Session {session['session_id']} successfully started: {max_trades} trades @ {session['approved_leverage_tier']} leverage.")

if __name__ == "__main__":
    main()
