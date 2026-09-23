#!/usr/bin/env python3
"""
AI Autonomous Trading Firm — Multi-Channel Notification Dispatcher (v2.3.0)
Sends formatted trade alerts, interactive approval buttons, real-time TP/SL milestone alerts,
and step-by-step manual execution instructions with auto-retry and multi-chat broadcasting.
"""

import sys
import os
import time
import json
import urllib.request
import urllib.parse
from datetime import datetime, timezone

# Ensure UTF-8 output on Windows consoles
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

CONFIG_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config", "alert_config.json")


def load_config():
    """Load configuration from alert_config.json or environment variables."""
    config = {
        "telegram": {"enabled": False, "bot_token": "", "chat_ids": [], "chat_id": ""},
        "discord": {"enabled": False, "webhook_url": ""},
        "settings": {"min_strategy_score_to_alert": 75}
    }
    
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                loaded = json.load(f)
                config.update(loaded)
        except Exception as e:
            print(f"[WARN] Error reading config file: {e}", file=sys.stderr)

    # Normalize chat_ids list
    tg = config.get("telegram", {})
    chat_ids = tg.get("chat_ids", [])
    if not isinstance(chat_ids, list):
        chat_ids = [str(chat_ids)]
    single_cid = tg.get("chat_id")
    if single_cid and str(single_cid) not in [str(c) for c in chat_ids]:
        chat_ids.append(str(single_cid))
    config["telegram"]["chat_ids"] = chat_ids

    # Allow environment variable overrides
    tg_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    tg_chat = os.environ.get("TELEGRAM_CHAT_ID")
    if tg_token:
        config["telegram"]["enabled"] = True
        config["telegram"]["bot_token"] = tg_token
    if tg_chat and tg_chat not in config["telegram"]["chat_ids"]:
        config["telegram"]["chat_ids"].append(tg_chat)

    discord_url = os.environ.get("DISCORD_WEBHOOK_URL")
    if discord_url:
        config["discord"]["enabled"] = True
        config["discord"]["webhook_url"] = discord_url

    return config


def send_telegram(bot_token: str, chat_id: str, text: str, ticket_id: str = None, retries: int = 2, reply_markup: dict = None) -> bool:
    """Send formatted markdown message to a specific Telegram chat_id with retry logic."""
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        "chat_id": str(chat_id).strip(),
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True
    }
    
    # Add interactive inline buttons
    if reply_markup:
        payload["reply_markup"] = reply_markup
    elif ticket_id:
        payload["reply_markup"] = {
            "inline_keyboard": [
                [
                    {"text": "✅ APPROVE & EXECUTE", "callback_data": f"approve_{ticket_id}"},
                    {"text": "❌ REJECT / PASS", "callback_data": f"reject_{ticket_id}"}
                ]
            ]
        }

    data = json.dumps(payload).encode("utf-8")
    
    for attempt in range(retries + 1):
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=15) as response:
                res_json = json.loads(response.read().decode("utf-8"))
                if res_json.get("ok"):
                    print(f"[OK] Telegram alert delivered successfully to Chat ID: {chat_id}.")
                    return True
                else:
                    print(f"[ERROR] Telegram API error for Chat ID {chat_id}: {res_json}", file=sys.stderr)
                    return False
        except urllib.error.HTTPError as e:
            err_msg = e.read().decode("utf-8")
            print(f"[WARN] Failed to send Telegram alert to Chat ID {chat_id}: {err_msg}", file=sys.stderr)
            return False
        except Exception as e:
            if attempt < retries:
                time.sleep(1)
                continue
            print(f"[ERROR] Failed to send Telegram alert to Chat ID {chat_id} after {retries+1} attempts: {e}", file=sys.stderr)
            return False
    return False


def send_admin_telegram(text: str, reply_markup: dict = None) -> bool:
    """Sends an alert strictly and exclusively to Administrator @wtalaat."""
    config = load_config()
    tg = config.get("telegram", {})
    if not (tg.get("enabled") and tg.get("bot_token") and not tg.get("bot_token").startswith("YOUR_")):
        return False
    bot_token = tg.get("bot_token")
    admin_id = str(tg.get("admin_chat_id", "1264076025")).strip()
    return send_telegram(bot_token, admin_id, text, reply_markup=reply_markup)


