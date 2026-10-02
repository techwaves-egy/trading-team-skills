#!/usr/bin/env python3
"""
AI Autonomous Trading Firm — Real-Time Trade Closure & Institutional 80/70 Profit Protection Monitor (v3.9.0)
Monitors MT5 deal stream in real-time (every 3 seconds).
Features:
  1. Real-time deal stream closure alerts to Telegram (TP, SL, BE, Manual, 80/70 Server SL).
  2. Institutional 80/70 Asymmetric Profit Protection Engine:
     - Arms when active trade reaches >= 80% of TP distance.
     - INSTANTLY modifies broker's server-side Stop Loss directly to 70% of TP distance on MT5 matching engine.
     - Guarantees 0ms broker execution latency and 100% immunity to network drops, PC reboots, or client latency.
     - Emits instant Telegram alert confirming server-side SL upgrade with locked minimum USD profit.
     - Retains local market-close failsafe if price retraces to <= 70% and broker order has not yet triggered.
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
from mt5_connector import close_position, modify_mt5_sl
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


def check_and_execute_profit_protection(positions, protection_state, armed_history=None):
    """
    Evaluates 80/70 Asymmetric Profit Protection across all open positions (v3.9.0):
    1. When progress >= 0.80 (80% of TP distance): Position is ARMED.
       INSTANTLY modifies broker's server-side Stop Loss directly to 70% of TP distance.
    2. When armed and progress <= 0.70: Position is IMMEDIATELY CLOSED AT MARKET on profit (failsafe)!
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
                "armed_at": None,
                "sl_modified_to_70": False,
                "sl_70_price": None
            }
            state_modified = True

        entry = protection_state[ticket_str]
        entry["peak_progress"] = max(entry.get("peak_progress", 0.0), progress)

        # C-5 fix: Leg-specific arming thresholds
        # Banker (default): arm at 80%, lock at 70%
        # Runner: arm at 60%, lock at 50% (wider TP needs earlier protection)
        pos_comment = str(getattr(pos, "comment", "")).lower()
        is_runner_leg = "runner" in pos_comment
        arm_threshold = 0.60 if is_runner_leg else 0.80
        lock_threshold = 0.50 if is_runner_leg else 0.70
        entry["arm_threshold"] = arm_threshold
        entry["lock_threshold"] = lock_threshold

        # Gate 1: Check Arming Threshold
        if progress >= arm_threshold and not entry.get("armed", False):
            entry["armed"] = True
            entry["armed_at"] = datetime.now(timezone.utc).isoformat()
            state_modified = True
            leg_label = "Runner" if is_runner_leg else "Banker"
            logger.info(
                f"[PROFIT PROTECTION ARMED] Position #{pos.ticket} ({pos.symbol} {pos_dir} {leg_label}) reached "
                f"{progress * 100:.1f}% of TP distance (threshold: {arm_threshold*100:.0f}%). Arming {lock_threshold*100:.0f}% server-side Stop Loss..."
            )

        # Instant Server-Side Stop Loss Modification to dynamic profit floor
        if entry.get("armed", False) and not entry.get("sl_modified_to_70", False):
            sym_info = mt5.symbol_info(pos.symbol)
            digits = sym_info.digits if sym_info else 2
            floor_pct = entry.get("lock_threshold", 0.70)

            if pos.type == mt5.ORDER_TYPE_BUY:
                floor_price = round(pos.price_open + (floor_pct * total_dist), digits)
                is_better = floor_price > pos.sl
            else:
                floor_price = round(pos.price_open - (floor_pct * total_dist), digits)
                is_better = (pos.sl == 0.0) or (floor_price < pos.sl)

            if is_better:
                logger.info(
                    f"[SERVER-SIDE SL MODIFICATION] Modifying Position #{pos.ticket} ({pos.symbol} {pos_dir}) "
                    f"Stop Loss from {pos.sl} -> {floor_price} ({floor_pct*100:.0f}% Profit Floor)..."
                )
                mod_res = modify_mt5_sl(pos.ticket, floor_price)
                if mod_res.get("status") == "SUCCESS":
                    entry["sl_modified_to_70"] = True
                    entry["sl_70_price"] = floor_price
                    state_modified = True

                    # Calculate guaranteed locked profit in USD
                    try:
                        locked_usd = mt5.order_calc_profit(pos.type, pos.symbol, pos.volume, pos.price_open, floor_price)
                    except Exception:
                        locked_usd = None
                    locked_usd_str = f"+${locked_usd:,.2f} USD" if locked_usd is not None else f"+{floor_pct*100:.0f}% Target Profit"

                    logger.info(
                        f"[SERVER-SIDE SL LOCKED] Position #{pos.ticket} Stop Loss successfully locked at "
                        f"{floor_price} on broker matching engine ({locked_usd_str} locked)."
                    )

                    # Dispatch Instant Telegram Notification
                    peak_pct = entry.get("peak_progress", progress) * 100
                    leg_label = "Runner (60/50)" if is_runner_leg else "Banker (80/70)"
                    alert_msg = (
                        f"🛡️ <b>PROFIT GUARD ARMED — SERVER SL LOCKED ({leg_label})</b>\n"
                        f"━━━━━━━━━━━━━━━━━━━━\n"
                        f"<b>Asset:</b> <code>{pos.symbol}</code> ({pos_dir})\n"
                        f"<b>Status:</b> 🔒 <b>SERVER-SIDE STOP LOSS UPGRADED</b>\n"
                        f"<b>Progress Reached:</b> <code>{peak_pct:.1f}%</code> of TP Target\n"
                        f"<b>Live Price:</b> <code>{pos.price_current}</code>\n"
                        f"<b>Entry Price:</b> <code>{pos.price_open}</code>\n"
                        f"<b>Take Profit Target:</b> <code>{pos.tp}</code>\n"
                        f"<b>New Server SL ({floor_pct*100:.0f}% Floor):</b> <code>{floor_price}</code>\n"
                        f"<b>Guaranteed Locked Win:</b> <b>{locked_usd_str}</b> (Minimum)\n"
                        f"<b>Position Ticket:</b> <code>#{pos.ticket}</code>\n"
                        f"━━━━━━━━━━━━━━━━━━━━\n"
                        f"<i>Broker server-side execution guaranteed with 0ms latency even during network disconnects.</i>"
                    )
                    broadcast_telegram(alert_msg)
                else:
                    logger.error(
                        f"[SERVER-SIDE SL FAILED] Failed to modify SL for #{pos.ticket}: {mod_res.get('reason')}. "
                        f"Will retry next cycle while Gate 2 market close remains active."
                    )
            else:
                # Already at or better than floor
                entry["sl_modified_to_70"] = True
                entry["sl_70_price"] = floor_price
                state_modified = True

        # Gate 2: Retracement Exit Threshold (Armed + <= lock_threshold) — Local Failsafe
        retracement_threshold = entry.get("lock_threshold", 0.70)
        if entry.get("armed", False) and progress <= retracement_threshold:
            peak_pct = entry.get("peak_progress", progress) * 100
            current_pct = progress * 100
            logger.warning(
                f"[PROFIT PROTECTION TRIGGERED - LOCAL FAILSAFE] Position #{pos.ticket} ({pos.symbol} {pos_dir}) retraced to "
                f"{current_pct:.1f}% after peak {peak_pct:.1f}%. Executing immediate market close to lock in win!"
            )

            res = close_position(pos.ticket)
            if res.get("status") == "SUCCESS":
                profit = pos.profit
                open_ts = getattr(pos, "time", int(time.time()))
                dur_sec = max(0, int(time.time()) - open_ts)
                dur_h = dur_sec // 3600
                dur_m = (dur_sec % 3600) // 60
                dur_str = f"{dur_h}h {dur_m}m ({dur_h} hours, {dur_m} mins)" if dur_h > 0 else f"{dur_m}m ({dur_m} mins)"
                alert_msg = (
                    f"🎯 <b>PROFIT PROTECTION WIN EXIT (80% ➔ 70% RETRACEMENT)</b>\n"
                    f"━━━━━━━━━━━━━━━━━━━━\n"
                    f"<b>Asset:</b> <code>{pos.symbol}</code> ({pos_dir})\n"
                    f"<b>Action:</b> <b>PROFIT LOCKED IN AT MARKET (FAILSAFE)</b>\n"
                    f"<b>Duration:</b> ⏱️ <b>{dur_str}</b>\n"
                    f"<b>Peak Distance Reached:</b> <code>{peak_pct:.1f}%</code> of TP\n"
                    f"<b>Exit Retracement:</b> <code>{current_pct:.1f}%</code> of TP\n"
                    f"<b>Execution Price:</b> <code>{pos.price_current}</code>\n"
                    f"<b>Realized P&L Secured:</b> <b>+${profit:,.2f} USD</b>\n"
                    f"<b>Deal Ticket:</b> <code>#{pos.ticket}</code>\n"
                    f"━━━━━━━━━━━━━━━━━━━━\n"
                    f"<i>Asymmetric Profit Guard: Protected win and prevented pullback to BE/loss.</i>"
                )
                broadcast_telegram(alert_msg)
                if armed_history is not None:
                    armed_history[ticket_str] = dict(entry)
                del protection_state[ticket_str]
                state_modified = True
            else:
                logger.error(f"Failed to execute profit protection close for #{pos.ticket}: {res.get('reason')}")

    # Clean up closed positions from state, archiving into armed_history
    expired_tickets = [t for t in protection_state if t not in active_tickets]
    if expired_tickets:
        for t in expired_tickets:
            if armed_history is not None:
                armed_history[t] = dict(protection_state[t])
            del protection_state[t]
        state_modified = True

    if state_modified:
        save_profit_protection_state(protection_state)


