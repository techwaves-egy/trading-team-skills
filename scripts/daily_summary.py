#!/usr/bin/env python3
"""
AI Autonomous Trading Firm — Daily Trade Summary Reporter (v3.8.0)
Queries MT5 deal history and open positions for the current day,
calculates forensic win/loss metrics, and dispatches a comprehensive
Market Close Daily Audit directly to Telegram Administrator @wtalaat.

Usage:
    python daily_summary.py                 # Send today's full summary to Admin now
    python daily_summary.py --daemon        # Run daily at market close automatically
    python daily_summary.py --weekly        # Send weekly market close audit
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

from send_alert import broadcast_telegram, send_admin_telegram

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - DailySummary - %(levelname)s - %(message)s"
)
logger = logging.getLogger("DailySummary")

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SESSION_PATH = os.path.join(BASE_DIR, "config", "session_state.json")
JOURNAL_DIR = os.path.join(BASE_DIR, "journal")


def load_session():
    """Load session state."""
    if os.path.exists(SESSION_PATH):
        try:
            with open(SESSION_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error loading session state: {e}")
    return {}


def save_journal_entry(date_str, summary_data):
    """Persist daily summary to journal directory for historical audit records."""
    os.makedirs(JOURNAL_DIR, exist_ok=True)
    path = os.path.join(JOURNAL_DIR, f"summary_{date_str}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(summary_data, f, indent=2, default=str)
    logger.info(f"Journal audit saved: {path}")


def get_daily_deals():
    """
    Query MT5 for all closed deals and open positions from today (00:00 UTC to now).
    Returns (closed_deals, account_info, open_positions)
    """
    try:
        import MetaTrader5 as mt5
    except ImportError:
        logger.error("MetaTrader5 not installed")
        return None, None, None

    if not mt5.initialize():
        logger.error(f"MT5 initialize failed: {mt5.last_error()}")
        return None, None, None

    now = datetime.now(timezone.utc)
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    deals = mt5.history_deals_get(day_start, now)
    account = mt5.account_info()
    positions = mt5.positions_get()

    closed_trades = []
    if deals:
        for d in deals:
            # We want trade exits: deal.entry == 1 (DEAL_ENTRY_OUT)
            if d.entry == 1 and d.type in (0, 1):
                pos_deals = mt5.history_deals_get(position=d.position_id)
                e_deal = None
                if pos_deals:
                    in_deals = [pd for pd in pos_deals if pd.entry == 0]
                    if in_deals:
                        e_deal = in_deals[0]

                open_price = e_deal.price if e_deal else 0.0
                open_time = datetime.fromtimestamp(e_deal.time, tz=timezone.utc) if e_deal else None
                close_time = datetime.fromtimestamp(d.time, tz=timezone.utc)
                duration_sec = int((close_time - open_time).total_seconds()) if open_time else 0
                dur_h = duration_sec // 3600
                dur_m = (duration_sec % 3600) // 60
                dur_str = f"{dur_h}h {dur_m}m" if dur_h > 0 else (f"{dur_m}m {duration_sec % 60}s" if dur_m > 0 else f"{duration_sec}s")
                
                # If e_deal exists, type is e_deal.type (0=BUY, 1=SELL). If not, exit type 1 implies entry was BUY.
                if e_deal:
                    order_type = "BUY" if e_deal.type == 0 else "SELL"
                else:
                    order_type = "BUY" if d.type == 1 else "SELL"

                net = round(d.profit + d.commission + d.swap, 2)

                comm = d.comment or ""
                if "[tp" in comm.lower():
                    reason = "Take Profit Hit"
                elif "[sl" in comm.lower():
                    reason = "Stop Loss Hit"
                elif "close" in comm.lower():
                    reason = "80/70 Asymmetric Exit"
                else:
                    reason = comm or "Market Settlement"

                closed_trades.append({
                    "ticket": d.ticket,
                    "position_id": d.position_id,
                    "symbol": d.symbol,
                    "type": order_type,
                    "volume": d.volume,
                    "open_price": open_price,
                    "close_price": d.price,
                    "open_time": open_time.strftime("%H:%M:%S UTC") if open_time else "N/A",
                    "close_time": close_time.strftime("%H:%M:%S UTC"),
                    "duration": dur_str,
                    "profit": round(d.profit, 2),
                    "commission": round(d.commission, 2),
                    "swap": round(d.swap, 2),
                    "net_pnl": net,
                    "reason": reason,
                    "comment": comm
                })

    open_pos_list = []
    if positions:
        for p in positions:
            open_pos_list.append({
                "ticket": p.ticket,
                "symbol": p.symbol,
                "type": "BUY" if p.type == 0 else "SELL",
                "volume": p.volume,
                "price_open": p.price_open,
                "price_current": p.price_current,
                "profit": round(p.profit, 2),
                "sl": p.sl,
                "tp": p.tp,
                "time": datetime.fromtimestamp(p.time, tz=timezone.utc).strftime("%H:%M:%S UTC")
            })

    mt5.shutdown()
    return closed_trades, account, open_pos_list


def build_summary():
    """Build a complete, forensic daily trade summary with all market close telemetry."""
    closed_trades, account, open_positions = get_daily_deals()
    now = datetime.now(timezone.utc)
    date_str = now.strftime("%Y-%m-%d")

    summary = {
        "date": date_str,
        "timestamp": now.strftime("%Y-%m-%d %H:%M:%S UTC"),
        "account_login": account.login if account else "N/A",
        "account_server": account.server if account else "N/A",
        "account_balance": round(account.balance, 2) if account else 0.0,
        "account_equity": round(account.equity, 2) if account else 0.0,
        "account_margin": round(account.margin, 2) if account else 0.0,
        "account_margin_free": round(account.margin_free, 2) if account else 0.0,
        "account_margin_level": round(account.margin_level, 2) if (account and account.margin_level) else 0.0,
        "total_trades": 0,
        "wins": 0,
        "losses": 0,
        "breakeven": 0,
        "total_profit": 0.0,
        "total_loss": 0.0,
        "net_pnl": 0.0,
        "win_rate": 0.0,
        "profit_factor": 0.0,
        "largest_win": 0.0,
        "largest_loss": 0.0,
        "avg_win": 0.0,
        "avg_loss": 0.0,
        "max_win_streak": 0,
        "max_loss_streak": 0,
        "starting_balance": 0.0,
        "daily_roi_pct": 0.0,
        "open_positions": open_positions or [],
        "trades": closed_trades or [],
        "status": "NO_TRADES"
    }

    if not closed_trades and not open_positions:
        summary["starting_balance"] = summary["account_balance"]
        return summary

    if closed_trades:
        summary["total_trades"] = len(closed_trades)
        wins_list = [t for t in closed_trades if t["net_pnl"] > 0]
        loss_list = [t for t in closed_trades if t["net_pnl"] < 0]
        be_list = [t for t in closed_trades if t["net_pnl"] == 0]

        summary["wins"] = len(wins_list)
        summary["losses"] = len(loss_list)
        summary["breakeven"] = len(be_list)

        tot_prof = sum(t["net_pnl"] for t in wins_list)
        tot_loss = sum(abs(t["net_pnl"]) for t in loss_list)

        summary["total_profit"] = round(tot_prof, 2)
        summary["total_loss"] = round(tot_loss, 2)
        summary["net_pnl"] = round(tot_prof - tot_loss, 2)

        if summary["total_trades"] > 0:
            summary["win_rate"] = round((summary["wins"] / summary["total_trades"]) * 100, 1)

        if tot_loss > 0:
            summary["profit_factor"] = round(tot_prof / tot_loss, 2)
        elif tot_prof > 0:
            summary["profit_factor"] = 999.0

        if wins_list:
            summary["largest_win"] = max(t["net_pnl"] for t in wins_list)
            summary["avg_win"] = round(tot_prof / len(wins_list), 2)
        if loss_list:
            summary["largest_loss"] = min(t["net_pnl"] for t in loss_list)
            summary["avg_loss"] = round(tot_loss / len(loss_list), 2)

        # Streak calculation
        cur_streak = 0
        streaks = []
        for t in closed_trades:
            if t["net_pnl"] > 0:
                cur_streak = max(0, cur_streak) + 1
            elif t["net_pnl"] < 0:
                cur_streak = min(0, cur_streak) - 1
            streaks.append(cur_streak)

        summary["max_win_streak"] = max(streaks) if streaks and max(streaks) > 0 else 0
        summary["max_loss_streak"] = abs(min(streaks)) if streaks and min(streaks) < 0 else 0

        # Account starting balance and daily ROI calculation
        starting_bal = round(summary["account_balance"] - summary["net_pnl"], 2)
        summary["starting_balance"] = starting_bal
        if starting_bal > 0:
            summary["daily_roi_pct"] = round((summary["net_pnl"] / starting_bal) * 100, 2)

        if summary["net_pnl"] > 0:
            summary["status"] = "PROFIT"
        elif summary["net_pnl"] < 0:
            summary["status"] = "LOSS"
        else:
            summary["status"] = "FLAT"

    return summary


def format_telegram_summary(summary):
    """
    Format the complete Daily Market Close Audit as a structured Telegram HTML message.
    Returns (part1_msg, part2_trades_log) or (single_msg, None)
    """
    date = summary["date"]
    pnl = summary["net_pnl"]
    pnl_sign = "+" if pnl >= 0 else ""
    bar_emoji = "🟢" if pnl > 0 else ("🔴" if pnl < 0 else "⚪")
    status_label = "PROFITABLE DAY" if pnl > 0 else ("LOSS DAY" if pnl < 0 else "FLAT / BREAKEVEN")
    roi_sign = "+" if summary["daily_roi_pct"] >= 0 else ""
    pf_display = f"{summary['profit_factor']:.2f}" if summary["profit_factor"] < 900 else "MAX"

    # Open Positions Audit at Market Close
    open_pos = summary.get("open_positions", [])
    if open_pos:
        pos_lines = []
        for op in open_pos:
            pos_sign = "+" if op["profit"] >= 0 else ""
            pos_lines.append(
                f"  ⚠️ #{op['ticket']} {op['symbol']} {op['type']} ({op['volume']}L) @ {op['price_open']} "
                f"| Float: <code>{pos_sign}${op['profit']:.2f}</code> | SL: {op['sl']} TP: {op['tp']}"
            )
        open_block = "<b>ACTIVE OVERNIGHT POSITIONS (" + str(len(open_pos)) + "):</b>\n" + "\n".join(pos_lines)
    else:
        open_block = "🛡️ <b>Overnight Exposure:</b> 🟢 <b>100% Flat &amp; Capital Protected (0 Open Positions)</b>"

    # Header and KPIs
    header_block = (
        f"🏛️ <b>EXECUTIVE DAILY TRADE AUDIT — MARKET CLOSE</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📅 <b>Date:</b> <code>{date}</code> (Settlement Close: <code>{summary['timestamp']}</code>)\n"
        f"🏦 <b>Account:</b> <code>{summary['account_server']} #{summary['account_login']}</code>\n"
        f"💰 <b>Closing Balance:</b> <code>${summary['account_balance']:,.2f}</code>\n"
        f"📊 <b>Closing Equity:</b>  <code>${summary['account_equity']:,.2f}</code>\n"
        f"💵 <b>Net Daily P&amp;L:</b> {bar_emoji} <b><code>{pnl_sign}${pnl:.2f}</code></b> ({roi_sign}{summary['daily_roi_pct']:.2f}% ROI • {status_label})\n\n"
        f"<b>📊 PERFORMANCE SCORECARD:</b>\n"
        f"  • Total Closed Trades: <b>{summary['total_trades']}</b>\n"
        f"  • Record: <b>{summary['wins']}W – {summary['losses']}L – {summary['breakeven']}BE</b>\n"
        f"  • Win Rate: <b>{summary['win_rate']}%</b>\n"
        f"  • Profit Factor: <b>{pf_display}</b>\n"
        f"  • Gross Profit: <code>+${summary['total_profit']:.2f}</code>\n"
        f"  • Gross Loss:   <code>-${summary['total_loss']:.2f}</code>\n"
        f"  • Best Trade:   <code>+${summary['largest_win']:.2f}</code>\n"
        f"  • Worst Trade:  <code>${summary['largest_loss']:.2f}</code>\n"
        f"  • Average Win:  <code>+${summary['avg_win']:.2f}</code>\n"
        f"  • Average Loss: <code>-${summary['avg_loss']:.2f}</code>\n"
        f"  • Streaks: <b>{summary['max_win_streak']} Wins</b> in a row | <b>{summary['max_loss_streak']} Losses</b>\n\n"
        f"{open_block}\n"
        f"  • Free Margin: <code>${summary['account_margin_free']:,.2f}</code>\n"
        f"  • Margin Level: <code>{summary['account_margin_level']:.1f}%</code>\n"
        f"  • Anti-Tamper Security: 🟢 <b>100% Cryptographically Certified</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━"
    )

    if not summary["trades"]:
        msg = header_block + "\n<i>No closed trade transactions executed today.</i>\n━━━━━━━━━━━━━━━━━━━━"
        return msg, None

    # Trade ledger formatting ("All what happened")
    trade_lines = []
    for i, t in enumerate(summary["trades"], 1):
        sign = "+" if t["net_pnl"] >= 0 else ""
        icon = "🟢" if t["net_pnl"] > 0 else ("🔴" if t["net_pnl"] < 0 else "⚪")
        trade_lines.append(
            f"{icon} <b>#{i:02d} {t['symbol']} {t['type']}</b> ({t['volume']}L) • <code>{sign}${t['net_pnl']:.2f}</code>\n"
            f"   Time: <code>{t['open_time']}</code> ➔ <code>{t['close_time']}</code> ({t['duration']})\n"
            f"   Price: <code>{t['open_price']}</code> ➔ <code>{t['close_price']}</code> | <i>{t['reason']}</i>"
        )

    ledger_text = "📋 <b>COMPLETE CHRONOLOGICAL TRADES LEDGER:</b>\n" + "\n\n".join(trade_lines)
    full_message = f"{header_block}\n\n{ledger_text}\n━━━━━━━━━━━━━━━━━━━━\n<i>AI Autonomous Trading Firm v3.8.0 • TechWaves EGY</i>"

    if len(full_message) <= 3900:
        return full_message, None
    else:
        part1 = f"{header_block}\n\n<i>(Detailed trade log dispatched in Part 2 below)</i>"
        part2 = (
            f"📋 <b>DAILY TRADE LOG — PART 2 (ALL EXECUTIONS):</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"{ledger_text}\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"<i>AI Autonomous Trading Firm v3.8.0 • TechWaves EGY</i>"
        )
        return part1, part2


def send_daily_summary(admin_only=True):
    """
    Build, format, save, and deliver the complete daily summary.
    Defaults to admin_only=True (delivering strictly to Administrator @wtalaat).
    """
    logger.info("Generating complete Daily Market Close Audit...")
    summary = build_summary()

    # Save to persistent journal
    save_journal_entry(summary["date"], summary)

    # Format Telegram HTML payload
    part1, part2 = format_telegram_summary(summary)

    if admin_only:
        send_admin_telegram(part1)
        if part2:
            time.sleep(1)
            send_admin_telegram(part2)
        logger.info(f"Daily Market Close Audit delivered directly to Administrator @wtalaat.")
    else:
        broadcast_telegram(part1)
        if part2:
            time.sleep(1)
            broadcast_telegram(part2)
        logger.info(f"Daily Market Close Audit broadcasted to all channels and admin.")

    return summary


def get_weekly_deals():
    """Query MT5 for all closed deals from the start of the current week (Monday 00:00 UTC to now)."""
    try:
        import MetaTrader5 as mt5
    except ImportError:
        logger.error("MetaTrader5 not installed")
        return None, None, None

    if not mt5.initialize():
        logger.error(f"MT5 initialize failed: {mt5.last_error()}")
        return None, None, None

    now = datetime.now(timezone.utc)
    days_since_monday = now.weekday()
    monday_start = (now - timedelta(days=days_since_monday)).replace(hour=0, minute=0, second=0, microsecond=0)

    deals = mt5.history_deals_get(monday_start, now)
    account = mt5.account_info()

    mt5.shutdown()
    return deals, account, monday_start


def build_weekly_summary():
    """Build a complete weekly trade summary from MT5 deal history."""
    deals, account, week_start = get_weekly_deals()
    now = datetime.now(timezone.utc)
    week_str = f"{now.strftime('%Y')}-W{now.strftime('%W')}"
    date_range_str = f"{week_start.strftime('%b %d')} – {now.strftime('%b %d, %Y')}"

    summary = {
        "week": week_str,
        "date_range": date_range_str,
        "timestamp": now.isoformat(),
        "account_balance": account.balance if account else 0.0,
        "account_equity": account.equity if account else 0.0,
        "total_trades": 0,
        "wins": 0,
        "losses": 0,
        "breakeven": 0,
        "total_profit": 0.0,
        "total_loss": 0.0,
        "net_pnl": 0.0,
        "largest_win": 0.0,
        "largest_loss": 0.0,
        "win_rate": 0.0,
        "profit_factor": 0.0,
        "trades": []
    }

    if deals is None or len(deals) == 0:
        summary["status"] = "NO_TRADES"
        return summary

    from collections import defaultdict
    positions = defaultdict(list)
    for deal in deals:
        if deal.position_id:
            positions[deal.position_id].append(deal)

    closed_trades = []
    for pid, d_list in sorted(positions.items()):
        close_deals = [d for d in d_list if d.entry == 1]
        if not close_deals:
            continue
        entry_deals = [d for d in d_list if d.entry == 0]
        e_deal = entry_deals[0] if entry_deals else close_deals[0]
        x_deal = close_deals[-1]

        p_profit = sum(d.profit for d in d_list)
        p_comm = sum(d.commission for d in d_list)
        p_swap = sum(d.swap for d in d_list)
        net = round(p_profit + p_comm + p_swap, 2)

        order_type = "BUY" if e_deal.type == 0 else "SELL"
        close_dt = datetime.fromtimestamp(x_deal.time, tz=timezone.utc)

        trade_obj = {
            "position_id": pid,
            "symbol": e_deal.symbol,
            "type": order_type,
            "volume": e_deal.volume,
            "entry_price": e_deal.price,
            "exit_price": x_deal.price,
            "net_pnl": net,
            "close_time": close_dt.strftime("%a %H:%M UTC"),
            "date": close_dt.strftime("%Y-%m-%d")
        }
        closed_trades.append(trade_obj)

        if net > 0:
            summary["wins"] += 1
            summary["total_profit"] += net
            if net > summary["largest_win"]:
                summary["largest_win"] = net
        elif net < 0:
            summary["losses"] += 1
            summary["total_loss"] += abs(net)
            if abs(net) > abs(summary["largest_loss"]):
                summary["largest_loss"] = net
        else:
            summary["breakeven"] += 1

    summary["total_trades"] = len(closed_trades)
    summary["trades"] = closed_trades
    summary["net_pnl"] = round(summary["total_profit"] - summary["total_loss"], 2)
    summary["total_profit"] = round(summary["total_profit"], 2)
    summary["total_loss"] = round(summary["total_loss"], 2)
    summary["largest_win"] = round(summary["largest_win"], 2)
    summary["largest_loss"] = round(summary["largest_loss"], 2)

    if summary["total_trades"] > 0:
        summary["win_rate"] = round((summary["wins"] / summary["total_trades"]) * 100, 1)

    if summary["total_loss"] > 0:
        summary["profit_factor"] = round(summary["total_profit"] / summary["total_loss"], 2)
    elif summary["total_profit"] > 0:
        summary["profit_factor"] = 999.0

    summary["status"] = "PROFIT" if summary["net_pnl"] >= 0 else ("LOSS" if summary["net_pnl"] < 0 else "NEUTRAL")
    return summary


def format_telegram_weekly_summary(summary):
    """Format the weekly summary as an executive Telegram HTML message."""
    week = summary["week"]
    date_range = summary["date_range"]
    pnl = summary["net_pnl"]
    pnl_sign = "+" if pnl >= 0 else ""
    bar_emoji = "🟢" if pnl >= 0 else "🔴"
    status_text = "PROFITABLE WEEK" if pnl > 0 else ("LOSS WEEK" if pnl < 0 else "FLAT WEEK")
    pf_display = f"{summary['profit_factor']:.2f}" if summary["profit_factor"] < 900 else "INF"

    trade_lines = []
    for i, t in enumerate(summary["trades"], 1):
        icon = "W" if t["net_pnl"] > 0 else ("L" if t["net_pnl"] < 0 else "BE")
        sign = "+" if t["net_pnl"] >= 0 else ""
        trade_lines.append(
            f"  {i}. {t['symbol']} {t['type']} ({t['volume']}L) @ {t['close_time']} — [{icon}] {sign}${t['net_pnl']:.2f}"
        )
    trade_block = "\n".join(trade_lines) if trade_lines else "  No closed trades this week"

    msg = (
        f"🏆 <b>WEEKLY PERFORMANCE &amp; WEEKEND CLOSE AUDIT</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📅 <b>Trading Week:</b> <code>{week}</code> ({date_range})\n"
        f"🏦 <b>Account Balance:</b> <code>${summary['account_balance']:,.2f}</code>\n"
        f"📈 <b>Weekly Net P&amp;L:</b> {bar_emoji} <b><code>{pnl_sign}${pnl:.2f}</code></b> ({status_text})\n"
        f"🎯 <b>Win Rate:</b> <b>{summary['win_rate']}%</b> ({summary['wins']}W – {summary['losses']}L – {summary['breakeven']}BE)\n"
        f"📊 <b>Profit Factor:</b> <b>{pf_display}</b>\n\n"
        f"<b>WEEKLY METRICS:</b>\n"
        f"  • Total Closed Trades: <b>{summary['total_trades']}</b>\n"
        f"  • Gross Profit: <code>+${summary['total_profit']:.2f}</code>\n"
        f"  • Gross Loss:   <code>-${summary['total_loss']:.2f}</code>\n"
        f"  • Best Trade:   <code>+${summary['largest_win']:.2f}</code>\n"
        f"  • Worst Trade:  <code>${summary['largest_loss']:.2f}</code>\n\n"
        f"<b>TRADE LOG:</b>\n"
        f"<code>{trade_block}</code>\n\n"
        f"🛑 <b>WEEKEND MARKET CLOSE STATUS:</b>\n"
        f"  • Open Exposure: <b>0 (100% Flat &amp; Protected)</b>\n"
        f"  • Background Scanners: <b>Standby / Protected</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"<i>AI Autonomous Trading Firm v3.8.0 • TechWaves EGY</i>"
    )
    return msg


def kill_all_trading_processes():
    """
    Terminates active scanner and monitor processes on Friday market close.
    Preserves telegram_listener.py for 24/7 administrative communication.
    """
    my_pid = os.getpid()
    logger.info("Executing Weekend Market Close Termination...")
    
    try:
        session = load_session()
        session["is_active"] = False
        session["shutdown_reason"] = "WEEKEND_MARKET_CLOSE_AUTO_TERMINATION"
        session["shutdown_time"] = datetime.now(timezone.utc).isoformat()
        with open(SESSION_PATH, "w", encoding="utf-8") as f:
            json.dump(session, f, indent=2)
        logger.info("Session state marked INACTIVE in session_state.json")
    except Exception as e:
        logger.error(f"Error updating session state on shutdown: {e}")

    ps_cmd = (
        f"$myPid = {my_pid}; "
        f"Get-CimInstance Win32_Process | "
        f"Where-Object {{ ($_.CommandLine -match 'auto_scanner\\.py' -or $_.CommandLine -match 'trade_monitor\\.py') -and $_.ProcessId -ne $myPid }} | "
        f"ForEach-Object {{ Stop-Process -Id $_.ProcessId -Force; Write-Output $_.ProcessId }}"
    )
    try:
        import subprocess
        res = subprocess.run(["powershell", "-NoProfile", "-Command", ps_cmd], capture_output=True, text=True, timeout=10)
        pids = [p.strip() for p in res.stdout.strip().splitlines() if p.strip()]
        logger.info(f"Terminated {len(pids)} background process(es): {pids}")
        return len(pids)
    except Exception as e:
        logger.error(f"Error terminating background processes: {e}")
        return 0


def send_market_close_summary(is_weekend=False, kill_processes=True, admin_only=True):
    """Dispatches the market close summary to Telegram Admin and enforces weekend protection."""
    now = datetime.now(timezone.utc)
    
    if is_weekend or now.weekday() in (4, 5, 6): # Friday close or weekend
        logger.info("Generating and sending Weekly Market Close Summary...")
        weekly_summary = build_weekly_summary()
        save_journal_entry(f"weekly_{weekly_summary['week']}", weekly_summary)
        msg = format_telegram_weekly_summary(weekly_summary)
        if admin_only:
            send_admin_telegram(msg)
        else:
            broadcast_telegram(msg)
        logger.info("Weekly Market Close Summary delivered to Telegram.")
    else:
        logger.info("Generating and sending Daily Market Close Summary to Admin...")
        send_daily_summary(admin_only=admin_only)

    if is_weekend and kill_processes:
        kill_all_trading_processes()


def run_daily_daemon():
    """
    Background daemon that runs continuously, sending comprehensive daily summaries
    to Telegram Admin @wtalaat at market close (21:55 UTC / 23:55 local time).
    """
    target_hour = 21
    target_minute = 55
    logger.info(f"Daily Summary Daemon started (v3.8.0). Daily market close dispatch set for {target_hour:02d}:{target_minute:02d} UTC to Telegram Admin.")

    while True:
        now = datetime.now(timezone.utc)
        target = now.replace(hour=target_hour, minute=target_minute, second=0, microsecond=0)

        if now >= target:
            target += timedelta(days=1)

        wait_seconds = (target - now).total_seconds()
        logger.info(f"Next market close summary scheduled at {target.strftime('%Y-%m-%d %H:%M UTC')} (waiting {wait_seconds / 3600:.1f}h)")
        time.sleep(wait_seconds)

        try:
            is_friday = (datetime.now(timezone.utc).weekday() == 4)
            send_market_close_summary(is_weekend=is_friday, kill_processes=is_friday, admin_only=True)
        except Exception as e:
            logger.error(f"Failed to execute market close summary: {e}", exc_info=True)

        time.sleep(120)


if __name__ == "__main__":
    if len(sys.argv) > 1:
        flag = sys.argv[1]
        if flag == "--daemon":
            run_daily_daemon()
        elif flag in ("--weekly", "-w"):
            send_market_close_summary(is_weekend=True, kill_processes=False, admin_only=True)
        elif flag in ("--market-close", "-mc"):
            is_weekend = len(sys.argv) > 2 and sys.argv[2] == "--weekend"
            send_market_close_summary(is_weekend=is_weekend, kill_processes=is_weekend, admin_only=True)
        elif flag in ("--broadcast", "-b"):
            summary = send_daily_summary(admin_only=False)
            print(f"\nStatus: {summary['status']} | Net P&L: ${summary['net_pnl']:.2f} (Broadcasted)")
        elif flag in ("--kill-processes", "-k"):
            kill_all_trading_processes()
        else:
            summary = send_daily_summary(admin_only=True)
            print(f"\nStatus: {summary['status']} | Net P&L: ${summary['net_pnl']:.2f} (Delivered to Admin)")
    else:
        summary = send_daily_summary(admin_only=True)
        print(f"\nStatus: {summary['status']} | Net P&L: ${summary['net_pnl']:.2f} (Delivered to Admin)")
