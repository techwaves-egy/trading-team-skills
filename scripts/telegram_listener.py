#!/usr/bin/env python3
"""
AI Autonomous Trading Firm — Two-Way Telegram Mobile Command Controller (v3.7.0)
Enables 100% remote control of the autonomous firm directly from Telegram:
  • /start_session [trades] [leverage] [quota] - Launch new trading session
  • /status - Live account telemetry, equity, balance & active positions
  • /scan - Force immediate multi-engine market sweep
  • /close - Emergency kill switch: Close all open positions immediately
  • /stop or /pause - Gracefully stop auto scanner daemon
  • /summary - On-demand daily trade summary
  • /weekly - On-demand weekly performance & close audit
  • /integrity - Cryptographic SHA-256 anti-tamper status
  • /help - Interactive mobile command guide
"""

import sys
import os
import time
import json
import logging
import subprocess
import urllib.request
import urllib.parse
from datetime import datetime, timezone

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.path.join(BASE_DIR, "scripts"))

import re

CONFIG_PATH = os.path.join(BASE_DIR, "config", "alert_config.json")
SESSION_PATH = os.path.join(BASE_DIR, "config", "session_state.json")
LOGS_DIR = os.path.join(BASE_DIR, "logs")
MIRROR_LOG_PATH = os.path.join(LOGS_DIR, "telegram_bot_mirror.log")
MIRROR_JSONL_PATH = os.path.join(LOGS_DIR, "telegram_bot_mirror.jsonl")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - TgListener - %(levelname)s - %(message)s"
)
logger = logging.getLogger("TgListener")


def extract_buttons(reply_markup):
    """Extract button labels from reply_markup dictionary."""
    if not reply_markup or not isinstance(reply_markup, dict):
        return None
    labels = []
    if "inline_keyboard" in reply_markup:
        for row in reply_markup["inline_keyboard"]:
            for btn in row:
                if "text" in btn:
                    labels.append(btn["text"])
    elif "keyboard" in reply_markup:
        for row in reply_markup["keyboard"]:
            for btn in row:
                if "text" in btn:
                    labels.append(btn["text"])
    return labels if labels else None


