#!/usr/bin/env python3
"""
CLI helper to launch an autonomous trading session with Sequential Multi-Trade Architecture.
Usage: python scripts/start_session.py [tier_or_rounds] (e.g. 1x, 2x, 3x, 5x or 2)
"""
import sys
import os
import json
from datetime import datetime, timezone

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.path.join(BASE_DIR, "scripts"))

from telegram_listener import start_trading_session, load_config, send_tg_message, make_main_keyboard

def main():
    tier = sys.argv[1] if len(sys.argv) > 1 else "2x"
    quota = int(sys.argv[2]) if len(sys.argv) > 2 and sys.argv[2].isdigit() else None

    session = start_trading_session(tier, quota_trades=quota)
    config = load_config()
    tg = config.get("telegram", {})
    bot_token = tg.get("bot_token")
    chats = tg.get("chat_ids", ["1264076025", "-1003989306390"])
    if tg.get("chat_id") and tg["chat_id"] not in chats:
        chats.append(tg["chat_id"])

    target_dollars = float(session.get("target_profit_per_trade", 25.0))
    session_goal = float(session.get("session_profit_goal", 50.0))
    rounds = session.get("max_trades", 2)
    tier_name = session.get("approved_leverage_tier", "2x")

    msg = (
        f"🚀 <b>AUTONOMOUS TRADING SESSION LAUNCHED</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🆔 <b>Session ID:</b> <code>{session['session_id']}</code>\n"
        f"🎯 <b>Sequential Target:</b> <b>{tier_name} Tier ({rounds} Trade{'s' if rounds > 1 else ''})</b>\n"
        f"💰 <b>Profit Target / Trade:</b> <code>+${target_dollars:.2f}</code> (Fixed per round)\n"
        f"🛡️ <b>80/70 Protection:</b> Arms @ <code>+${target_dollars * 0.80:.2f}</code> | Floor @ <code>+${target_dollars * 0.70:.2f}</code>\n"
        f"🏆 <b>Total Session Goal:</b> <b>+${session_goal:.2f} USD</b>\n"
        f"📦 <b>Position Size:</b> <code>{session.get('default_lots', 0.01)} lot</code> (Strict Anti-Stacking)\n"
        f"⚡ <b>Strategy:</b> Bollinger Bands 2.0 Mean Reversion\n"
        f"🛡️ <b>CRO Risk Clearance:</b> ✅ APPROVED\n"
        f"🤖 <b>Daemons:</b> Scanner & Real-Time Deal Streamer Active\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"<i>Autonomous scanner is actively monitoring markets for Round 1 setup...</i>"
    )

    for c in chats:
        send_tg_message(bot_token, c, msg, make_main_keyboard())

    print(f"Session {session['session_id']} successfully started: {rounds} sequential trades ({tier_name}) @ ${target_dollars}/trade (Goal: ${session_goal}).")

if __name__ == "__main__":
    main()