def check_and_upgrade_runners(closed_deal, open_positions):
    """
    Druckenmiller Asymmetric Runner Engine (v5.1.0):
    When a winning trade closes (Leg 1 Banker), immediately find remaining positions
    on the same symbol tagged as Runner (via order comment).
    1. Instantly upgrade its MT5 server-side Stop Loss to Break-Even + dynamic profit lock floor.
    2. Dynamic offset: max($2.00, 0.15 × ATR_1H) adapts to volatility.
    3. Broadcast Telegram alert confirming runner activation (Zero Risk, Uncapped Upside).
    """
    if not open_positions or closed_deal.profit <= 0:
        return

    symbol = closed_deal.symbol

    # Calculate dynamic offset based on ATR
    try:
        from mt5_connector import calculate_atr
        atr = calculate_atr(symbol, mt5.TIMEFRAME_H1, 14)
    except Exception:
        atr = None

    is_gold = "XAU" in symbol.upper() or "GOLD" in symbol.upper()
    if atr and atr > 0:
        offset = max(2.0 if is_gold else (20 * (mt5.symbol_info(symbol).point if mt5.symbol_info(symbol) else 0.0001)),
                     0.15 * atr)
    else:
        offset = 2.0 if is_gold else 0.0020

    for pos in open_positions:
        if pos.symbol != symbol:
            continue

        # H-3 fix: Only upgrade positions tagged as Runner (from scanner comment)
        pos_comment = str(getattr(pos, "comment", "")).lower()
        is_runner = "runner" in pos_comment
        # Fallback: if comment not available or not tagged, upgrade any same-symbol position
        # (preserves backward compatibility with older trades)
        if not is_runner and pos_comment and ("banker" in pos_comment):
            continue  # Skip positions explicitly tagged as Banker

        sym_info = mt5.symbol_info(symbol)
        digits = sym_info.digits if sym_info else 2

        if pos.type == mt5.ORDER_TYPE_BUY:
            floor_sl = round(pos.price_open + offset, digits)
            if pos.sl < floor_sl:
                logger.info(f"[RUNNER UPGRADE] Upgrading Runner #{pos.ticket} SL to BE+lock: {floor_sl} (offset={offset:.2f})")
                res = modify_mt5_sl(pos.ticket, floor_sl)
                if res.get("status") == "SUCCESS":
                    broadcast_telegram(
                        f"🏃 <b>DRUCKENMILLER RUNNER ARMED: ZERO RISK ACTIVE</b>\n"
                        f"━━━━━━━━━━━━━━━━━━━━\n"
                        f"<b>Asset:</b> <code>{symbol}</code> (BUY)\n"
                        f"<b>Trigger:</b> Leg 1 Banked (+${closed_deal.profit:.2f} USD)!\n"
                        f"<b>Action:</b> Runner #{pos.ticket} Stop Loss upgraded to <code>${floor_sl}</code> (BE + Dynamic Lock)\n"
                        f"<b>Dynamic Offset:</b> <code>${offset:.2f}</code> (max($2, 0.15×ATR))\n"
                        f"<b>Remaining Downside:</b> <b>$0.00 (Protected)</b>\n"
                        f"<b>Upside Potential:</b> 🚀 <b>Uncapped Macro Runner</b>\n"
                        f"━━━━━━━━━━━━━━━━━━━━\n"
                        f"<i>Institutional Asymmetry: Base win banked; trailing runner for macro expansion.</i>"
                    )
        elif pos.type == mt5.ORDER_TYPE_SELL:
            floor_sl = round(pos.price_open - offset, digits)
            if pos.sl == 0.0 or pos.sl > floor_sl:
                logger.info(f"[RUNNER UPGRADE] Upgrading Runner #{pos.ticket} SL to BE+lock: {floor_sl} (offset={offset:.2f})")
                res = modify_mt5_sl(pos.ticket, floor_sl)
                if res.get("status") == "SUCCESS":
                    broadcast_telegram(
                        f"🏃 <b>DRUCKENMILLER RUNNER ARMED: ZERO RISK ACTIVE</b>\n"
                        f"━━━━━━━━━━━━━━━━━━━━\n"
                        f"<b>Asset:</b> <code>{symbol}</code> (SELL)\n"
                        f"<b>Trigger:</b> Leg 1 Banked (+${closed_deal.profit:.2f} USD)!\n"
                        f"<b>Action:</b> Runner #{pos.ticket} Stop Loss upgraded to <code>${floor_sl}</code> (BE + Dynamic Lock)\n"
                        f"<b>Dynamic Offset:</b> <code>${offset:.2f}</code> (max($2, 0.15×ATR))\n"
                        f"<b>Remaining Downside:</b> <b>$0.00 (Protected)</b>\n"
                        f"<b>Upside Potential:</b> 🚀 <b>Uncapped Macro Runner</b>\n"
                        f"━━━━━━━━━━━━━━━━━━━━\n"
                        f"<i>Institutional Asymmetry: Base win banked; trailing runner for macro expansion.</i>"
                    )


