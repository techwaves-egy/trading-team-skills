#!/usr/bin/env python3
"""
AI Autonomous Trading Firm — Real-Time Trade Closure & Result Monitor (v3.8.0)
Monitors MT5 deal stream in real-time (every 3 seconds).
Features:
  1. Real-time deal stream closure alerts to Telegram (TP, SL, BE, Manual).
  2. 80/70 Asymmetric Profit Protection Engine:
     - Arms when active trade reaches >= 80% of TP distance.
     - Automatically closes position at market if price retraces to <= 70% of TP distance to lock in the win!
"""

import sys
import os
import time
import json
import logging
from datetime import datetime, timezone, timedelta

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from send_alert import broadcast_telegram
from mt5_connector import close_position
import MetaTrader5 as mt5

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - TradeMonitor - %(levelname)s - %(message)s"
)
logger = logging.getLogger("TradeMonitor")

PROCESSED_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config", "processed_deal_tickets.json")
PROTECTION_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config", "profit_protection_state.json")


def load_processed_tickets():
    if os.path.exists(PROCESSED_FILE):
        try:
            with open(PROCESSED_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                return set(data.get("tickets", []))
        except Exception as e:
            logger.error(f"Error loading processed tickets: {e}")
    return set()


def save_processed_tickets(ticket_set):
    os.makedirs(os.path.dirname(PROCESSED_FILE), exist_ok=True)
    with open(PROCESSED_FILE, "w", encoding="utf-8") as f:
        recent = list(ticket_set)[-500:]
        json.dump({"tickets": recent, "updated": datetime.now(timezone.utc).isoformat()}, f, indent=2)


def load_profit_protection_state():
    if os.path.exists(PROTECTION_FILE):
        try:
            with open(PROTECTION_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error loading profit protection state: {e}")
    return {}


def save_profit_protection_state(state):
    os.makedirs(os.path.dirname(PROTECTION_FILE), exist_ok=True)
    with open(PROTECTION_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)


def calculate_tp_progress(pos):
    """
    Computes progress towards Take Profit:
    0.0 = at entry price
    1.0 = at full TP
    Returns: (progress: float, total_tp_dist: float, current_dist: float)
    """
    if pos.tp <= 0:
        return 0.0, 0.0, 0.0

    if pos.type == mt5.ORDER_TYPE_BUY:
        total_dist = pos.tp - pos.price_open
        if total_dist <= 0:
            return 0.0, 0.0, 0.0
        current_dist = pos.price_current - pos.price_open
        progress = current_dist / total_dist
    elif pos.type == mt5.ORDER_TYPE_SELL:
        total_dist = pos.price_open - pos.tp
        if total_dist <= 0:
            return 0.0, 0.0, 0.0
        current_dist = pos.price_open - pos.price_current
        progress = current_dist / total_dist
    else:
        return 0.0, 0.0, 0.0

    return progress, total_dist, current_dist


def check_and_execute_profit_protection(positions, protection_state):
    """
    Evaluates 80/70 Asymmetric Profit Protection across all open positions:
    1. When progress >= 0.80 (80% of TP distance): Position is ARMED.
    2. When armed and progress <= 0.70: Position is IMMEDIATELY CLOSED AT MARKET on profit!
    """
    active_tickets = set()
    state_modified = False

    for pos in positions:
        ticket_str = str(pos.ticket)
        active_tickets.add(ticket_str)

        if pos.tp <= 0:
            continue

        progress, total_dist, current_dist = calculate_tp_progress(pos)
        pos_dir = "BUY" if pos.type == mt5.ORDER_TYPE_BUY else "SELL"

        if ticket_str not in protection_state:
            protection_state[ticket_str] = {
                "symbol": pos.symbol,
                "direction": pos_dir,
                "open_price": pos.price_open,
                "tp_price": pos.tp,
                "armed": False,
                "peak_progress": max(0.0, progress),
                "armed_at": None
            }
            state_modified = True

        entry = protection_state[ticket_str]
        entry["peak_progress"] = max(entry.get("peak_progress", 0.0), progress)

        # Gate 1: Check Arming Threshold (>= 80% of TP)
        if progress >= 0.80 and not entry.get("armed", False):
            entry["armed"] = True
            entry["armed_at"] = datetime.now(timezone.utc).isoformat()
            state_modified = True
            logger.info(
                f"[PROFIT PROTECTION ARMED] Position #{pos.ticket} ({pos.symbol} {pos_dir}) reached "
                f"{progress * 100:.1f}% of TP distance. Retracement protection armed at 70% floor!"
            )

        # Gate 2: Check Retracement Exit Threshold (Armed + <= 70% of TP)
        if entry.get("armed", False) and progress <= 0.70:
            peak_pct = entry.get("peak_progress", progress) * 100
            current_pct = progress * 100
            logger.warning(
                f"[PROFIT PROTECTION TRIGGERED] Position #{pos.ticket} ({pos.symbol} {pos_dir}) retraced to "
                f"{current_pct:.1f}% after peak {peak_pct:.1f}%. Executing immediate market close to lock in win!"
            )

            res = close_position(pos.ticket)
            if res.get("status") == "SUCCESS":
                profit = pos.profit
                alert_msg = (
                    f"🎯 <b>PROFIT PROTECTION WIN EXIT (80% ➔ 70% RETRACEMENT)</b>\n"
                    f"━━━━━━━━━━━━━━━━━━━━\n"
                    f"<b>Asset:</b> <code>{pos.symbol}</code> ({pos_dir})\n"
                    f"<b>Action:</b> <b>PROFIT LOCKED IN AT MARKET</b>\n"
                    f"<b>Peak Distance Reached:</b> <code>{peak_pct:.1f}%</code> of TP\n"
                    f"<b>Exit Retracement:</b> <code>{current_pct:.1f}%</code> of TP\n"
                    f"<b>Execution Price:</b> <code>{pos.price_current}</code>\n"
                    f"<b>Floating P&L Secured:</b> <b>+${profit:,.2f} USD</b>\n"
                    f"<b>Deal Ticket:</b> <code>#{pos.ticket}</code>\n"
                    f"━━━━━━━━━━━━━━━━━━━━\n"
                    f"<i>Asymmetric Profit Guard: Protected win and prevented pullback to BE/loss.</i>"
                )
                broadcast_telegram(alert_msg)
                del protection_state[ticket_str]
                state_modified = True
            else:
                logger.error(f"Failed to execute profit protection close for #{pos.ticket}: {res.get('reason')}")

    # Clean up closed positions from state
    expired_tickets = [t for t in protection_state if t not in active_tickets]
    if expired_tickets:
        for t in expired_tickets:
            del protection_state[t]
        state_modified = True

    if state_modified:
        save_profit_protection_state(protection_state)


def determine_exit_type(deal):
    """Determine whether TP, SL, BE, Profit Protection, or Manual closed the deal."""
    comment = str(deal.comment).lower()
    profit = deal.profit + getattr(deal, "swap", 0.0) + getattr(deal, "fee", 0.0)

    if "[tp" in comment or "tp" in comment or deal.reason == getattr(mt5, "DEAL_REASON_TP", 5):
        return "TAKE_PROFIT_REACHED", "🎯 TAKE PROFIT REACHED"
    elif "[sl" in comment or "sl" in comment or deal.reason == getattr(mt5, "DEAL_REASON_SL", 4):
        if profit >= 0:
            return "BREAK_EVEN_EXIT", "🛡️ BREAK-EVEN / TRAILING STOP REACHED"
        else:
            return "STOP_LOSS_REACHED", "🛑 STOP LOSS REACHED"
    elif "close" in comment:
        if profit > 0:
            return "PROFIT_PROTECTION_EXIT", "🎯 TARGET / PROFIT PROTECTION EXIT"
        else:
            return "MANUAL_EXIT", "💼 MANUAL / SYSTEM CLOSE"
    else:
        if profit > 0:
            return "TAKE_PROFIT_REACHED", "🎯 TARGET / PROFIT EXIT"
        elif profit == 0:
            return "BREAK_EVEN_EXIT", "⚖️ BREAK-EVEN EXIT"
        else:
            return "STOP_LOSS_REACHED", "🛑 STOP LOSS / EXIT"


def format_telegram_alert(deal, account_info):
    """Format an institutional trade closure alert."""
    exit_key, exit_header = determine_exit_type(deal)
    symbol = deal.symbol
    pos_direction = "BUY" if deal.type == 1 else "SELL"
    profit = round(deal.profit + getattr(deal, "swap", 0.0) + getattr(deal, "fee", 0.0), 2)
    pnl_sign = "+" if profit >= 0 else ""
    pnl_str = f"{pnl_sign}${profit:,.2f}"

    price = deal.price
    volume = deal.volume
    close_time = datetime.fromtimestamp(deal.time, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    balance = account_info.balance if account_info else 0.0
    equity = account_info.equity if account_info else 0.0

    if profit > 0:
        badge = "🟢 PROFIT"
    elif profit == 0:
        badge = "⚪ BREAK-EVEN"
    else:
        badge = "🔴 LOSS"

    msg = f"""<b>{exit_header}</b>
━━━━━━━━━━━━━━━━━━━━
<b>Asset:</b> <code>{symbol}</code> ({pos_direction})
<b>Result:</b> <b>{badge} ({pnl_str})</b>
<b>Exit Price:</b> <code>{price}</code>
<b>Volume:</b> <code>{volume:.2f} Lots</code>
<b>Close Time:</b> <code>{close_time}</code>
<b>Deal Ticket:</b> <code>#{deal.ticket}</code> (Order #{deal.order})
━━━━━━━━━━━━━━━━━━━━
<b>Account Balance:</b> <code>${balance:,.2f}</code>
<b>Account Equity:</b> <code>${equity:,.2f}</code>
<b>Strategy Status:</b> 80/70 Profit Guard Protected (v3.8.0)"""

    return msg


def ensure_mt5_connected():
    """Verify live MT5 IPC connection and auto-reconnect if dropped."""
    try:
        if not mt5.terminal_info():
            logger.warning("[MT5 HEALTH] MT5 terminal not connected. Attempting reconnection...")
            if mt5.initialize():
                logger.info("[MT5 HEALTH] MT5 reconnected successfully.")
                return True
            else:
                logger.error(f"[MT5 HEALTH] MT5 reconnect failed: {mt5.last_error()}")
                return False
        return True
    except Exception as e:
        logger.error(f"[MT5 HEALTH] Connection check exception: {e}")
        try:
            return mt5.initialize()
        except Exception:
            return False


def monitor_loop():
    logger.info("Initializing Real-Time MT5 Trade Closure & Profit Protection Monitor (v3.8.8)...")
    if not ensure_mt5_connected():
        logger.error(f"Initial MT5 connection failed: {mt5.last_error()}")

    processed_tickets = load_processed_tickets()
    protection_state = load_profit_protection_state()

    logger.info(f"Trade Monitor ACTIVE — polling deal stream & 80/70 profit guard every 3 seconds ({len(processed_tickets)} processed deals tracked)...")

    last_heartbeat = time.time()

    while True:
        try:
            # 0. Health check & Auto-reconnect
            if not ensure_mt5_connected():
                time.sleep(3)
                continue

            # 1. Check 80/70 Asymmetric Profit Protection on Open Positions
            positions = mt5.positions_get()
            if positions:
                check_and_execute_profit_protection(positions, protection_state)

            # 2. Check Deal Stream for Closed Trades
            now_ts = int(time.time()) + 86400
            from_ts = now_ts - (86400 * 2)
            deals = mt5.history_deals_get(from_ts, now_ts)

            if deals is None:
                err = mt5.last_error()
                if err[0] != 1:
                    logger.warning(f"Failed to query history deals: {err}. Triggering reconnect...")
                    mt5.initialize()
            else:
                for deal in deals:
                    if deal.entry in [mt5.DEAL_ENTRY_OUT, getattr(mt5, "DEAL_ENTRY_OUT_BY", 2)] and deal.ticket not in processed_tickets:
                        logger.info(f"NEW CLOSED TRADE DETECTED: Deal #{deal.ticket} on {deal.symbol} | Profit: ${deal.profit:+.2f} ({deal.comment})")

                        account_info = mt5.account_info()
                        alert_msg = format_telegram_alert(deal, account_info)

                        broadcast_telegram(alert_msg)

                        processed_tickets.add(deal.ticket)
                        save_processed_tickets(processed_tickets)
                        logger.info(f"Alert delivered for Deal #{deal.ticket}.")

            # 3. Periodic Heartbeat (Every 10 minutes)
            if time.time() - last_heartbeat >= 600:
                pos_count = len(positions) if positions else 0
                logger.info(f"[HEARTBEAT] Monitor active. Open positions: {pos_count} | Processed deals: {len(processed_tickets)}")
                last_heartbeat = time.time()

        except Exception as e:
            logger.error(f"Error in monitor loop: {e}", exc_info=True)

        time.sleep(3)


if __name__ == "__main__":
    monitor_loop()
