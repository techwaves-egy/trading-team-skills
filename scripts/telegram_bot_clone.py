#!/usr/bin/env python3
"""
AI Autonomous Trading Firm — Telegram Bot Console Clone & Live Streamer (v1.0.0)
Provides a complete 1:1 local mirror and execution clone of the Telegram mobile bot:
1. Real-Time Watch: Live-streams all commands sent from your phone and the bot's replies.
2. Conversation History: Displays the historical dialogue between Administrator @wtalaat and the bot.
3. Local Command Execution: Run any Telegram bot command directly in your console as a local clone.
4. Interactive Shell: An interactive prompt mirroring mobile button controls.

Usage:
    python scripts/telegram_bot_clone.py                    # Display recent Telegram conversation
    python scripts/telegram_bot_clone.py --watch             # Live stream incoming commands & bot replies
    python scripts/telegram_bot_clone.py /status             # Execute /status command locally
    python scripts/telegram_bot_clone.py /news XAUUSD        # Execute /news command locally
    python scripts/telegram_bot_clone.py /scan               # Execute /scan command locally
    python scripts/telegram_bot_clone.py /wizard             # Display /wizard menus locally
    python scripts/telegram_bot_clone.py --interactive       # Open interactive clone shell
"""

import sys
import os
import time
import json
import re
import argparse
from datetime import datetime, timezone

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.path.join(BASE_DIR, "scripts"))

LOGS_DIR = os.path.join(BASE_DIR, "logs")
MIRROR_LOG_PATH = os.path.join(LOGS_DIR, "telegram_bot_mirror.log")
MIRROR_JSONL_PATH = os.path.join(LOGS_DIR, "telegram_bot_mirror.jsonl")
CONFIG_PATH = os.path.join(BASE_DIR, "config", "alert_config.json")


def clean_html(raw_html):
    """Clean HTML tags for readable console formatting."""
    if not raw_html:
        return ""
    text = re.sub(r"<code>([^<]+)</code>", r"[\1]", raw_html)
    text = re.sub(r"<b>([^<]+)</b>", r"**\1**", text)
    text = re.sub(r"<i>([^<]+)</i>", r"_\1_", text)
    text = re.sub(r"<[^>]+>", "", text)
    return text.strip()