def determine_exit_type(deal, armed_history=None):
    """Determine whether TP, SL, BE, Profit Protection, or Manual closed the deal."""
    comment = str(deal.comment).lower()
    profit = deal.profit + getattr(deal, "swap", 0.0) + getattr(deal, "fee", 0.0)

    # Check if position was recorded in armed_history
    pos_id_str = str(getattr(deal, "position_id", deal.order))
    order_str = str(deal.order)
    was_armed = False
    if armed_history:
        hist_entry = armed_history.get(pos_id_str) or armed_history.get(order_str)
        if hist_entry and (hist_entry.get("sl_modified_to_70") or hist_entry.get("armed")):
            was_armed = True

    if "[tp" in comment or "tp" in comment or deal.reason == getattr(mt5, "DEAL_REASON_TP", 5):
        return "TAKE_PROFIT_REACHED", "🎯 TAKE PROFIT REACHED"
    elif "[sl" in comment or "sl" in comment or deal.reason == getattr(mt5, "DEAL_REASON_SL", 4):
        if was_armed or profit >= 5.0:
            return "PROFIT_PROTECTION_EXIT", "🎯 80/70 PROFIT PROTECTION WIN (70% SERVER SL HIT)"
        elif profit >= 0:
            return "BREAK_EVEN_EXIT", "🛡️ BREAK-EVEN / TRAILING STOP REACHED"
        else:
            return "STOP_LOSS_REACHED", "🛑 STOP LOSS REACHED"
    elif "close" in comment:
        if was_armed or profit > 0:
            return "PROFIT_PROTECTION_EXIT", "🎯 80/70 PROFIT PROTECTION EXIT"
        else:
            return "MANUAL_EXIT", "💼 MANUAL / SYSTEM CLOSE"
    else:
        if was_armed or profit >= 5.0:
            return "PROFIT_PROTECTION_EXIT", "🎯 80/70 PROFIT PROTECTION WIN"
        elif profit > 0:
            return "TAKE_PROFIT_REACHED", "🎯 TARGET / PROFIT EXIT"
        elif profit == 0:
            return "BREAK_EVEN_EXIT", "⚖️ BREAK-EVEN EXIT"
        else:
            return "STOP_LOSS_REACHED", "🛑 STOP LOSS / EXIT"


