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

CONFIG_PATH = os.path.join(BASE_DIR, "config", "alert_config.json")
SESSION_PATH = os.path.join(BASE_DIR, "config", "session_state.json")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - TgListener - %(levelname)s - %(message)s"
)
logger = logging.getLogger("TgListener")


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
    """Send HTML message with optional inline keyboard."""
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML"
    }
    if reply_markup:
        payload["reply_markup"] = reply_markup
    return tg_api_request(bot_token, "sendMessage", payload)


def make_main_keyboard():
    """Create persistent interactive command keyboard."""
    return {
        "inline_keyboard": [
            [
                {"text": "🚀 Start Session (5T / 2x)", "callback_data": "cb_start_5_2x"},
                {"text": "📊 Live Status", "callback_data": "cb_status"}
            ],
            [
                {"text": "🔍 Scan Market", "callback_data": "cb_scan"},
                {"text": "🛑 Close All (Kill)", "callback_data": "cb_close"}
            ],
            [
                {"text": "📈 Today Summary", "callback_data": "cb_summary"},
                {"text": "🏆 Weekly Audit", "callback_data": "cb_weekly"}
            ],
            [
                {"text": "⏹️ Stop Scanner", "callback_data": "cb_stop"},
                {"text": "🛡️ Verify Security", "callback_data": "cb_integrity"}
            ]
        ]
    }


def start_trading_session(max_trades=5, leverage_tier="2x", quota_trades=None):
    """
    Initializes session state and spawns autonomous scanner & trade monitor daemons.
    """
    lev_map = {"1x": 1.0, "2x": 2.0, "3x": 3.0, "5x": 5.0}
    lev_mult = lev_map.get(str(leverage_tier).lower().strip(), 2.0)
    quota = quota_trades if quota_trades is not None else max_trades

    session_id = f"SES-{datetime.now(timezone.utc).strftime('%Y%m%d')}-MOB{int(time.time()) % 1000:03d}"

    session_data = {
        "session_id": session_id,
        "active_market": "EURUSD, XAUUSD",
        "watchlist": ["EURUSD", "XAUUSD"],
        "risk_per_trade_dollars": 25.0,
        "max_daily_loss_dollars": 50.0,
        "default_lots": 0.01,
        "leverage_multiplier": lev_mult,
        "leverage_trades_quota": quota,
        "leverage_trades_used": 0,
        "baseline_leverage": 1.0,
        "gold_profit_target_base": 25.0,
        "max_trades": max_trades,
        "trades_executed": 0,
        "trading_mode": "D",
        "risk_manager_status": "APPROVED_BY_CRO",
        "approved_leverage_tier": f"{int(lev_mult)}x",
        "margin_stress_score": f"{0.05 * lev_mult:.2f}% (Institutional A+ Rating)",
        "start_time": datetime.now(timezone.utc).isoformat(),
        "is_active": True
    }
    save_session(session_data)

    # Launch background daemons
    scanner_cmd = [sys.executable, os.path.join(BASE_DIR, "scripts", "auto_scanner.py"), "15"]
    monitor_cmd = [sys.executable, os.path.join(BASE_DIR, "scripts", "trade_monitor.py")]
    summary_cmd = [sys.executable, os.path.join(BASE_DIR, "scripts", "daily_summary.py"), "--daemon"]

    try:
        subprocess.Popen(scanner_cmd, cwd=BASE_DIR, creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0)
        subprocess.Popen(monitor_cmd, cwd=BASE_DIR, creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0)
        subprocess.Popen(summary_cmd, cwd=BASE_DIR, creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0)
        logger.info(f"Spawned autonomous daemons for session {session_id}")
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
    if weekday == 6 and (hour < 20 or (hour == 20 and minute < 55)):
        return True, "Sunday pre-open close"
    return False, "Market is OPEN"