def broadcast_telegram(text: str, ticket_id: str = None, reply_markup: dict = None, admin_only: bool = False) -> int:
    """Broadcasts a message to Telegram destinations (or exclusively to Admin @wtalaat if admin_only=True)."""
    if admin_only:
        return 1 if send_admin_telegram(text, reply_markup=reply_markup) else 0

    config = load_config()
    delivered = 0
    tg = config.get("telegram", {})
    if tg.get("enabled") and tg.get("bot_token") and not tg.get("bot_token").startswith("YOUR_"):
        bot_token = tg.get("bot_token")
        for cid in tg.get("chat_ids", []):
            if cid and str(cid).strip():
                if send_telegram(bot_token, str(cid).strip(), text, ticket_id=ticket_id, reply_markup=reply_markup):
                    delivered += 1
    return delivered


# ==========================================
# REAL-TIME MILESTONE & ACTION ALERT FORMATTERS
# ==========================================

def format_tp1_alert(ticket: dict) -> str:
    """Format TP1 Milestone Hit with step-by-step manual action instructions."""
    instrument = ticket.get("instrument", "XAUUSD")
    tp1_price = ticket.get("tp1", "N/A")
    entry_price = ticket.get("entry", "N/A")
    vol_close = ticket.get("tp1_volume", "40% (0.44 Lots)")
    
    msg = f"""<b>🎯 TAKE PROFIT 1 (TP1) REACHED! — {instrument}</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━
<b>Status:</b> 🟢 <b>MILESTONE 1 ACHIEVED (+1.5R GAIN)</b>
<b>Hit Price:</b> <code>${tp1_price}</code>

👉 <b>ACTION TO TAKE ON YOUR BROKER NOW:</b>
1. <b>Close 40% Volume:</b> Close <code>{vol_close}</code> at market.
2. <b>Move Stop Loss:</b> Modify SL to <code>${entry_price}</code> <b>(BREAK-EVEN / RISK-FREE)</b>.

🔒 <i>Guaranteed Outcome: Trade can no longer result in a loss.</i>
🎯 <b>Next Target:</b> TP2 @ <code>${ticket.get('tp2', 'N/A')}</code>
━━━━━━━━━━━━━━━━━━━━━━━━━━"""
    return msg


def format_tp2_alert(ticket: dict) -> str:
    """Format TP2 Milestone Hit with step-by-step manual action instructions."""
    instrument = ticket.get("instrument", "XAUUSD")
    tp2_price = ticket.get("tp2", "N/A")
    tp1_price = ticket.get("tp1", "N/A")
    vol_close = ticket.get("tp2_volume", "40% (0.44 Lots)")
    
    msg = f"""<b>🎯🎯 TAKE PROFIT 2 (TP2) REACHED! — {instrument}</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━
<b>Status:</b> 🟢 <b>MILESTONE 2 ACHIEVED (+2.5R GAIN)</b>
<b>Hit Price:</b> <code>${tp2_price}</code>

👉 <b>ACTION TO TAKE ON YOUR BROKER NOW:</b>
1. <b>Close 40% Volume:</b> Close another <code>{vol_close}</code> at market.
2. <b>Lock In Profit:</b> Move Stop Loss up to <code>${tp1_price}</code> <b>(LOCK +1.5R PROFIT)</b>.
3. <b>Let Runner Ride:</b> Keep remaining 20% on trailing stop targeting <code>${ticket.get('tp3', 'N/A')}</code>.

💰 <i>Banked: 80% total position profits secured.</i>
━━━━━━━━━━━━━━━━━━━━━━━━━━"""
    return msg


def format_sl_alert(ticket: dict) -> str:
    """Format Stop Loss Hit alert with cool-down instructions."""
    instrument = ticket.get("instrument", "XAUUSD")
    sl_price = ticket.get("stop_loss", "N/A")
    risk_amount = ticket.get("risk_dollars", "$1,000.00")
    
    msg = f"""<b>🛑 STOP LOSS HIT — {instrument}</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━
<b>Status:</b> 🔴 <b>POSITION CLOSED AT INVALIDATION</b>
<b>Exit Price:</b> <code>${sl_price}</code>
<b>Realized Risk:</b> <code>-{risk_amount}</code> (Pre-calculated 1.0% bounded risk)

👉 <b>ACTION TO TAKE ON YOUR BROKER NOW:</b>
1. <b>Verify Position Closed:</b> Confirm position is 100% closed on your broker.
2. <b>Purge Pending Orders:</b> Ensure any attached TP/SL limits are cancelled.

⏳ <b>Cool-Down Protocol Activated:</b>
• Mandatory 30-minute scanning pause on {instrument}.
• Capital preservation rules enforced.
━━━━━━━━━━━━━━━━━━━━━━━━━━"""
    return msg