def display_recent_history(limit=10):
    """Display the last N messages from the Telegram conversation log."""
    print("\n" + "═" * 70)
    print("📱 TELEGRAM BOT REAL-TIME CONVERSATION CLONE (ADMIN <-> BOT)")
    print("═" * 70)

    if not os.path.exists(MIRROR_JSONL_PATH):
        print(f"No conversation history logged yet in {MIRROR_JSONL_PATH}.")
        print("Send a command on Telegram or run 'python scripts/telegram_bot_clone.py /status' to initiate.")
        print("═" * 70 + "\n")
        return

    events = []
    try:
        with open(MIRROR_JSONL_PATH, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        events.append(json.loads(line))
                    except Exception:
                        pass
    except Exception as e:
        print(f"Error reading conversation log: {e}")
        return

    if not events:
        print("Log is currently empty.")
        print("═" * 70 + "\n")
        return

    recent = events[-limit:]
    for ev in recent:
        ts = ev.get("timestamp", "N/A")
        direction = ev.get("direction", "BOT")
        user = ev.get("user_info", "")
        text = ev.get("text", "")
        buttons = ev.get("buttons")

        if direction == "USER":
            print(f"\n👤 [USER -> BOT] | {ts} {f'({user})' if user else ''}")
            print("─" * 70)
            print(f"  💬 {text}")
        else:
            print(f"\n🤖 [BOT -> USER] | {ts}")
            print("─" * 70)
            for line in text.split("\n"):
                print(f"  {line}")
            if buttons:
                print(f"  🔘 Buttons: {' | '.join(buttons[:6])}{'...' if len(buttons) > 6 else ''}")

    print("\n" + "═" * 70)
    print(f"Showing last {len(recent)} event(s). Use --watch to stream in real-time.")
    print("═" * 70 + "\n")


def watch_live_stream():
    """Live tail the conversation log in real-time as messages arrive."""
    print("\n" + "═" * 70)
    print("🟢 TELEGRAM BOT LIVE STREAM ACTIVE — Watching for mobile commands...")
    print("Press Ctrl+C to exit stream.")
    print("═" * 70 + "\n")

    os.makedirs(LOGS_DIR, exist_ok=True)
    if not os.path.exists(MIRROR_LOG_PATH):
        open(MIRROR_LOG_PATH, "a", encoding="utf-8").close()

    try:
        with open(MIRROR_LOG_PATH, "r", encoding="utf-8", errors="ignore") as f:
            # Go to end of file
            f.seek(0, os.SEEK_END)
            while True:
                line = f.readline()
                if line:
                    sys.stdout.write(line)
                    sys.stdout.flush()
                else:
                    time.sleep(0.5)
    except KeyboardInterrupt:
        print("\n[Stream Stopped]")


def execute_clone_command(cmd_str, dispatch_to_tg=False):
    """
    Execute a Telegram command locally using the exact listener logic,
    capturing the result and displaying it as a clone.
    """
    cmd_parts = cmd_str.strip().split()
    if not cmd_parts:
        print("No command provided.")
        return

    cmd = cmd_parts[0].lower()
    args = cmd_parts[1:]

    # Map aliases
    btn_map = {
        "status": "/status",
        "scan": "/scan",
        "news": "/news",
        "wizard": "/wizard",
        "summary": "/summary",
        "weekly": "/weekly",
        "integrity": "/integrity",
        "close": "/close",
        "stop": "/stop",
        "help": "/help"
    }
    if cmd in btn_map:
        cmd = btn_map[cmd]

    print("\n" + "═" * 70)
    print(f"⚡ RUNNING BOT CLONE COMMAND: {cmd} {' '.join(args)}")
    print("═" * 70)

    try:
        import telegram_listener as tl
        cfg = tl.load_config()
        tg_cfg = cfg.get("telegram", {})
        bot_token = tg_cfg.get("bot_token")
        chat_id = tg_cfg.get("admin_chat_id") or tg_cfg.get("chat_id")

        # Intercept messages locally
        captured_messages = []

        def capture_send(token, cid, text, reply_markup=None):
            captured_messages.append({"action": "SEND", "text": text, "buttons": tl.extract_buttons(reply_markup)})
            if dispatch_to_tg and token and cid:
                tl.tg_api_request(token, "sendMessage", {"chat_id": cid, "text": text, "parse_mode": "HTML", "reply_markup": reply_markup})

        def capture_edit(token, cid, mid, text, reply_markup=None):
            captured_messages.append({"action": "EDIT", "text": text, "buttons": tl.extract_buttons(reply_markup)})
            if dispatch_to_tg and token and cid:
                tl.tg_api_request(token, "editMessageText", {"chat_id": cid, "message_id": mid, "text": text, "parse_mode": "HTML", "reply_markup": reply_markup})

        orig_send = tl.send_tg_message
        orig_edit = tl.edit_tg_message
        tl.send_tg_message = capture_send
        tl.edit_tg_message = capture_edit

        # Execute target command
        if cmd == "/status":
            tl.handle_status_cmd(chat_id, bot_token)
        elif cmd == "/scan":
            tl.handle_scan_cmd(chat_id, bot_token)
        elif cmd in ("/wizard", "/start_session"):
            tl.handle_start_session_cmd(args if args else ["wizard"], chat_id, bot_token)
        elif cmd in ("/continuous", "/always_active"):
            m = "BOTH"
            b = "2"
            if len(args) >= 2:
                m = args[0]
                b = args[1]
            elif len(args) == 1:
                if args[0].upper() in ("GOLD", "FOREX", "BOTH", "EURUSD", "XAUUSD"):
                    m = args[0]
                    b = "2"
                else:
                    m = "BOTH"
                    b = args[0]
            tl.handle_start_session_cmd([m, b, "allweek"], chat_id, bot_token)
        elif cmd == "/news":
            from news_analyzer import get_analyzer
            analyzer = get_analyzer()
            sym = args[0] if args else "XAUUSD"
            report = analyzer.format_telegram_advisory(sym)
            capture_send(bot_token, chat_id, report, tl.make_main_keyboard())
        elif cmd == "/summary":
            from daily_summary import send_daily_summary
            summary = send_daily_summary(admin_only=True)
            capture_send(bot_token, chat_id, f"📈 Daily Summary Generated: Net P&L: ${summary['net_pnl']:.2f}")
        elif cmd == "/weekly":
            from daily_summary import send_market_close_summary
            send_market_close_summary(is_weekend=True, kill_processes=False, admin_only=True)
        elif cmd == "/integrity":
            tl.handle_integrity_cmd(chat_id, bot_token)
        elif cmd == "/close":
            tl.handle_close_cmd(chat_id, bot_token)
        elif cmd == "/stop":
            tl.handle_stop_cmd(chat_id, bot_token)
        elif cmd in ("/help", "/menu"):
            tl.handle_help_cmd(chat_id, bot_token)
        elif cmd in ("/buy", "/sell"):
            order_type = "BUY" if cmd == "/buy" else "SELL"
            tl.handle_direct_trade_cmd(order_type, args, chat_id, bot_token)
        else:
            capture_send(bot_token, chat_id, f"❓ Unknown command: {cmd}\nSend /help to view all available commands.")

        # Restore original functions
        tl.send_tg_message = orig_send
        tl.edit_tg_message = orig_edit

        # Print captured output
        if captured_messages:
            for msg in captured_messages:
                clean = clean_html(msg["text"])
                print(f"\n🤖 [BOT CLONE RESPONSE]:")
                print("─" * 70)
                print(clean)
                if msg.get("buttons"):
                    print("─" * 70)
                    print(f"🔘 Interactive Buttons: {' | '.join(msg['buttons'][:6])}{'...' if len(msg['buttons']) > 6 else ''}")
        else:
            print("[Command executed with no direct output message]")

        print("\n" + "═" * 70)
        if dispatch_to_tg:
            print("✅ Also dispatched live to Telegram chat.")
        else:
            print("💡 Local clone simulation only. Use --send to also dispatch to Telegram.")
        print("═" * 70 + "\n")

    except Exception as e:
        print(f"Error executing clone command: {e}")
        import traceback
        traceback.print_exc()


def interactive_shell():
    """Interactive command-line shell mirroring the Telegram Bot."""
    print("\n" + "═" * 70)
    print("🤖 TELEGRAM BOT INTERACTIVE CONSOLE CLONE")
    print("Type any Telegram command (e.g. /status, /news, /scan, /help, exit)")
    print("═" * 70 + "\n")

    while True:
        try:
            user_input = input("📱 [Telegram-Clone] > ").strip()
            if not user_input:
                continue
            if user_input.lower() in ("exit", "quit", "q"):
                print("Exiting clone shell.")
                break
            execute_clone_command(user_input, dispatch_to_tg=False)
        except (KeyboardInterrupt, EOFError):
            print("\nExiting clone shell.")
            break


def main():
    parser = argparse.ArgumentParser(description="Telegram Bot Local Clone & Real-Time Streamer")
    parser.add_argument("command", nargs="*", help="Command to execute (e.g. /status, /news, /scan)")
    parser.add_argument("--watch", "-w", action="store_true", help="Live stream incoming commands & bot replies")
    parser.add_argument("--history", "-H", type=int, default=10, help="Number of historical events to display")
    parser.add_argument("--interactive", "-i", action="store_true", help="Launch interactive bot clone shell")
    parser.add_argument("--send", "-s", action="store_true", help="Also dispatch local clone command to Telegram")

    args = parser.parse_args()

    if args.watch:
        watch_live_stream()
    elif args.interactive:
        interactive_shell()
    elif args.command:
        full_cmd = " ".join(args.command)
        execute_clone_command(full_cmd, dispatch_to_tg=args.send)
    else:
        display_recent_history(limit=args.history)


if __name__ == "__main__":
    main()