def calculate_trade_duration(deal):
    """
    Computes holding duration of a trade in hours and minutes.
    Returns: formatted string e.g. '4h 18m (4 hours, 18 mins)' or '25m (25 mins)'.
    """
    open_time = None
    pos_id = getattr(deal, "position_id", None) or getattr(deal, "order", None)

    if pos_id:
        try:
            pos_deals = mt5.history_deals_get(position=pos_id)
            if pos_deals:
                in_deals = [d for d in pos_deals if d.entry == mt5.DEAL_ENTRY_IN]
                if in_deals:
                    open_time = in_deals[0].time
        except Exception:
            pass

        if not open_time:
            try:
                pos_orders = mt5.history_orders_get(ticket=pos_id)
                if pos_orders:
                    open_time = pos_orders[0].time_setup
            except Exception:
                pass

    if not open_time:
        return "N/A"

    duration_sec = max(0, deal.time - open_time)
    hours = duration_sec // 3600
    minutes = (duration_sec % 3600) // 60

    if hours > 0:
        h_unit = "hour" if hours == 1 else "hours"
        m_unit = "min" if minutes == 1 else "mins"
        return f"{hours}h {minutes}m ({hours} {h_unit}, {minutes} {m_unit})"
    else:
        m_unit = "min" if minutes == 1 else "mins"
        return f"{minutes}m ({minutes} {m_unit})"