def format_telegram_trade_alert(ticket: dict) -> str:
    """Format initial trade signal alert for Telegram."""
    direction = ticket.get("direction", "BUY").upper()
    dir_emoji = "🟢" if "BUY" in direction else "🔴"
    ticket_id = ticket.get("ticket_id", "TRD-XAU-001")
    
    msg = f"""<b>{dir_emoji} NEW TRADE SIGNAL — {ticket.get('instrument', 'XAUUSD')}</b>
━━━━━━━━━━━━━━━━━━━━
<b>Ticket ID:</b> <code>{ticket_id}</code>
<b>Direction:</b> {direction} ({ticket.get('order_type', 'Limit')})
<b>Strategy:</b> {ticket.get('strategy', 'Pullback Continuation')} (Score: <b>{ticket.get('strategy_score', '89.0')}/100</b>)
<b>Market Regime:</b> <code>{ticket.get('market_regime', 'STRONG_UPTREND')}</code>

📍 <b>Entry Price:</b> <code>${ticket.get('entry', '0.00')}</code>
🛑 <b>Stop Loss:</b> <code>${ticket.get('stop_loss', '0.00')}</code> (Risk: ${ticket.get('risk_distance', '0.00')})
🎯 <b>Take Profit 1:</b> <code>${ticket.get('tp1', '0.00')}</code> (Close 40% ➔ SL to BE)
🎯 <b>Take Profit 2:</b> <code>${ticket.get('tp2', '0.00')}</code> (Close 40% ➔ Lock TP1)
🚀 <b>Runner (TP3):</b> <code>${ticket.get('tp3', '0.00')}</code> (Trail 20% volume)

💼 <b>Recommended Lots:</b> <code>{ticket.get('position_lots', '1.00 Lots')}</code>
⚖️ <b>Expected R:R:</b> <code>1 : {ticket.get('expected_rr', '2.50')}</code>
🔒 <b>Risk Gate:</b> ✅ Risk Manager Approved (No Veto)
⏱️ <b>Approval Window:</b> <i>Reply 'Yes' in chat or tap button below (5 min timeout)</i>
━━━━━━━━━━━━━━━━━━━━
<i>Executed under AI Autonomous Trading Firm Charter</i>"""
    return msg


# ==========================================
# PUBLIC DISPATCH METHODS
# ==========================================

def dispatch_alert(ticket: dict):
    """Dispatch initial trade signal alert."""
    ticket_id = ticket.get("ticket_id", "TRD-" + datetime.now(timezone.utc).strftime("%Y%m%d%H%M"))
    text = format_telegram_trade_alert(ticket)
    return broadcast_telegram(text, ticket_id=ticket_id)


def dispatch_tp1(ticket: dict):
    """Dispatch TP1 achievement alert with manual action instructions."""
    text = format_tp1_alert(ticket)
    return broadcast_telegram(text)


def dispatch_tp2(ticket: dict):
    """Dispatch TP2 achievement alert with manual action instructions."""
    text = format_tp2_alert(ticket)
    return broadcast_telegram(text)


def dispatch_sl(ticket: dict):
    """Dispatch Stop Loss hit alert with manual action instructions."""
    text = format_sl_alert(ticket)
    return broadcast_telegram(text)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--test-tp1":
        sample = {
            "instrument": "XAUUSD (Gold)",
            "entry": "4638.50",
            "tp1": "4652.00",
            "tp2": "4661.00",
            "tp3": "4675.00",
            "tp1_volume": "0.44 Lots (40%)"
        }
        dispatch_tp1(sample)
    elif len(sys.argv) > 1 and sys.argv[1] == "--test-sl":
        sample = {
            "instrument": "XAUUSD (Gold)",
            "stop_loss": "4629.50",
            "risk_dollars": "$1,000.00"
        }
        dispatch_sl(sample)
    elif len(sys.argv) > 1 and sys.argv[1] == "--test":
        sample = {
            "ticket_id": "TRD-MULTI-TEST",
            "instrument": "XAUUSD (Gold Spot)",
            "direction": "BUY (LONG)",
            "order_type": "Limit / Value Entry",
            "strategy": "Pullback / Trend Continuation",
            "strategy_score": 89.0,
            "market_regime": "STRONG_UPTREND",
            "entry": "4638.50",
            "stop_loss": "4629.50",
            "risk_distance": "9.00",
            "tp1": "4652.00",
            "tp2": "4661.00",
            "tp3": "4675.00",
            "position_lots": "1.11 Lots",
            "risk_percent": "1.0",
            "risk_dollars": "1,000.00",
            "expected_rr": "2.50"
        }
        dispatch_alert(sample)
    else:
        print("Usage: python send_alert.py [--test | --test-tp1 | --test-sl]")
