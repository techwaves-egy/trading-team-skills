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
    args = sys.argv[1:]
    market = "BOTH"
    batch = 2
    rounds = 2

    if len(args) >= 3:
        market = args[0]
        batch = args[1]
        rounds = args[2]
    elif len(args) == 2:
        if args[0].upper() in ("GOLD", "FOREX", "BOTH", "EURUSD", "XAUUSD"):
            market = args[0]
            batch = args[1]
            rounds = 2
        else:
            market = "BOTH"
            batch = args[0]
            rounds = args[1]
    elif len(args) == 1:
        if args[0].upper() in ("GOLD", "FOREX", "BOTH", "EURUSD", "XAUUSD"):
            market = args[0]
            batch = 2
            rounds = 2
        else:
            market = "BOTH"
            batch = args[0]
            rounds = 1

    session = start_trading_session(market, batch, rounds)
    config = load_config()
    tg = config.get("telegram", {})
    bot_token = tg.get("bot_token")
    chats = tg.get("chat_ids", ["1264076025", "-1003989306390"])
    if tg.get("chat_id") and tg["chat_id"] not in chats:
        chats.append(tg["chat_id"])

    target_dollars = float(session.get("target_profit_per_trade", 25.0))
    batch_size = session.get("concurrent_batch_size", 1)
    daily_rounds = session.get("daily_rounds", 1)
    batch_goal = float(session.get("batch_profit_goal", 50.0))
    daily_goal = float(session.get("session_profit_goal", 100.0))
    total_trades = session.get("max_trades", 2)
    market_label = session.get("active_market", "EURUSD, XAUUSD")

    msg = (
        f"🚀 <b>AUTONOMOUS TRADING SESSION LAUNCHED</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🆔 <b>Session ID:</b> <code>{session['session_id']}</code>\n"
        f"🌐 <b>Active Market:</b> <b>{market_label}</b>\n"
        f"⚡ <b>Batch Concurrency:</b> <b>{batch_size}x Simultaneous Orders</b> (0.01L each)\n"
        f"🎯 <b>Daily Execution:</b> <b>{daily_rounds} Round{'s' if daily_rounds > 1 else ''} Daily</b> ({total_trades} Total Trades)\n"
        f"💰 <b>Target Profit / Trade:</b> <code>+${target_dollars:.2f}</code>\n"
        f"🏆 <b>Batch Target / Round:</b> <b>+${batch_goal:.2f} USD</b>\n"
        f"🌟 <b>Total Daily Goal:</b> <b>+${daily_goal:.2f} USD</b>\n"
        f"🛡️ <b>80/70 Protection:</b> Arms @ <code>+${target_dollars * 0.80:.2f}</code> | Floor @ <code>+${target_dollars * 0.70:.2f}</code> per trade\n"
        f"🛡️ <b>CRO Safety Score:</b> <b>{session.get('margin_stress_score')}</b>\n"
        f"🤖 <b>Active Daemons:</b> Scanner, Trade Monitor &amp; Daily Auditor Online\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"<i>Autonomous scanner is actively monitoring markets for Round 1 setup...</i>"
    )

    for c in chats:
        send_tg_message(bot_token, c, msg, make_main_keyboard())

    print(f"Session {session['session_id']} successfully started: {market_label} | {batch_size}x concurrency | {daily_rounds} rounds ({total_trades} trades total) @ ${target_dollars}/trade (Daily Goal: ${daily_goal}).")

if __name__ == "__main__":
    main()