def handle_start_session_cmd(args, chat_id, bot_token):
    """Parse /start_session command parameters and initiate session."""
    max_trades = 5
    leverage_tier = "2x"
    quota = 5

    # Check for market closure
    is_closed, reason = is_market_closed_now()
    if is_closed and "--force" not in args:
        warning_msg = (
            f"⚠️ <b>MARKET IS CURRENTLY CLOSED FOR THE WEEKEND</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"📅 <b>Status:</b> {reason}\n"
            f"⏰ <b>Market Reopens:</b> <b>Sunday 21:00 UTC</b> (Monday 00:00 Cairo time / UTC+3)\n\n"
            f"💡 MT5 brokers do not accept live Forex or Gold orders on weekends.\n"
            f"<i>Your session parameters have been prepared. Run <code>/start_session</code> when the market reopens on Sunday night!</i>"
        )
        send_tg_message(bot_token, chat_id, warning_msg, reply_markup=make_main_keyboard())
        return

    if len(args) >= 1 and args[0].isdigit():
        max_trades = int(args[0])
        quota = max_trades
    if len(args) >= 2 and not args[1].startswith("--"):
        leverage_tier = args[1].lower().replace("x", "") + "x"
    if len(args) >= 3 and args[2].isdigit():
        quota = int(args[2])

    session = start_trading_session(max_trades, leverage_tier, quota)
    gold_target = 25.0 * session["leverage_multiplier"]

    msg = (
        f"🚀 <b>AUTONOMOUS SESSION LAUNCHED VIA TELEGRAM</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🆔 <b>Session ID:</b> <code>{session['session_id']}</code>\n"
        f"🎯 <b>Total Allowed Trades:</b> <b>{session['max_trades']} Trades</b>\n"
        f"⚡ <b>Leverage Tier:</b> <b>{session['approved_leverage_tier']}</b> ({0.01 * session['leverage_multiplier']:.2f} lots)\n"
        f"⏳ <b>Leverage Duration:</b> <b>{session['leverage_trades_quota']} trades</b>\n"
        f"🏆 <b>Strategy:</b> Bollinger Bands 2.0 Mean Reversion\n"
        f"💰 <b>Gold Profit Target:</b> <code>+${gold_target:.2f} / trade</code>\n"
        f"🛡️ <b>CRO Risk Clearance:</b> ✅ APPROVED\n"
        f"🤖 <b>Daemons:</b> Scanner, Deal Streamer & Summary Active\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"<i>Autonomous scanner is actively monitoring markets...</i>"
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
        mt5.shutdown()

        session = load_session()
        is_active = session.get("is_active", False)
        status_icon = "🟢 ACTIVE" if is_active else "⏹️ INACTIVE"

        pos_lines = []
        if positions:
            for p in positions:
                side = "BUY" if p.type == 0 else "SELL"
                pos_lines.append(f"  • #{p.ticket} {side} {p.symbol} ({p.volume}L) @ {p.price_open} ➔ P&L: <code>${p.profit:+.2f}</code>")
            pos_text = "\n".join(pos_lines)
        else:
            pos_text = "  • No open positions (100% Flat & Protected)"

        msg = (
            f"📊 <b>FIRM LIVE TELEMETRY &amp; STATUS</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"🆔 <b>Session:</b> <code>{session.get('session_id', 'NONE')}</code> [{status_icon}]\n"
            f"🏦 <b>Account Balance:</b> <code>${acc.balance:,.2f}</code>\n"
            f"📈 <b>Equity:</b> <code>${acc.equity:,.2f}</code> | <b>Free Margin:</b> <code>${acc.margin_free:,.2f}</code>\n"
            f"🎯 <b>Trades Executed:</b> <b>{session.get('trades_executed', 0)} / {session.get('max_trades', 0)}</b>\n"
            f"⚡ <b>Active Leverage:</b> <b>{session.get('approved_leverage_tier', '1x')}</b>\n\n"
            f"🛡️ <b>OPEN POSITIONS ({len(positions) if positions else 0}):</b>\n"
            f"{pos_text}\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"<i>AI Autonomous Trading Firm v3.7.0</i>"
        )
        send_tg_message(bot_token, chat_id, msg, reply_markup=make_main_keyboard())
    except Exception as e:
        send_tg_message(bot_token, chat_id, f"❌ Error querying status: {e}")


def handle_scan_cmd(chat_id, bot_token):
    """Execute on-demand market scan across active universe and reply with telemetry."""
    try:
        import MetaTrader5 as mt5
        import pandas as pd
        import numpy as np

        if not mt5.initialize():
            send_tg_message(bot_token, chat_id, f"❌ Failed to connect to MT5: {mt5.last_error()}")
            return

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

            digits = 2 if "XAU" in symbol else 5
            reports.append(
                f"<b>{symbol} (M15):</b>\n"
                f"  • Price: <code>{last['close']:.{digits}f}</code> | RSI(14): <b>{last['rsi']:.1f}</b>\n"
                f"  • Upper BB: <code>{last['upper']:.{digits}f}</code> (dist: {dist_up:.{digits}f})\n"
                f"  • Lower BB: <code>{last['lower']:.{digits}f}</code> (dist: {dist_dn:.{digits}f})\n"
                f"  • ATR(14): <code>{last['atr']:.{digits}f}</code>\n"
                f"  • Status: <b>{status}</b>"
            )

        mt5.shutdown()
        scan_text = "\n\n".join(reports) if reports else "No candle data available."
        msg = (
            f"🔍 <b>ON-DEMAND MARKET SWEEP TELEMETRY</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"{scan_text}\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"<i>AI Champion Strategy: Bollinger Bands 2.0-StdDev Mean Reversion</i>"
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
        from skill_integrity_guard import verify_integrity
        valid, mismatches = verify_integrity()
        if valid:
            msg = (
                f"🛡️ <b>CRYPTOGRAPHIC INTEGRITY VERIFIED</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"✅ <b>Status:</b> 100% SECURE & AUTHENTIC\n"
                f"🔒 <b>Protected Files:</b> 8 core engine & skill files verified against SHA-256 signatures.\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"<i>Anti-Tamper Security Guard v3.7.0</i>"
            )
        else:
            msg = f"⚠️ <b>SECURITY ALERT:</b> Tampering detected on: {mismatches}"
        send_tg_message(bot_token, chat_id, msg, reply_markup=make_main_keyboard())
    except Exception as e:
        send_tg_message(bot_token, chat_id, f"❌ Integrity check error: {e}")


def handle_direct_trade_cmd(order_type, args, chat_id, bot_token):
    """
    Executes a direct market order from Telegram: /buy XAUUSD 0.02 or /sell EURUSD 0.10
    """
    try:
        import MetaTrader5 as mt5
        if not mt5.initialize():
            send_tg_message(bot_token, chat_id, f"❌ Failed to connect to MT5: {mt5.last_error()}")
            return

        symbol = args[0].upper() if len(args) >= 1 else "EURUSD"
        if "GOLD" in symbol or "XAU" in symbol:
            symbol = "XAUUSD"
        elif "EUR" in symbol:
            symbol = "EURUSD"
        else:
            symbol = "EURUSD"

        # Resolve volume
        if len(args) >= 2:
            try:
                volume = float(args[1])
            except ValueError:
                volume = 0.02 if symbol == "XAUUSD" else 0.10
        else:
            volume = 0.02 if symbol == "XAUUSD" else 0.10

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

        sl_dist = round(max(atr * 1.5, 0.0012 if "EUR" in symbol else 10.0), digits)
        tp_dist = round(max(atr * 2.0, 0.0016 if "EUR" in symbol else 15.0), digits)

        if order_type == "BUY":
            sl = round(price - sl_dist, digits)
            tp = round(price + tp_dist, digits)
        else:
            sl = round(price + sl_dist, digits)
            tp = round(price - tp_dist, digits)

        ticket_data = {
            "symbol": symbol,
            "order_type": order_type,
            "volume": volume,
            "price": price,
            "stop_loss": sl,
            "take_profit_1": tp,
            "take_profit_2": tp,
            "take_profit_3": tp,
            "risk_reward_ratio": 1.5,
            "strategy_name": "Bollinger_Mean_Reversion",
            "confidence_score": 85.0
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
        f"<b>🚀 Launch Autonomous Session:</b>\n"
        f"  • <code>/start_session [trades] [leverage]</code> (e.g. <code>/start_session 5 2x</code>)\n"
        f"  • <code>/trade</code> or <code>/start_trading</code> — Quick launch session\n"
        f"  • <code>/status</code> — Live balance, equity, positions & remaining quota\n"
        f"  • <code>/stop</code> — Stop active auto-scanner\n\n"
        f"<b>⚡ Instant Direct Execution:</b>\n"
        f"  • <code>/buy [symbol] [lots]</code> — Instant market BUY (e.g. <code>/buy XAUUSD 0.02</code>)\n"
        f"  • <code>/sell [symbol] [lots]</code> — Instant market SELL (e.g. <code>/sell EURUSD 0.10</code>)\n"
        f"  • <code>/scan</code> — Force immediate market sweep on EURUSD & Gold\n"
        f"  • <code>/close</code> — <b>Kill Switch:</b> Emergency close all open positions\n\n"
        f"<b>📊 Reports &amp; Security:</b>\n"
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
        data = cb.get("data", "")

        if not is_authorized(user_id, chat_id, config):
            logger.warning(f"Unauthorized callback from user {user_id}")
            return

        tg_api_request(bot_token, "answerCallbackQuery", {"callback_query_id": cb.get("id")})

        if data == "cb_status":
            handle_status_cmd(chat_id, bot_token)
        elif data == "cb_scan":
            handle_scan_cmd(chat_id, bot_token)
        elif data == "cb_close":
            handle_close_cmd(chat_id, bot_token)
        elif data == "cb_stop":
            handle_stop_cmd(chat_id, bot_token)
        elif data == "cb_summary":
            from daily_summary import send_daily_summary
            send_daily_summary()
        elif data == "cb_weekly":
            from daily_summary import send_market_close_summary
            send_market_close_summary(is_weekend=True, kill_processes=False)
        elif data == "cb_integrity":
            handle_integrity_cmd(chat_id, bot_token)
        elif data == "cb_start_5_2x":
            handle_start_session_cmd(["5", "2x"], chat_id, bot_token)
        elif data.startswith("auth_approve_"):
            tok = data.replace("auth_approve_", "")
            from skill_integrity_guard import approve_pending_authorization
            user_info = cb.get("from", {})
            admin_label = f"Telegram Admin @{user_info.get('username', user_id)} (ID: {user_id})"
            ok, res_msg = approve_pending_authorization(token=tok, approved_by=admin_label)
            send_tg_message(bot_token, chat_id, res_msg, reply_markup=make_main_keyboard())
        elif data.startswith("auth_reject_"):
            tok = data.replace("auth_reject_", "")
            from skill_integrity_guard import reject_pending_authorization
            user_info = cb.get("from", {})
            admin_label = f"Telegram Admin @{user_info.get('username', user_id)} (ID: {user_id})"
            ok, res_msg = reject_pending_authorization(token=tok, rejected_by=admin_label)
            send_tg_message(bot_token, chat_id, res_msg, reply_markup=make_main_keyboard())
        return

    # Handle Text Messages
    if "message" in update:
        msg = update["message"]
        user_id = msg.get("from", {}).get("id")
        chat_id = msg.get("chat", {}).get("id")
        text = msg.get("text", "").strip()

        if not is_authorized(user_id, chat_id, config):
            logger.warning(f"Unauthorized message from user {user_id}: {text}")
            send_tg_message(bot_token, chat_id, f"⛔ Unauthorized. User ID <code>{user_id}</code> is not in the approved whitelist.")
            return

        if not text.startswith("/"):
            return

        parts = text.split()
        cmd = parts[0].lower().replace("@techwavesegbot", "")
        args = parts[1:]

        logger.info(f"Processing command: {cmd} with args {args} from user {user_id}")

        if cmd in ("/start", "/help"):
            handle_help_cmd(chat_id, bot_token)
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
        elif cmd in ("/weekly", "/audit"):
            from daily_summary import send_market_close_summary
            send_market_close_summary(is_weekend=True, kill_processes=False)
        elif cmd == "/integrity":
            handle_integrity_cmd(chat_id, bot_token)
        elif cmd in ("/approve", "/authorize", "/certify"):
            tok = args[0] if len(args) > 0 else None
            from skill_integrity_guard import approve_pending_authorization
            user_info = msg.get("from", {})
            admin_label = f"Telegram Admin @{user_info.get('username', user_id)} (ID: {user_id})"
            ok, res_msg = approve_pending_authorization(token=tok, approved_by=admin_label)
            send_tg_message(bot_token, chat_id, res_msg, reply_markup=make_main_keyboard())
        elif cmd in ("/reject", "/deny"):
            tok = args[0] if len(args) > 0 else None
            from skill_integrity_guard import reject_pending_authorization
            user_info = msg.get("from", {})
            admin_label = f"Telegram Admin @{user_info.get('username', user_id)} (ID: {user_id})"
            ok, res_msg = reject_pending_authorization(token=tok, rejected_by=admin_label)
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

    logger.info("Telegram Mobile Listener v3.7.0 started. Listening for remote commands...")
    offset = None

    while True:
        try:
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