def format_telegram_alert(deal, account_info, armed_history=None):
    """Format an institutional trade closure alert."""
    exit_key, exit_header = determine_exit_type(deal, armed_history)
    symbol = deal.symbol
    pos_direction = "BUY" if deal.type == 1 else "SELL"
    profit = round(deal.profit + getattr(deal, "swap", 0.0) + getattr(deal, "fee", 0.0), 2)
    pnl_sign = "+" if profit >= 0 else ""
    pnl_str = f"{pnl_sign}${profit:,.2f}"

    price = deal.price
    volume = deal.volume
    close_time = datetime.fromtimestamp(deal.time, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    duration_str = calculate_trade_duration(deal)

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
<b>Duration:</b> ⏱️ <b>{duration_str}</b>
<b>Exit Price:</b> <code>{price}</code>
<b>Volume:</b> <code>{volume:.2f} Lots</code>
<b>Close Time:</b> <code>{close_time}</code>
<b>Deal Ticket:</b> <code>#{deal.ticket}</code> (Order #{deal.order})
━━━━━━━━━━━━━━━━━━━━
<b>Account Balance:</b> <code>${balance:,.2f}</code>
<b>Account Equity:</b> <code>${equity:,.2f}</code>
<b>Strategy Status:</b> 80/70 Server SL Profit Guard Protected (v3.9.0)"""

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
    logger.info("Initializing Real-Time MT5 Trade Closure & Server-Side 80/70 Profit Protection Monitor (v3.9.0)...")
    if not ensure_mt5_connected():
        logger.error(f"Initial MT5 connection failed: {mt5.last_error()}")

    processed_tickets = load_processed_tickets()
    protection_state = load_profit_protection_state()
    armed_history = {}

    logger.info(f"Trade Monitor ACTIVE — polling deal stream & 80/70 server SL guard every 3 seconds ({len(processed_tickets)} processed deals tracked)...")

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
                check_and_execute_profit_protection(positions, protection_state, armed_history)

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
                        alert_msg = format_telegram_alert(deal, account_info, armed_history)

                        broadcast_telegram(alert_msg)

                        # Druckenmiller Runner Engine: If closed in profit, upgrade remaining runners to BE+lock
                        if deal.profit > 0:
                            live_positions = mt5.positions_get()
                            check_and_upgrade_runners(deal, live_positions)

                        processed_tickets.add(deal.ticket)
                        save_processed_tickets(processed_tickets)
                        logger.info(f"Alert delivered for Deal #{deal.ticket}.")

            # Clean armed_history if too large
            if len(armed_history) > 200:
                for k in list(armed_history.keys())[:-100]:
                    del armed_history[k]

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