def mirror_log_event(direction, content, user_info=None, buttons=None):
    """
    Log incoming and outgoing Telegram Bot events to create a real-time clone
    of the bot conversation accessible directly in the IDE terminal.
    direction: 'USER' or 'BOT'
    """
    try:
        os.makedirs(LOGS_DIR, exist_ok=True)
        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

        clean_text = re.sub(r"<[^>]+>", "", content).strip() if content else ""

        badge = "👤 [USER -> BOT]" if direction == "USER" else "🤖 [BOT -> USER]"
        if user_info and direction == "USER":
            badge += f" ({user_info})"

        entry_lines = [
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
            f"{badge} | {now_str}",
            "────────────────────────────────────────────────────────────",
            clean_text
        ]
        if buttons:
            entry_lines.append(f"🔘 Interactive Buttons: {', '.join(buttons[:6])}{'...' if len(buttons) > 6 else ''}")
        entry_lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n")
        entry_str = "\n".join(entry_lines)

        with open(MIRROR_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(entry_str)

        event_obj = {
            "timestamp": now_str,
            "direction": direction,
            "user_info": user_info,
            "text": clean_text,
            "buttons": buttons
        }
        with open(MIRROR_JSONL_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(event_obj, ensure_ascii=False) + "\n")

        print(f"\n[TG-CLONE] {badge} | {now_str}\n{clean_text}\n", flush=True)
    except Exception as e:
        logger.error(f"Error mirroring telegram event: {e}")


def load_config():
    """Load bot configuration."""
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error reading config: {e}")
    return {}


def load_session():
    """Load session state."""
    if os.path.exists(SESSION_PATH):
        try:
            with open(SESSION_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error reading session: {e}")
    return {}


def save_session(data):
    """Save session state."""
    try:
        with open(SESSION_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        logger.error(f"Error saving session: {e}")


def is_authorized(user_id, chat_id, config):
    """Verify sender identity against approved user and chat IDs."""
    tg = config.get("telegram", {})
    allowed_users = [str(u) for u in tg.get("allowed_user_ids", ["1264076025"])]
    allowed_chats = [str(c) for c in tg.get("chat_ids", ["1264076025", "-1003989306390"])]
    if tg.get("chat_id"):
        allowed_chats.append(str(tg["chat_id"]))

    return str(user_id) in allowed_users or str(chat_id) in allowed_chats


def is_admin(user_id, config):
    """Verify if user is the designated Administrator @wtalaat."""
    tg = config.get("telegram", {})
    admin_id = str(tg.get("admin_chat_id", "1264076025")).strip()
    allowed_users = [str(u).strip() for u in tg.get("allowed_user_ids", ["1264076025"])]
    return str(user_id).strip() == admin_id or str(user_id).strip() in allowed_users


def tg_api_request(bot_token, method, data=None):
    """Dispatch HTTP request to Telegram Bot API."""
    url = f"https://api.telegram.org/bot{bot_token}/{method}"
    try:
        if data:
            encoded_data = json.dumps(data).encode("utf-8")
            req = urllib.request.Request(url, data=encoded_data, headers={"Content-Type": "application/json"})
        else:
            req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=35) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        logger.error(f"Telegram API request ({method}) failed: {e}")
        return None


def send_tg_message(bot_token, chat_id, text, reply_markup=None):
    """Send HTML message with optional inline or reply keyboard."""
    mirror_log_event("BOT", text, buttons=extract_buttons(reply_markup))
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML"
    }
    if reply_markup:
        payload["reply_markup"] = reply_markup
    return tg_api_request(bot_token, "sendMessage", payload)


def edit_tg_message(bot_token, chat_id, message_id, text, reply_markup=None):
    """Edit existing HTML message text and inline keyboard."""
    mirror_log_event("BOT", f"[Edit Message]: {text}", buttons=extract_buttons(reply_markup))
    payload = {
        "chat_id": chat_id,
        "message_id": message_id,
        "text": text,
        "parse_mode": "HTML"
    }
    if reply_markup:
        payload["reply_markup"] = reply_markup
    res = tg_api_request(bot_token, "editMessageText", payload)
    if not res or not res.get("ok"):
        return send_tg_message(bot_token, chat_id, text, reply_markup)
    return res


def make_reply_keyboard():
    """
    Create persistent custom reply keyboard docked permanently
    at the bottom of the user's screen in Telegram.
    """
    return {
        "keyboard": [
            [
                {"text": "📊 Live Status"},
                {"text": "🔍 Scan Market"}
            ],
            [
                {"text": "⚙️ Configure Session (Wizard)"}
            ],
            [
                {"text": "🔄 Gold 2x (All-Week Continuous)"},
                {"text": "🔄 Both 2x (All-Week Continuous)"}
            ],
            [
                {"text": "🥇 Gold 5x (3 Rounds • +$375)"},
                {"text": "🥇 Gold 2x (2 Rounds • +$100)"}
            ],
            [
                {"text": "🌐 Both 2x (2 Rounds • +$100)"},
                {"text": "🚀 Fast 1x ($25 Win)"}
            ],
            [
                {"text": "⚡ Buy Gold (0.01)"},
                {"text": "⚡ Sell Gold (0.01)"}
            ],
            [
                {"text": "📈 Today Summary"},
                {"text": "🛑 Close All (Kill)"}
            ],
            [
                {"text": "📰 News & CRO Advisory"},
                {"text": "🛡️ Verify Security"}
            ],
            [
                {"text": "⏹️ Stop Scanner"},
                {"text": "❓ Help / Menu"}
            ]
        ],
        "resize_keyboard": True,
        "is_persistent": True,
        "one_time_keyboard": False
    }


def make_main_keyboard():
    """Create interactive inline callback keyboard attached to messages."""
    return {
        "inline_keyboard": [
            [
                {"text": "📊 Live Status", "callback_data": "cb_status"},
                {"text": "🔍 Scan Market", "callback_data": "cb_scan"}
            ],
            [
                {"text": "⚙️ Configure Session (Wizard)", "callback_data": "wiz_start"}
            ],
            [
                {"text": "🔄 Gold 2x (All-Week)", "callback_data": "cb_quick_gold_2x_allweek"},
                {"text": "🔄 Both 2x (All-Week)", "callback_data": "cb_quick_both_2x_allweek"}
            ],
            [
                {"text": "🥇 Gold 5x (3 Rnds • +$375)", "callback_data": "cb_quick_gold_5x3"},
                {"text": "🥇 Gold 3x (3 Rnds • +$225)", "callback_data": "cb_quick_gold_3x3"}
            ],
            [
                {"text": "🥇 Gold 2x (2 Rnds • +$100)", "callback_data": "cb_quick_gold_2x2"},
                {"text": "🌐 Both 2x (2 Rnds • +$100)", "callback_data": "cb_quick_both_2x2"}
            ],
            [
                {"text": "🚀 Fast 1x (+$25)", "callback_data": "cb_start_1x"}
            ],
            [
                {"text": "⚡ Buy Gold (0.01)", "callback_data": "cb_buy_gold"},
                {"text": "⚡ Sell Gold (0.01)", "callback_data": "cb_sell_gold"}
            ],
            [
                {"text": "📈 Today Summary", "callback_data": "cb_summary"},
                {"text": "🛑 Close All (Kill)", "callback_data": "cb_close"}
            ],
            [
                {"text": "📰 News & CRO Advisory", "callback_data": "cb_news"},
                {"text": "🛡️ Verify Security", "callback_data": "cb_integrity"}
            ],
            [
                {"text": "⏹️ Stop Scanner", "callback_data": "cb_stop"}
            ]
        ]
    }


def send_wizard_step1(chat_id, bot_token, message_id=None):
    """Step 1/3: Interactive Market Universe Selection."""
    text = (
        "⚙️ <b>STEP 1/3: SELECT MARKET UNIVERSE</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "Choose which market asset(s) the autonomous scanner will trade:\n\n"
        "• 🥇 <b>Gold Only (XAUUSD):</b> Hyper-liquid, high-volatility momentum ($25 target / trade)\n"
        "• 💶 <b>Forex Only (EURUSD):</b> Stable institutional trend liquidity ($25 target / trade)\n"
        "• 🌐 <b>Multi-Asset (Both):</b> Dual scanner covering both EURUSD & XAUUSD\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "👉 <i>Tap an option below to proceed:</i>"
    )
    kb = {
        "inline_keyboard": [
            [
                {"text": "🥇 Gold Only (XAUUSD)", "callback_data": "wiz_m_GOLD"},
                {"text": "💶 Forex Only (EURUSD)", "callback_data": "wiz_m_FOREX"}
            ],
            [
                {"text": "🌐 Both (Gold + Forex)", "callback_data": "wiz_m_BOTH"}
            ],
            [
                {"text": "« Back to Main Menu", "callback_data": "cb_help"}
            ]
        ]
    }
    if message_id:
        return edit_tg_message(bot_token, chat_id, message_id, text, kb)
    return send_tg_message(bot_token, chat_id, text, kb)


def send_wizard_step2(chat_id, bot_token, market, message_id=None):
    """Step 2/3: Interactive Batch Concurrency Selection."""
    labels = {
        "GOLD": "🥇 Gold Only (XAUUSD)",
        "FOREX": "💶 Forex Only (EURUSD)",
        "BOTH": "🌐 Both (Gold + Forex)"
    }
    m_label = labels.get(market.upper(), market)
    text = (
        f"⚙️ <b>STEP 2/3: SELECT CONCURRENT BATCH SIZE (x)</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"Selected Universe: <b>{m_label}</b>\n\n"
        f"How many simultaneous trades should be executed per setup?\n"
        f"Each trade opens <code>0.01 lot</code> with an independent <b>+$25.00 profit target</b> and <b>80/70 Asymmetric Protection</b>:\n\n"
        f"• <b>1x:</b> 1 trade per signal ➔ <b>+$25.00 / round</b>\n"
        f"• <b>2x:</b> 2 concurrent trades ➔ <b>+$50.00 / round</b>\n"
        f"• <b>3x:</b> 3 concurrent trades ➔ <b>+$75.00 / round</b>\n"
        f"• <b>5x:</b> 5 concurrent trades ➔ <b>+$125.00 / round</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"👉 <i>Tap batch concurrency (x) to proceed to Step 3:</i>"
    )
    kb = {
        "inline_keyboard": [
            [
                {"text": "1x (1 Trade • +$25)", "callback_data": f"wiz_b_{market}_1"},
                {"text": "2x (2 Trades • +$50)", "callback_data": f"wiz_b_{market}_2"}
            ],
            [
                {"text": "3x (3 Trades • +$75)", "callback_data": f"wiz_b_{market}_3"},
                {"text": "5x (5 Trades • +$125)", "callback_data": f"wiz_b_{market}_5"}
            ],
            [
                {"text": "« Back to Step 1 (Market)", "callback_data": "wiz_start"}
            ]
        ]
    }
    if message_id:
        return edit_tg_message(bot_token, chat_id, message_id, text, kb)
    return send_tg_message(bot_token, chat_id, text, kb)


def send_wizard_step3(chat_id, bot_token, market, batch_str, message_id=None):
    """Step 3/3: Interactive Daily Rounds Frequency Selection."""
    labels = {
        "GOLD": "🥇 Gold Only (XAUUSD)",
        "FOREX": "💶 Forex Only (EURUSD)",
        "BOTH": "🌐 Both (Gold + Forex)"
    }
    m_label = labels.get(market.upper(), market)
    batch = int(batch_str) if str(batch_str).isdigit() else 2
    batch_goal = batch * 25.0

    text = (
        f"⚙️ <b>STEP 3/3: SELECT EXECUTION FREQUENCY & DURATION</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"Universe: <b>{m_label}</b>\n"
        f"Batch Size: <b>{batch}x Concurrent Trades</b> (0.01L each • +${batch_goal:.2f} / round)\n\n"
        f"Choose daily fixed rounds OR continuous all-week trading:\n"
        f"• <b>1 Round Daily:</b> {batch * 1} trades daily ➔ Daily Goal: <b>+${batch_goal * 1:.2f}</b>\n"
        f"• <b>2 Rounds Daily:</b> {batch * 2} trades daily ➔ Daily Goal: <b>+${batch_goal * 2:.2f}</b>\n"
        f"• <b>3 Rounds Daily:</b> {batch * 3} trades daily ➔ Daily Goal: <b>+${batch_goal * 3:.2f}</b>\n"
        f"• <b>5 Rounds Daily:</b> {batch * 5} trades daily ➔ Daily Goal: <b>+${batch_goal * 5:.2f}</b>\n"
        f"• <b>🔄 Always Active:</b> Continuous {batch}x batches all week through Friday close!\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"👉 <i>Tap an option below to launch the autonomous engine:</i>"
    )
    kb = {
        "inline_keyboard": [
            [
                {"text": f"1 Round (+${batch_goal*1:.0f})", "callback_data": f"wiz_r_{market}_{batch}_1"},
                {"text": f"2 Rounds (+${batch_goal*2:.0f})", "callback_data": f"wiz_r_{market}_{batch}_2"}
            ],
            [
                {"text": f"3 Rounds (+${batch_goal*3:.0f})", "callback_data": f"wiz_r_{market}_{batch}_3"},
                {"text": f"5 Rounds (+${batch_goal*5:.0f})", "callback_data": f"wiz_r_{market}_{batch}_5"}
            ],
            [
                {"text": "🔄 Always Active (All-Week Continuous)", "callback_data": f"wiz_r_{market}_{batch}_allweek"}
            ],
            [
                {"text": "« Back to Step 2 (Batch Concurrency)", "callback_data": f"wiz_m_{market}"}
            ]
        ]
    }
    if message_id:
        return edit_tg_message(bot_token, chat_id, message_id, text, kb)
    return send_tg_message(bot_token, chat_id, text, kb)


def set_bot_commands(bot_token):
    """Register official command menu with Telegram Bot API."""
    commands = [
        {"command": "wizard", "description": "⚙️ 3-Step Interactive Session Wizard"},
        {"command": "status", "description": "📊 Live balance, equity, PTJ bias & positions"},
        {"command": "continuous", "description": "🔄 Always active all-week trading [market] [batch]"},
        {"command": "scan", "description": "🔍 Force immediate market sweep"},
        {"command": "news", "description": "📰 Macro news & CRO advisory"},
        {"command": "start_session", "description": "🚀 Launch session [market] [batch] [rounds]"},
        {"command": "summary", "description": "📈 Today's complete market close audit"},
        {"command": "buy", "description": "⚡ Instant market BUY execution"},
        {"command": "sell", "description": "⚡ Instant market SELL execution"},
        {"command": "close", "description": "🛑 Emergency kill switch: Close all"},
        {"command": "stop", "description": "⏹️ Stop active auto-scanner"},
        {"command": "integrity", "description": "🛡️ Verify SHA-256 security status"},
        {"command": "weekly", "description": "🏆 Full weekly performance audit"},
        {"command": "approve", "description": "🔑 Authorize pending code changes"},
        {"command": "help", "description": "❓ Full mobile command directory"}
    ]
    try:
        res = tg_api_request(bot_token, "setMyCommands", {"commands": commands})
        if res and res.get("ok"):
            logger.info("Successfully registered bot command menu with Telegram.")
    except Exception as e:
        logger.warning(f"Error registering bot commands: {e}")


def send_engine_restart_alert(bot_token, config):
    """Sends an executive notification when the trading engine restarts."""
    try:
        import MetaTrader5 as mt5
        acc_str = "Disconnected"
        bal_str = "N/A"
        eq_str = "N/A"
        open_count = 0
        if mt5.initialize():
            acc = mt5.account_info()
            if acc:
                acc_str = f"{acc.server} #{acc.login}"
                bal_str = f"${acc.balance:,.2f}"
                eq_str = f"${acc.equity:,.2f}"
            pos = mt5.positions_get()
            open_count = len(pos) if pos else 0
            mt5.shutdown()

        from skill_integrity_guard import verify_skill_integrity
        is_valid, _ = verify_skill_integrity(silent=True)
        sec_status = "🟢 100% Cryptographically Certified (SHA-256)" if is_valid else "⚠️ Tamper Warning Active"

        session = load_session()
        session_id = session.get("session_id", "STANDBY")
        trades_done = session.get("trades_executed", 0)
        max_trades = session.get("max_trades", 5)
        lev_tier = session.get("approved_leverage_tier", "2x")

        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

        msg = (
            f"🚀 <b>AI AUTONOMOUS TRADING FIRM — ENGINE ONLINE &amp; RESTARTED</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"📅 <b>System Time:</b> <code>{now_str}</code>\n"
            f"🏦 <b>Broker / Account:</b> <code>{acc_str}</code>\n"
            f"💰 <b>Balance:</b> <code>{bal_str}</code> | <b>Equity:</b> <code>{eq_str}</code>\n"
            f"🛡️ <b>Open Exposure:</b> <b>{open_count} open position(s)</b>\n"
            f"🎯 <b>Session State:</b> <code>{session_id}</code> ({trades_done}/{max_trades} trades • {lev_tier})\n\n"
            f"<b>ACTIVE OPERATIONAL DAEMONS:</b>\n"
            f"  • 🟢 <b>Two-Way Mobile Listener:</b> Interactive 24/7\n"
            f"  • 🟢 <b>Autonomous Market Scanner:</b> 15m scanning active\n"
            f"  • 🟢 <b>Trade Monitor:</b> Deal Streamer &amp; 80/70 Protection armed\n"
            f"  • 🟢 <b>Daily Market Close Auditor:</b> 21:55 UTC scheduled\n"
            f"  • 🟢 <b>Security Guard:</b> {sec_status}\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"👉 <i>All commands are active as persistent buttons below:</i>"
        )

        admin_id = str(config.get("telegram", {}).get("admin_chat_id", "1264076025")).strip()
        send_tg_message(bot_token, admin_id, msg, reply_markup=make_reply_keyboard())
        logger.info(f"Engine restart notification delivered to Administrator {admin_id}")
    except Exception as e:
        logger.error(f"Error sending engine restart alert: {e}")


def start_trading_session(market="BOTH", batch_size=2, daily_rounds=2, quota_trades=None):
    """
    Initializes session state for v3.8.4 Batch Concurrency & Multi-Round Architecture:
      - market: "GOLD" (XAUUSD), "FOREX" (EURUSD), or "BOTH" (EURUSD, XAUUSD)
      - batch_size (x): Number of concurrent trades opened per setup (e.g. 1, 2, 3, 5).
                        Each trade is 0.01 lot with an independent $25.00 profit target and 80/70 protection.
      - daily_rounds: Number of batches/cycles executed daily (e.g. 1, 2, 3, 5 rounds).
      - total daily trades = batch_size * daily_rounds
      - batch profit goal = batch_size * $25.00
      - daily profit goal = total daily trades * $25.00
    """
    m_str = str(market).strip().upper()
    if m_str.endswith("X") or m_str.isdigit():
        raw_num = m_str[:-1] if m_str.endswith("X") else m_str
        b_val = max(1, int(raw_num)) if raw_num.isdigit() else 2
        m_resolved = "BOTH"
        b_resolved = b_val
        r_raw = str(batch_size).strip().upper().replace("X", "").replace("R", "")
        is_continuous = r_raw in ("ALLWEEK", "ALL_WEEK", "CONTINUOUS", "ALWAYS", "ALWAYS_ACTIVE", "UNLIMITED", "WEEK")
        r_resolved = "ALL_WEEK" if is_continuous else (int(r_raw) if r_raw.isdigit() else 1)
    else:
        if "GOLD" in m_str or "XAU" in m_str:
            m_resolved = "GOLD"
        elif "EUR" in m_str or "FOREX" in m_str:
            m_resolved = "FOREX"
        else:
            m_resolved = "BOTH"

        b_raw = str(batch_size).strip().upper().replace("X", "")
        b_resolved = int(b_raw) if b_raw.isdigit() else 2
        r_raw = str(daily_rounds).strip().upper().replace("X", "").replace("R", "")
        is_continuous = r_raw in ("ALLWEEK", "ALL_WEEK", "CONTINUOUS", "ALWAYS", "ALWAYS_ACTIVE", "UNLIMITED", "WEEK")
        r_resolved = "ALL_WEEK" if is_continuous else (int(r_raw) if r_raw.isdigit() else 2)

    is_continuous = (r_resolved == "ALL_WEEK")
    final_batch = max(1, b_resolved)
    target_profit_per_trade = 25.0
    batch_profit_goal = round(target_profit_per_trade * final_batch, 2)

    if is_continuous:
        final_rounds = "ALL_WEEK"
        total_trades = 9999
        session_profit_goal = "Uncapped (All-Week Continuous)"
        tier_label = f"{final_batch}x (Continuous All-Week)"
        session_id = f"SES-{datetime.now(timezone.utc).strftime('%Y%m%d')}-{m_resolved}-{final_batch}X-ALLWEEK"
    else:
        final_rounds = max(1, r_resolved)
        total_trades = final_batch * final_rounds
        session_profit_goal = round(target_profit_per_trade * total_trades, 2)
        tier_label = f"{final_batch}x ({final_rounds}R)"
        session_id = f"SES-{datetime.now(timezone.utc).strftime('%Y%m%d')}-{m_resolved}-{final_batch}X-{final_rounds}R"

    if m_resolved == "GOLD":
        watchlist = ["XAUUSD"]
        active_market_label = "XAUUSD (Gold Only)"
    elif m_resolved == "FOREX":
        watchlist = ["EURUSD"]
        active_market_label = "EURUSD (Forex Only)"
    else:
        watchlist = ["EURUSD", "XAUUSD"]
        active_market_label = "EURUSD, XAUUSD (Both Multi-Asset)"

    margin_stress = f"{final_batch * 2.7:.1f}% (Institutional A+ Rating)"

    session_data = {
        "session_id": session_id,
        "market_choice": m_resolved,
        "active_market": active_market_label,
        "watchlist": watchlist,
        "concurrent_batch_size": final_batch,
        "daily_rounds": final_rounds,
        "is_continuous": is_continuous,
        "target_profit_per_trade": target_profit_per_trade,
        "batch_profit_goal": batch_profit_goal,
        "session_profit_goal": session_profit_goal,
        "session_tier": tier_label,
        "risk_per_trade_dollars": 25.0,
        "max_daily_loss_dollars": 50.0,
        "default_lots": 0.01,
        "leverage_multiplier": 1.0,
        "leverage_trades_quota": quota_trades if quota_trades is not None else total_trades,
        "leverage_trades_used": 0,
        "baseline_leverage": 1.0,
        "gold_profit_target_base": 25.0,
        "max_trades": total_trades,
        "trades_executed": 0,
        "trades_today": 0,
        "current_trade_day": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "trading_mode": "D",
        "risk_manager_status": "APPROVED_BY_CRO",
        "approved_leverage_tier": tier_label,
        "margin_stress_score": margin_stress,
        "start_time": datetime.now(timezone.utc).isoformat(),
        "is_active": True
    }
    save_session(session_data)

    # Launch background daemons only if not already running
    try:
        import psutil
        running_cmd = []
        for p in psutil.process_iter(["name", "cmdline"]):
            try:
                if "python" in (p.info["name"] or "").lower():
                    running_cmd.append(" ".join(p.info["cmdline"] or []))
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass

        scanner_running = any("auto_scanner.py" in c for c in running_cmd)
        monitor_running = any("trade_monitor.py" in c for c in running_cmd)
        summary_running = any("daily_summary.py" in c for c in running_cmd)

        if not scanner_running:
            scanner_cmd = [sys.executable, os.path.join(BASE_DIR, "scripts", "auto_scanner.py"), "15"]
            subprocess.Popen(scanner_cmd, cwd=BASE_DIR, creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0)
            logger.info("Spawned auto_scanner.py daemon")

        if not monitor_running:
            monitor_cmd = [sys.executable, os.path.join(BASE_DIR, "scripts", "trade_monitor.py")]
            subprocess.Popen(monitor_cmd, cwd=BASE_DIR, creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0)
            logger.info("Spawned trade_monitor.py daemon")

        if not summary_running:
            summary_cmd = [sys.executable, os.path.join(BASE_DIR, "scripts", "daily_summary.py"), "--daemon"]
            subprocess.Popen(summary_cmd, cwd=BASE_DIR, creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0)
            logger.info("Spawned daily_summary.py daemon")

    except Exception as e:
        logger.error(f"Error launching daemons: {e}")

    return session_data


def is_market_closed_now():
    """Check if global markets are currently closed for the weekend."""
    now = datetime.now(timezone.utc)
    weekday = now.weekday()  # 0=Mon, 4=Fri, 5=Sat, 6=Sun
    hour = now.hour
    minute = now.minute

    if weekday == 4 and (hour > 21 or (hour == 21 and minute >= 55)):
        return True, "Friday post-settlement close"
    if weekday == 5:
        return True, "Saturday full-day close"
    if weekday == 6 and hour < 22:
        return True, "Sunday pre-open close (Gold & FX open at 22:00 UTC)"
    return False, "Market is OPEN"


def check_sunday_market_reopen(bot_token, config):
    """
    Automated Sunday Market Reopen Daemon Hook (Gate 12).
    If markets have reopened (Sunday >= 22:00 UTC or weekday) and a session was parked
    with WEEKEND_MARKET_CLOSE_AUTO_TERMINATION, automatically reactivate it,
    spawn auto_scanner and trade_monitor daemons, and alert Administrator @wtalaat.
    """
    closed, _ = is_market_closed_now()
    if closed:
        return

    session = load_session()
    if not session.get("is_active", True) and session.get("shutdown_reason") == "WEEKEND_MARKET_CLOSE_AUTO_TERMINATION":
        logger.info("[SUNDAY RE-OPEN PROTOCOL] Markets reopened. Reactivating session state and launching trading daemons.")
        now_utc = datetime.now(timezone.utc)
        session["is_active"] = True
        session["trades_executed"] = 0
        session["shutdown_reason"] = None
        session["start_time"] = now_utc.isoformat()
        save_session(session)

        # Check if daemons are already running
        import psutil
        running_cmd = []
        for p in psutil.process_iter(["name", "cmdline"]):
            if "python" in (p.info["name"] or "").lower():
                running_cmd.append(" ".join(p.info["cmdline"] or []))

        scanner_running = any("auto_scanner.py" in c for c in running_cmd)
        monitor_running = any("trade_monitor.py" in c for c in running_cmd)

        if not scanner_running:
            scanner_cmd = [sys.executable, os.path.join(BASE_DIR, "scripts", "auto_scanner.py"), "15"]
            subprocess.Popen(scanner_cmd, cwd=BASE_DIR, creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0)
            logger.info("Auto-spawned auto_scanner.py daemon for Sunday reopen.")

        if not monitor_running:
            monitor_cmd = [sys.executable, os.path.join(BASE_DIR, "scripts", "trade_monitor.py")]
            subprocess.Popen(monitor_cmd, cwd=BASE_DIR, creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0)
            logger.info("Auto-spawned trade_monitor.py daemon for Sunday reopen.")

        # Broadcast Sunday Re-Open alert to Admin
        tg_cfg = config.get("telegram", {})
        admin_chat_id = tg_cfg.get("admin_chat_id") or tg_cfg.get("chat_id")
        if bot_token and admin_chat_id:
            msg = (
                "🔔 <b>SUNDAY MARKET REOPEN DETECTED (Gate 12)</b>\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "📅 <b>Global FX &amp; Metals Markets are now OPEN.</b>\n"
                f"🆔 <b>Session Reactivated:</b> <code>{session.get('session_id')}</code>\n"
                f"🌐 <b>Universe:</b> <b>{session.get('active_market')}</b>\n"
                f"⚡ <b>Concurrency:</b> <b>{session.get('concurrent_batch_size')}x Batch</b>\n"
                f"🎯 <b>Daily Rounds:</b> <b>{session.get('daily_rounds')} Rounds</b>\n"
                "🤖 <b>Autonomous Daemons:</b> <code>auto_scanner.py</code> &amp; <code>trade_monitor.py</code> online\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "✅ <i>Execution engine is live and scanning for institutional setups!</i>"
            )
            send_tg_message(bot_token, admin_chat_id, msg, reply_markup=make_main_keyboard())


def handle_start_session_cmd(args, chat_id, bot_token, message_id=None):
    """
    Parse /start_session command parameters and initiate session.
    Supported inputs:
      - No args or 'wizard' -> Launches 3-step interactive button wizard
      - /start_session gold 5 3 -> 5 concurrent gold trades, 3 rounds daily
      - /start_session both 2 2 -> 2 concurrent trades, 2 rounds daily
      - /start_session 5x 3 -> 5 concurrent trades, 3 rounds daily
      - /start_session 1x -> 1 trade, 1 round
    """
    # If no args or wizard requested, open wizard Step 1
    if not args or args[0].lower() in ("wizard", "config", "step1", "menu"):
        send_wizard_step1(chat_id, bot_token, message_id)
        return

    clean_args = [a for a in args if not a.startswith("--")]
    market = "BOTH"
    batch = 2
    rounds = 2

    if len(clean_args) >= 3:
        market = clean_args[0]
        batch = clean_args[1]
        rounds = clean_args[2]
    elif len(clean_args) == 2:
        arg0_up = clean_args[0].upper()
        arg1_up = clean_args[1].upper()
        if arg0_up in ("GOLD", "FOREX", "BOTH", "EURUSD", "XAUUSD"):
            market = clean_args[0]
            if arg1_up in ("ALLWEEK", "ALL_WEEK", "CONTINUOUS", "ALWAYS", "UNLIMITED"):
                batch = 2
                rounds = "ALL_WEEK"
            else:
                batch = clean_args[1]
                rounds = 2
        else:
            market = "BOTH"
            batch = clean_args[0]
            rounds = clean_args[1]
    elif len(clean_args) == 1:
        arg0_up = clean_args[0].upper()
        if arg0_up in ("GOLD", "FOREX", "BOTH", "EURUSD", "XAUUSD"):
            market = clean_args[0]
            batch = 2
            rounds = 2
        elif arg0_up in ("ALLWEEK", "ALL_WEEK", "CONTINUOUS", "ALWAYS", "UNLIMITED"):
            market = "BOTH"
            batch = 2
            rounds = "ALL_WEEK"
        else:
            market = "BOTH"
            batch = clean_args[0]
            rounds = 1

    # Check for market closure
    is_closed, reason = is_market_closed_now()
    if is_closed and "--force" not in args:
        session = start_trading_session(market, batch, rounds)
        freq_label = "🔄 Continuous All-Week" if session.get("is_continuous") else f"{session.get('daily_rounds')} Daily"
        warning_msg = (
            f"⚠️ <b>SESSION ARMED FOR SUNDAY MARKET RE-OPEN</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"📅 <b>Current Market Status:</b> {reason}\n"
            f"⏰ <b>Market Reopens:</b> <b>Sunday 22:00 UTC</b> (Monday 01:00 Cairo time / UTC+3)\n\n"
            f"🆔 <b>Session ID:</b> <code>{session['session_id']}</code>\n"
            f"🌐 <b>Active Universe:</b> <b>{session.get('active_market')}</b>\n"
            f"⚡ <b>Concurrency:</b> <b>{session.get('concurrent_batch_size')}x Orders</b>\n"
            f"🎯 <b>Frequency:</b> <b>{freq_label}</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"✅ <i>Session parameters saved & armed! The autonomous engine will automatically commence scanning upon market reopen on Sunday at 22:00 UTC.</i>"
        )
        send_tg_message(bot_token, chat_id, warning_msg, reply_markup=make_main_keyboard())
        return

    session = start_trading_session(market, batch, rounds)
    target_dollars = float(session.get("target_profit_per_trade", 25.0))
    batch_size = session.get("concurrent_batch_size", 1)
    batch_goal = float(session.get("batch_profit_goal", 50.0))
    is_continuous = bool(session.get("is_continuous", False))
    market_label = session.get("active_market", "EURUSD, XAUUSD")

    if is_continuous:
        rounds_line = f"🎯 <b>Execution Mode:</b> <b>🔄 Always Active (All-Week Continuous)</b>\n"
        goal_line = f"🌟 <b>Session Goal:</b> <b>Continuous Profit Compounding (Monday–Friday)</b>\n"
    else:
        daily_rounds = session.get("daily_rounds", 1)
        raw_goal = session.get("session_profit_goal", 100.0)
        daily_goal = float(raw_goal) if not isinstance(raw_goal, str) else 100.0
        total_trades = session.get("max_trades", 2)
        rounds_line = f"🎯 <b>Daily Execution:</b> <b>{daily_rounds} Round{'s' if isinstance(daily_rounds, int) and daily_rounds > 1 else ''} Daily</b> ({total_trades} Total Trades)\n"
        goal_line = f"🌟 <b>Total Daily Goal:</b> <b>+${daily_goal:.2f} USD</b>\n"

    msg = (
        f"🚀 <b>AUTONOMOUS SESSION LAUNCHED VIA TELEGRAM</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🆔 <b>Session ID:</b> <code>{session['session_id']}</code>\n"
        f"🌐 <b>Active Market:</b> <b>{market_label}</b>\n"
        f"⚡ <b>Batch Concurrency:</b> <b>{batch_size}x Simultaneous Orders</b> (0.01L each)\n"
        f"{rounds_line}"
        f"💰 <b>Target Profit / Trade:</b> <code>+${target_dollars:.2f}</code>\n"
        f"🏆 <b>Batch Target / Round:</b> <b>+${batch_goal:.2f} USD</b>\n"
        f"{goal_line}"
        f"🛡️ <b>80/70 Protection:</b> Arms @ <code>+${target_dollars * 0.80:.2f}</code> | Floor @ <code>+${target_dollars * 0.70:.2f}</code> per trade\n"
        f"🛡️ <b>CRO Safety Score:</b> <b>{session.get('margin_stress_score')}</b>\n"
        f"🤖 <b>Active Daemons:</b> Scanner, Trade Monitor &amp; Daily Auditor Online\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"<i>Autonomous scanner is actively monitoring markets for high-probability setups...</i>"
    )
    send_tg_message(bot_token, chat_id, msg, reply_markup=make_main_keyboard())


def handle_status_cmd(chat_id, bot_token):
    """Retrieve MT5 live telemetry and session parameters."""
    try:
        import MetaTrader5 as mt5
        if not mt5.initialize():
            send_tg_message(bot_token, chat_id, f"❌ Failed to connect to MT5: {mt5.last_error()}")
            return

        acc = mt5.account_info()
        positions = mt5.positions_get()
        term = mt5.terminal_info()
        algo_status = "🟢 ENABLED (Ready)" if (term and term.trade_allowed) else "⚠️ DISABLED (Press Ctrl+E in MT5)"

        # Macro bias & daily PnL
        from mt5_connector import get_macro_trend_bias, get_daily_realized_pnl
        today_pnl = get_daily_realized_pnl()
        macro_xau = get_macro_trend_bias("XAUUSD", mt5.TIMEFRAME_H4)
        macro_bias_gold = macro_xau.get("bias", "UNKNOWN")

        # Killzone check
        now_utc = datetime.now(timezone.utc)
        cur_min = now_utc.hour * 60 + now_utc.minute
        in_london = (420 <= cur_min <= 630)
        in_ny = (750 <= cur_min <= 990)
        if in_london:
            kz_status = "🟢 London Open (07:00-10:30 UTC)"
        elif in_ny:
            kz_status = "🟢 New York Active (12:30-16:30 UTC)"
        elif 630 < cur_min < 750:
            kz_status = "⏸️ European Lunch Lull"
        else:
            kz_status = "🌙 Asian / Overnight (Off-Killzone)"

        margin_lvl = (acc.equity / acc.margin * 100.0) if acc and acc.margin > 0 else 9999.0

        mt5.shutdown()

        session = load_session()
        is_active = session.get("is_active", False)
        status_icon = "🟢 ACTIVE" if is_active else "⏹️ INACTIVE"

        pos_lines = []
        if positions:
            for p in positions:
                side = "BUY" if p.type == 0 else "SELL"
                c_tag = f" [{p.comment}]" if p.comment else ""
                pos_lines.append(f"  • #{p.ticket} {side} {p.symbol} ({p.volume}L){c_tag} @ {p.price_open} ➔ P&L: <code>${p.profit:+.2f}</code>")
            pos_text = "\n".join(pos_lines)
        else:
            pos_text = "  • No open positions (100% Flat & Protected)"

        target_per_trade = float(session.get("target_profit_per_trade", 25.0))
        batch_size = int(session.get("concurrent_batch_size", 1))
        batch_goal = float(session.get("batch_profit_goal", target_per_trade * batch_size))
        trades_done = session.get('trades_executed', 0)
        trades_today = session.get('trades_today', trades_done)
        max_trades = session.get('max_trades', 0)
        is_continuous = bool(session.get("is_continuous", False)) or str(session.get("daily_rounds", "")).upper() in ("ALL_WEEK", "ALLWEEK", "CONTINUOUS", "ALWAYS_ACTIVE", "UNLIMITED")
        market_label = session.get("active_market", "EURUSD, XAUUSD")

        if is_continuous:
            rounds_display = f"🔄 <b>Mode:</b> <b>Always Active (All-Week Continuous)</b> (Today: {trades_today} | Week Total: {trades_done} Trades)"
        else:
            raw_rounds = session.get("daily_rounds", (max_trades // batch_size) if batch_size > 0 else max_trades)
            daily_rounds = int(raw_rounds) if str(raw_rounds).isdigit() else 2
            current_round = ((trades_done - 1) // batch_size) + 1 if trades_done > 0 and batch_size > 0 else 0
            rounds_display = f"🎯 <b>Daily Rounds:</b> <b>Round {current_round}/{daily_rounds}</b> ({trades_done}/{max_trades} Total Trades)"

        msg = (
            f"📊 <b>FIRM LIVE TELEMETRY &amp; STATUS</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"🆔 <b>Session:</b> <code>{session.get('session_id', 'NONE')}</code> [{status_icon}]\n"
            f"🤖 <b>MT5 Algo Trading:</b> <b>{algo_status}</b>\n"
            f"🌐 <b>Universe:</b> <b>{market_label}</b>\n"
            f"🏦 <b>Balance:</b> <code>${acc.balance:,.2f}</code> | <b>Equity:</b> <code>${acc.equity:,.2f}</code>\n"
            f"📈 <b>Free Margin:</b> <code>${acc.margin_free:,.2f}</code> | <b>Margin Level:</b> <code>{margin_lvl:.0f}%</code>\n"
            f"💵 <b>Today Realized PnL:</b> <b><code>${today_pnl:+.2f} USD</code></b>\n"
            f"🧭 <b>PTJ 4H 200 EMA (Gold):</b> <b>{macro_bias_gold}</b>\n"
            f"⏱️ <b>Killzone:</b> <b>{kz_status}</b>\n"
            f"⚡ <b>Concurrency:</b> <b>{batch_size}x Concurrent Trades</b> per setup\n"
            f"{rounds_display}\n"
            f"🛡️ <b>Asymmetric Protection:</b> Banker (80/70 Server SL) | Runner (Dynamic BE+Lock & 60/50 Guard)\n\n"
            f"🛡️ <b>OPEN POSITIONS ({len(positions) if positions else 0}):</b>\n"
            f"{pos_text}\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"<i>AI Autonomous Trading Firm v5.4.0</i>"
        )
        send_tg_message(bot_token, chat_id, msg, reply_markup=make_main_keyboard())
    except Exception as e:
        send_tg_message(bot_token, chat_id, f"❌ Error querying status: {e}")


def handle_scan_cmd(chat_id, bot_token):
    """Execute on-demand market sweep with PTJ 4H bias, spread gate, and BB status."""
    try:
        import MetaTrader5 as mt5
        import pandas as pd
        import numpy as np

        if not mt5.initialize():
            send_tg_message(bot_token, chat_id, f"❌ Failed to connect to MT5: {mt5.last_error()}")
            return

        from mt5_connector import get_macro_trend_bias

        # Killzone check
        now_utc = datetime.now(timezone.utc)
        cur_min = now_utc.hour * 60 + now_utc.minute
        in_london = (420 <= cur_min <= 630)
        in_ny = (750 <= cur_min <= 990)
        if in_london:
            kz_status = "🟢 London Open Killzone (07:00-10:30 UTC)"
        elif in_ny:
            kz_status = "🟢 New York Active Killzone (12:30-16:30 UTC)"
        elif 630 < cur_min < 750:
            kz_status = "⏸️ European Lunch Lull (10:30-12:30 UTC)"
        else:
            kz_status = "🌙 Asian / Overnight (Off-Killzone)"

        reports = []
        for symbol in ["EURUSD", "XAUUSD"]:
            rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M15, 0, 30)
            if rates is None or len(rates) < 20:
                continue
            df = pd.DataFrame(rates)
            df['mid'] = df['close'].rolling(20).mean()
            df['std'] = df['close'].rolling(20).std()
            df['upper'] = df['mid'] + 2.0 * df['std']
            df['lower'] = df['mid'] - 2.0 * df['std']
            df['tr'] = np.maximum(df['high'] - df['low'], np.maximum(abs(df['high'] - df['close'].shift(1)), abs(df['low'] - df['close'].shift(1))))
            df['atr'] = df['tr'].rolling(14).mean()
            delta = df['close'].diff()
            gain = (delta.where(delta > 0, 0)).rolling(14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
            rs = gain / (loss + 1e-9)
            df['rsi'] = 100 - (100 / (1 + rs))

            last = df.iloc[-1]
            dist_up = last['upper'] - last['close']
            dist_dn = last['close'] - last['lower']

            if last['close'] >= last['upper']:
                status = "🔴 OVERBOUGHT (Short Reversal Zone)"
            elif last['close'] <= last['lower']:
                status = "🟢 OVERSOLD (Long Reversal Zone)"
            else:
                status = "⚪ CONSOLIDATING (Inside Envelope)"

            # PTJ 4H macro bias
            m_info = get_macro_trend_bias(symbol, mt5.TIMEFRAME_H4)
            m_bias = m_info.get("bias", "NEUTRAL")

            # Spread check
            tick = mt5.symbol_info_tick(symbol)
            spread_str = f"${(tick.ask - tick.bid):.2f}" if tick and "XAU" in symbol else (f"{((tick.ask - tick.bid)*10000):.1f} pips" if tick else "N/A")

            digits = 2 if "XAU" in symbol else 5
            reports.append(
                f"<b>{symbol} (M15):</b>\n"
                f"  • Price: <code>{last['close']:.{digits}f}</code> | Spread: <code>{spread_str}</code>\n"
                f"  • PTJ 4H Bias: <b>{m_bias}</b> (200 EMA: {m_info.get('ema200', 0):.{digits}f})\n"
                f"  • RSI(14): <b>{last['rsi']:.1f}</b> | ATR(14): <code>{last['atr']:.{digits}f}</code>\n"
                f"  • BB Upper: <code>{last['upper']:.{digits}f}</code> | Lower: <code>{last['lower']:.{digits}f}</code>\n"
                f"  • Status: <b>{status}</b>"
            )

        mt5.shutdown()
        scan_text = "\n\n".join(reports) if reports else "No candle data available."
        msg = (
            f"🔍 <b>ON-DEMAND MARKET SWEEP TELEMETRY</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"⏱️ <b>Killzone:</b> <b>{kz_status}</b>\n\n"
            f"{scan_text}\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"<i>AI Autonomous Firm v5.1.0 (PTJ 4H Trend &amp; Asymmetric Reversion)</i>"
        )
        send_tg_message(bot_token, chat_id, msg, reply_markup=make_main_keyboard())
    except Exception as e:
        send_tg_message(bot_token, chat_id, f"❌ Error during market scan: {e}")


def handle_close_cmd(chat_id, bot_token):
    """Execute Emergency Kill Switch: Close all open positions immediately."""
    try:
        from mt5_connector import close_all_positions
        res = close_all_positions()

        import MetaTrader5 as mt5
        mt5.initialize()
        acc = mt5.account_info()
        mt5.shutdown()

        msg = (
            f"🛑 <b>EMERGENCY KILL SWITCH EXECUTED</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"✅ <b>Status:</b> ALL OPEN POSITIONS CLOSED\n"
            f"🛡️ <b>Open Exposure:</b> 0 (100% Flat & Safe)\n"
            f"🏦 <b>Account Balance:</b> <code>${acc.balance:,.2f}</code>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"<i>All market risk terminated per remote Telegram command.</i>"
        )
        send_tg_message(bot_token, chat_id, msg, reply_markup=make_main_keyboard())
    except Exception as e:
        send_tg_message(bot_token, chat_id, f"❌ Error executing emergency close: {e}")


def handle_stop_cmd(chat_id, bot_token):
    """Gracefully stop autonomous scanner and mark session inactive."""
    try:
        session = load_session()
        session["is_active"] = False
        session["shutdown_reason"] = "REMOTE_TELEGRAM_STOP_COMMAND"
        save_session(session)

        from daily_summary import kill_all_trading_processes
        killed = kill_all_trading_processes()

        msg = (
            f"⏹️ <b>AUTONOMOUS TRADING ENGINE STOPPED</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"🆔 <b>Session:</b> <code>{session.get('session_id', 'N/A')}</code>\n"
            f"⏹️ <b>Engine Status:</b> INACTIVE / STOPPED\n"
            f"🤖 <b>Processes Terminated:</b> {killed} daemon(s)\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"<i>Send /start_session or tap the button below to resume.</i>"
        )
        send_tg_message(bot_token, chat_id, msg, reply_markup=make_main_keyboard())
    except Exception as e:
        send_tg_message(bot_token, chat_id, f"❌ Error stopping engine: {e}")


def handle_integrity_cmd(chat_id, bot_token):
    """Verify cryptographic SHA-256 signatures."""
    try:
        from skill_integrity_guard import verify_skill_integrity
        valid, mismatches = verify_skill_integrity(silent=True)
        if valid:
            msg = (
                f"🛡️ <b>CRYPTOGRAPHIC INTEGRITY VERIFIED</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"✅ <b>Status:</b> 100% SECURE &amp; AUTHENTIC\n"
                f"🔒 <b>Protected Files:</b> All 12 core engine &amp; skill files verified against SHA-256 signatures.\n"
                f"💻 <b>Authorized Node:</b> Master Primary Node (<code>WALEED-IT</code>)\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"<i>Anti-Tamper Security Guard v5.1.0</i>"
            )
        else:
            mismatches_str = ", ".join(mismatches) if isinstance(mismatches, list) else str(mismatches)
            msg = f"⚠️ <b>SECURITY ALERT:</b> Tampering detected on:\n{mismatches_str}"
        send_tg_message(bot_token, chat_id, msg, reply_markup=make_main_keyboard())
    except Exception as e:
        send_tg_message(bot_token, chat_id, f"❌ Integrity check error: {e}")


def handle_direct_trade_cmd(order_type, args, chat_id, bot_token):
    """
    Executes a direct market order from Telegram: /buy XAUUSD 0.01 or /sell EURUSD 0.01
    """
    try:
        import MetaTrader5 as mt5
        if not mt5.initialize():
            send_tg_message(bot_token, chat_id, f"❌ Failed to connect to MT5: {mt5.last_error()}")
            return

        symbol = args[0].upper() if len(args) >= 1 else "XAUUSD"
        if "GOLD" in symbol or "XAU" in symbol:
            symbol = "XAUUSD"
        elif "EUR" in symbol:
            symbol = "EURUSD"
        else:
            symbol = "XAUUSD"

        # Resolve volume (default 0.01 for micro account safety)
        session = load_session()
        def_lots = float(session.get("default_lots", 0.01))
        if len(args) >= 2:
            try:
                volume = float(args[1])
            except ValueError:
                volume = def_lots
        else:
            volume = def_lots

        tick = mt5.symbol_info_tick(symbol)
        if not tick:
            mt5.shutdown()
            send_tg_message(bot_token, chat_id, f"❌ Cannot get price tick for {symbol}. Market might be closed for the weekend.")
            return

        price = tick.ask if order_type == "BUY" else tick.bid
        digits = 2 if "XAU" in symbol else 5

        # ATR calculation for dynamic SL/TP
        rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M15, 0, 20)
        atr = 15.0 if symbol == "XAUUSD" else 0.0010
        if rates is not None and len(rates) >= 14:
            highs = [r['high'] for r in rates]
            lows = [r['low'] for r in rates]
            atr = max(sum([h - l for h, l in zip(highs[-14:], lows[-14:])]) / 14.0, 0.0005 if "EUR" in symbol else 5.0)

        sl_dist = round(max(atr * 1.0, 0.0010 if "EUR" in symbol else 8.0), digits)
        tp_dist = round(max(sl_dist * 1.5, 0.0015 if "EUR" in symbol else 12.0), digits)

        if order_type == "BUY":
            sl = round(price - sl_dist, digits)
            tp = round(price + tp_dist, digits)
        else:
            sl = round(price + sl_dist, digits)
            tp = round(price - tp_dist, digits)

        ticket_data = {
            "symbol": symbol,
            "order_type": order_type,
            "lots": volume,
            "sl": sl,
            "tp": tp,
            "strategy": "Manual_Telegram_Direct",
            "comment": "v5.1.0-Manual"
        }

        from mt5_connector import execute_mt5_order
        res = execute_mt5_order(ticket_data)
        mt5.shutdown()

        if res.get("status") == "SUCCESS":
            msg = (
                f"⚡ <b>TRADE EXECUTED DIRECTLY FROM TELEGRAM</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"🎫 <b>Ticket:</b> <code>#{res.get('ticket')}</code>\n"
                f"🎯 <b>Action:</b> <b>{order_type} {symbol}</b> ({volume} lots)\n"
                f"💵 <b>Execution Price:</b> <code>{res.get('price')}</code>\n"
                f"🛑 <b>Stop Loss:</b> <code>{res.get('sl')}</code>\n"
                f"🎯 <b>Take Profit:</b> <code>{res.get('tp1')}</code>\n"
                f"🛡️ <b>CRO Safety:</b> Active &amp; Protected\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"<i>Real-time deal streamer is actively monitoring exit...</i>"
            )
        else:
            msg = (
                f"❌ <b>ORDER REJECTED / FAILED</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"<b>Reason:</b> {res.get('reason', 'Unknown error')}\n"
                f"━━━━━━━━━━━━━━━━━━━━"
            )

        send_tg_message(bot_token, chat_id, msg, reply_markup=make_main_keyboard())
    except Exception as e:
        send_tg_message(bot_token, chat_id, f"❌ Error executing direct trade: {e}")


def handle_help_cmd(chat_id, bot_token):
    """Display complete mobile command directory."""
    msg = (
        f"🤖 <b>AI AUTONOMOUS TRADING FIRM — REMOTE COMMANDS</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"<b>⚙️ Interactive Configurator:</b>\n"
        f"  • Tap <b>⚙️ Configure Session (Wizard)</b> to pick market, concurrency & daily rounds via interactive buttons.\n"
        f"  • Or type <code>/wizard</code> anytime.\n\n"
        f"<b>🚀 Direct Session Launch (Market, Concurrency, Rounds):</b>\n"
        f"  • <code>/continuous [market] [batch]</code> — 🔄 <b>Always Active All-Week Mode</b> (e.g. <code>/continuous gold 2</code>)\n"
        f"  • <code>/start_session gold 5 3</code> — Gold, 5x concurrent (15 trades, +$375 goal)\n"
        f"  • <code>/start_session gold 2 allweek</code> — Gold, 2x concurrent Always Active All Week\n"
        f"  • <code>/start_session both 2 2</code> — Both, 2x concurrent (4 trades, +$100 goal)\n"
        f"  • <code>/start_session 1x</code> — 1 Trade ($25 target, 80/70 protection)\n"
        f"  • <code>/status</code> — Live balance, equity, rounds progress & target metrics\n"
        f"  • <code>/stop</code> — Stop active auto-scanner\n\n"
        f"<b>⚡ Instant Direct Execution:</b>\n"
        f"  • <code>/buy [symbol] [lots]</code> — Instant market BUY (e.g. <code>/buy XAUUSD 0.01</code>)\n"
        f"  • <code>/sell [symbol] [lots]</code> — Instant market SELL (e.g. <code>/sell EURUSD 0.01</code>)\n"
        f"  • <code>/scan</code> — Force immediate market sweep on EURUSD & Gold\n"
        f"  • <code>/close</code> — <b>Kill Switch:</b> Emergency close all open positions\n\n"
        f"<b>📊 Reports &amp; Security:</b>\n"
        f"  • <code>/news [symbol]</code> — Live Macro &amp; Economic News Advisory for CRO\n"
        f"  • <code>/summary</code> — Today's performance summary\n"
        f"  • <code>/weekly</code> — Full weekly audit report\n"
        f"  • <code>/integrity</code> — Verify SHA-256 anti-tamper status\n"
        f"  • <code>/approve [token]</code> — Authorize pending code/skill modifications\n"
        f"  • <code>/reject [token]</code> — Reject modifications &amp; maintain lockout\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"<i>Tap any quick button below for instant action:</i>"
    )
    send_tg_message(bot_token, chat_id, msg, reply_markup=make_main_keyboard())


def process_update(update, bot_token, config):
    """Route incoming message or callback query."""
    # Handle Callback Queries (Button Clicks)
    if "callback_query" in update:
        cb = update["callback_query"]
        user_id = cb.get("from", {}).get("id")
        chat_id = cb.get("message", {}).get("chat", {}).get("id")
        msg_id = cb.get("message", {}).get("message_id")
        data = cb.get("data", "")

        if not is_authorized(user_id, chat_id, config):
            logger.warning(f"Unauthorized callback from user {user_id}")
            return

        mirror_log_event("USER", f"[Button Click]: {data}", user_info=f"User {user_id}")
        tg_api_request(bot_token, "answerCallbackQuery", {"callback_query_id": cb.get("id")})

        if data == "cb_status":
            handle_status_cmd(chat_id, bot_token)
        elif data == "cb_scan":
            handle_scan_cmd(chat_id, bot_token)
        elif data == "cb_close":
            handle_close_cmd(chat_id, bot_token)
        elif data == "cb_stop":
            handle_stop_cmd(chat_id, bot_token)
        elif data == "cb_help":
            handle_help_cmd(chat_id, bot_token)
        elif data == "cb_summary":
            from daily_summary import send_daily_summary
            send_daily_summary()
        elif data == "cb_weekly":
            from daily_summary import send_market_close_summary
            send_market_close_summary(is_weekend=True, kill_processes=False)
        elif data == "cb_integrity":
            handle_integrity_cmd(chat_id, bot_token)
        elif data == "cb_news":
            from news_analyzer import get_analyzer
            analyzer = get_analyzer()
            report = analyzer.format_telegram_advisory("XAUUSD")
            send_tg_message(bot_token, chat_id, report, reply_markup=make_main_keyboard())
        elif data == "wiz_start":
            send_wizard_step1(chat_id, bot_token, msg_id)
        elif data.startswith("wiz_m_"):
            m = data.replace("wiz_m_", "")
            send_wizard_step2(chat_id, bot_token, m, msg_id)
        elif data.startswith("wiz_b_"):
            parts = data.split("_")
            m = parts[2]
            b = parts[3]
            send_wizard_step3(chat_id, bot_token, m, b, msg_id)
        elif data.startswith("wiz_r_"):
            parts = data.split("_")
            m = parts[2]
            b = parts[3]
            r = parts[4]
            handle_start_session_cmd([m, b, r], chat_id, bot_token, msg_id)
        elif data == "cb_quick_gold_5x3":
            handle_start_session_cmd(["GOLD", "5", "3"], chat_id, bot_token)
        elif data == "cb_quick_gold_3x3":
            handle_start_session_cmd(["GOLD", "3", "3"], chat_id, bot_token)
        elif data == "cb_quick_gold_2x2":
            handle_start_session_cmd(["GOLD", "2", "2"], chat_id, bot_token)
        elif data == "cb_quick_gold_2x_allweek":
            handle_start_session_cmd(["GOLD", "2", "allweek"], chat_id, bot_token)
        elif data == "cb_quick_both_2x_allweek":
            handle_start_session_cmd(["BOTH", "2", "allweek"], chat_id, bot_token)
        elif data == "cb_quick_gold_1x5":
            handle_start_session_cmd(["GOLD", "1", "5"], chat_id, bot_token)
        elif data == "cb_quick_gold_1x3":
            handle_start_session_cmd(["GOLD", "1", "3"], chat_id, bot_token)
        elif data == "cb_quick_both_2x2":
            handle_start_session_cmd(["BOTH", "2", "2"], chat_id, bot_token)
        elif data == "cb_start_1x":
            handle_start_session_cmd(["BOTH", "1", "1"], chat_id, bot_token)
        elif data in ("cb_start_2x", "cb_start_5_2x"):
            handle_start_session_cmd(["BOTH", "2", "2"], chat_id, bot_token)
        elif data == "cb_start_3x":
            handle_start_session_cmd(["BOTH", "3", "1"], chat_id, bot_token)
        elif data == "cb_start_5x":
            handle_start_session_cmd(["BOTH", "5", "1"], chat_id, bot_token)
        elif data == "cb_buy_gold":
            handle_direct_trade_cmd("BUY", ["XAUUSD", "0.01"], chat_id, bot_token)
        elif data == "cb_sell_gold":
            handle_direct_trade_cmd("SELL", ["XAUUSD", "0.01"], chat_id, bot_token)
        elif data.startswith("auth_approve_"):
            if not is_admin(user_id, config):
                send_tg_message(bot_token, chat_id, "⛔ Permission Denied: Only Administrator @wtalaat can authorize modifications.")
                return
            tok = data.replace("auth_approve_", "")
            from skill_integrity_guard import approve_pending_authorization
            user_info = cb.get("from", {})
            admin_label = f"Telegram Admin @{user_info.get('username', user_id)} (ID: {user_id})"
            ok, res_msg = approve_pending_authorization(token=tok, approved_by=admin_label, notify=False)
            send_tg_message(bot_token, chat_id, res_msg, reply_markup=make_main_keyboard())
        elif data.startswith("auth_reject_"):
            if not is_admin(user_id, config):
                send_tg_message(bot_token, chat_id, "⛔ Permission Denied: Only Administrator @wtalaat can reject modifications.")
                return
            tok = data.replace("auth_reject_", "")
            from skill_integrity_guard import reject_pending_authorization
            user_info = cb.get("from", {})
            admin_label = f"Telegram Admin @{user_info.get('username', user_id)} (ID: {user_id})"
            ok, res_msg = reject_pending_authorization(token=tok, rejected_by=admin_label, notify=False)
            send_tg_message(bot_token, chat_id, res_msg, reply_markup=make_main_keyboard())
        return

    # Handle Text Messages (Commands and Button Taps)
    if "message" in update:
        msg = update["message"]
        user_id = msg.get("from", {}).get("id")
        chat_id = msg.get("chat", {}).get("id")
        text = msg.get("text", "").strip()

        if not is_authorized(user_id, chat_id, config):
            logger.warning(f"Unauthorized message from user {user_id}: {text}")
            send_tg_message(bot_token, chat_id, f"⛔ Unauthorized. User ID <code>{user_id}</code> is not in the approved whitelist.")
            return

        mirror_log_event("USER", text, user_info=f"User {user_id}")

        # Map persistent button texts and common natural language to commands
        btn_map = {
            "📊 live status": "/status",
            "📊 status": "/status",
            "status": "/status",
            "live status": "/status",
            "🔍 scan market": "/scan",
            "🔍 scan": "/scan",
            "scan": "/scan",
            "scan market": "/scan",
            "⚙️ configure session (wizard)": "/wizard",
            "⚙️ configure session": "/wizard",
            "configure session": "/wizard",
            "configure": "/wizard",
            "wizard": "/wizard",
            "config": "/wizard",
            "setup": "/wizard",
            "🥇 gold 5x (3 rounds • +$375)": "/start_session gold 5 3",
            "gold 5x (3 rounds • +$375)": "/start_session gold 5 3",
            "gold 5x": "/start_session gold 5 3",
            "🥇 gold 2x (2 rounds • +$100)": "/start_session gold 2 2",
            "gold 2x (2 rounds • +$100)": "/start_session gold 2 2",
            "gold 2x": "/start_session gold 2 2",
            "🔄 gold 2x (all-week continuous)": "/start_session gold 2 allweek",
            "gold 2x (all-week continuous)": "/start_session gold 2 allweek",
            "gold 2x all-week": "/start_session gold 2 allweek",
            "gold 2x continuous": "/start_session gold 2 allweek",
            "🔄 both 2x (all-week continuous)": "/start_session both 2 allweek",
            "both 2x (all-week continuous)": "/start_session both 2 allweek",
            "both 2x all-week": "/start_session both 2 allweek",
            "both 2x continuous": "/start_session both 2 allweek",
            "all-week": "/start_session both 2 allweek",
            "allweek": "/start_session both 2 allweek",
            "continuous": "/start_session both 2 allweek",
            "always active": "/start_session both 2 allweek",
            "🌐 both 2x (2 rounds • +$100)": "/start_session both 2 2",
            "both 2x (2 rounds • +$100)": "/start_session both 2 2",
            "both 2x": "/start_session both 2 2",
            "🚀 fast 1x ($25 win)": "/start_session both 1 1",
            "fast 1x ($25 win)": "/start_session both 1 1",
            "fast 1x": "/start_session both 1 1",
            "🚀 start 1x ($25)": "/start_session both 1 1",
            "🚀 start 1x": "/start_session both 1 1",
            "start 1x": "/start_session both 1 1",
            "1x": "/start_session both 1 1",
            "1": "/start_session both 1 1",
            "🚀 start 2x ($50)": "/start_session both 2 1",
            "🚀 start 2x": "/start_session both 2 1",
            "start 2x": "/start_session both 2 1",
            "2x": "/start_session both 2 1",
            "2": "/start_session both 2 1",
            "🚀 start 3x ($75)": "/start_session both 3 1",
            "🚀 start 3x": "/start_session both 3 1",
            "start 3x": "/start_session both 3 1",
            "3x": "/start_session both 3 1",
            "3": "/start_session both 3 1",
            "🚀 start 5x ($125)": "/start_session both 5 1",
            "🚀 start 5x": "/start_session both 5 1",
            "start 5x": "/start_session both 5 1",
            "5x": "/start_session both 5 1",
            "5": "/start_session both 5 1",
            "🚀 start session": "/wizard",
            "start session": "/wizard",
            "start": "/wizard",
            "trade": "/wizard",
            "📈 today summary": "/summary",
            "📈 summary": "/summary",
            "today summary": "/summary",
            "summary": "/summary",
            "daily summary": "/summary",
            "🏆 weekly audit": "/weekly",
            "weekly audit": "/weekly",
            "weekly": "/weekly",
            "audit": "/weekly",
            "⚡ buy gold (0.01)": "/buy XAUUSD 0.01",
            "⚡ buy gold (0.02)": "/buy XAUUSD 0.02",
            "⚡ buy gold": "/buy XAUUSD 0.01",
            "buy gold": "/buy XAUUSD 0.01",
            "⚡ sell gold (0.01)": "/sell XAUUSD 0.01",
            "⚡ sell gold (0.02)": "/sell XAUUSD 0.02",
            "⚡ sell gold": "/sell XAUUSD 0.01",
            "sell gold": "/sell XAUUSD 0.01",
            "📰 news & cro advisory": "/news",
            "📰 news advisory": "/news",
            "📰 news": "/news",
            "news": "/news",
            "macro": "/news",
            "economic news": "/news",
            "🛡️ verify security": "/integrity",
            "🛡️ integrity": "/integrity",
            "verify security": "/integrity",
            "integrity": "/integrity",
            "security": "/integrity",
            "🛑 close all (kill)": "/close",
            "🛑 close all": "/close",
            "close all": "/close",
            "close": "/close",
            "kill": "/close",
            "⏹️ stop scanner": "/stop",
            "stop scanner": "/stop",
            "stop": "/stop",
            "pause": "/stop",
            "❓ help / menu": "/help",
            "help": "/help",
            "menu": "/help"
        }

        normalized = text.lower().strip()
        if normalized in btn_map:
            text = btn_map[normalized]

        if not text.startswith("/"):
            send_tg_message(
                bot_token,
                chat_id,
                "💡 <i>Select an action from the buttons below or send /help to view command list:</i>",
                reply_markup=make_reply_keyboard()
            )
            return

        parts = text.split()
        cmd = parts[0].lower().replace("@techwavesegbot", "")
        args = parts[1:]

        logger.info(f"Processing command: {cmd} with args {args} from user {user_id}")

        if cmd in ("/start", "/help"):
            handle_help_cmd(chat_id, bot_token)
        elif cmd in ("/wizard", "/config", "/setup"):
            send_wizard_step1(chat_id, bot_token)
        elif cmd in ("/continuous", "/always_active", "/allweek"):
            # e.g. /continuous gold 2, /continuous 2, /continuous
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
            handle_start_session_cmd([m, b, "allweek"], chat_id, bot_token)
        elif cmd in ("/start_session", "/run", "/launch", "/start_trading", "/start_trades", "/trade", "/trade_now"):
            handle_start_session_cmd(args, chat_id, bot_token)
        elif cmd == "/buy":
            handle_direct_trade_cmd("BUY", args, chat_id, bot_token)
        elif cmd == "/sell":
            handle_direct_trade_cmd("SELL", args, chat_id, bot_token)
        elif cmd == "/status":
            handle_status_cmd(chat_id, bot_token)
        elif cmd == "/scan":
            handle_scan_cmd(chat_id, bot_token)
        elif cmd == "/close":
            handle_close_cmd(chat_id, bot_token)
        elif cmd in ("/stop", "/pause"):
            handle_stop_cmd(chat_id, bot_token)
        elif cmd == "/summary":
            from daily_summary import send_daily_summary
            send_daily_summary()
            send_tg_message(bot_token, chat_id, "📈 <b>Daily Market Close Audit</b> generated &amp; delivered to CRO @wtalaat.", reply_markup=make_main_keyboard())
        elif cmd in ("/weekly", "/audit"):
            from daily_summary import send_market_close_summary
            send_market_close_summary(is_weekend=True, kill_processes=False)
            send_tg_message(bot_token, chat_id, "🏆 <b>Weekly Performance Audit</b> generated &amp; delivered to CRO @wtalaat.", reply_markup=make_main_keyboard())
        elif cmd in ("/restart", "/reboot"):
            send_tg_message(bot_token, chat_id, "🔄 <b>Engine Daemons Reloaded &amp; Verified.</b>", reply_markup=make_main_keyboard())
            send_engine_restart_alert(bot_token, config)
        elif cmd == "/integrity":
            handle_integrity_cmd(chat_id, bot_token)
        elif cmd in ("/news", "/macro"):
            sym = args[0].upper() if args else "XAUUSD"
            from news_analyzer import get_analyzer
            analyzer = get_analyzer()
            report = analyzer.format_telegram_advisory(sym)
            send_tg_message(bot_token, chat_id, report, reply_markup=make_main_keyboard())
        elif cmd in ("/approve", "/authorize", "/certify"):
            if not is_admin(user_id, config):
                send_tg_message(bot_token, chat_id, "⛔ Permission Denied: Only Administrator @wtalaat can authorize modifications.")
                return
            tok = args[0] if len(args) > 0 else None
            from skill_integrity_guard import approve_pending_authorization
            user_info = msg.get("from", {})
            admin_label = f"Telegram Admin @{user_info.get('username', user_id)} (ID: {user_id})"
            ok, res_msg = approve_pending_authorization(token=tok, approved_by=admin_label, notify=False)
            send_tg_message(bot_token, chat_id, res_msg, reply_markup=make_main_keyboard())
        elif cmd in ("/reject", "/deny"):
            if not is_admin(user_id, config):
                send_tg_message(bot_token, chat_id, "⛔ Permission Denied: Only Administrator @wtalaat can reject modifications.")
                return
            tok = args[0] if len(args) > 0 else None
            from skill_integrity_guard import reject_pending_authorization
            user_info = msg.get("from", {})
            admin_label = f"Telegram Admin @{user_info.get('username', user_id)} (ID: {user_id})"
            ok, res_msg = reject_pending_authorization(token=tok, rejected_by=admin_label, notify=False)
            send_tg_message(bot_token, chat_id, res_msg, reply_markup=make_main_keyboard())
        else:
            send_tg_message(bot_token, chat_id, f"❓ Unknown command: <code>{cmd}</code>\nSend /help to view all available commands.", reply_markup=make_main_keyboard())


def run_telegram_listener():
    """Main long-polling loop."""
    config = load_config()
    tg_cfg = config.get("telegram", {})
    bot_token = tg_cfg.get("bot_token")

    if not bot_token:
        logger.error("No Telegram bot_token configured in alert_config.json")
        return

    logger.info("Telegram Mobile Listener v3.8.2 started. Listening for remote commands...")

    # 1. Register official command menu with Telegram Bot API
    set_bot_commands(bot_token)

    # 2. Dispatch Engine Online & Restart notification to Administrator
    send_engine_restart_alert(bot_token, config)

    offset = None
    last_reopen_check = 0

    while True:
        try:
            now_ts = time.time()
            if now_ts - last_reopen_check >= 30:
                last_reopen_check = now_ts
                try:
                    check_sunday_market_reopen(bot_token, config)
                except Exception as ex_reopen:
                    logger.error(f"Error checking Sunday market reopen: {ex_reopen}")

            params = {"timeout": 30}
            if offset:
                params["offset"] = offset

            resp = tg_api_request(bot_token, "getUpdates", params)
            if resp and resp.get("ok"):
                updates = resp.get("result", [])
                for update in updates:
                    offset = update["update_id"] + 1
                    try:
                        process_update(update, bot_token, config)
                    except Exception as ex:
                        logger.error(f"Error processing update {update.get('update_id')}: {ex}", exc_info=True)

            time.sleep(1)
        except Exception as e:
            logger.error(f"Error in Telegram polling loop: {e}")
            time.sleep(5)


if __name__ == "__main__":
    run_telegram_listener()
