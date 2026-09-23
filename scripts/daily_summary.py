#!/usr/bin/env python3
"""
AI Autonomous Trading Firm — Daily Trade Summary Reporter (v3.0.0)
Queries MT5 deal history for the current day, calculates win/loss stats,
and broadcasts a formatted summary to Telegram.

Usage:
    python daily_summary.py           # Send today's summary now
    python daily_summary.py --daemon  # Run daily at 23:55 UTC automatically
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

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - DailySummary - %(levelname)s - %(message)s"
)
logger = logging.getLogger("DailySummary")

SESSION_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config", "session_state.json")
JOURNAL_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "journal")


def load_session():
    """Load session state."""
    if os.path.exists(SESSION_PATH):
        with open(SESSION_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_journal_entry(date_str, summary_data):
    """Persist daily summary to journal directory for historical records."""
    os.makedirs(JOURNAL_DIR, exist_ok=True)
    path = os.path.join(JOURNAL_DIR, f"summary_{date_str}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(summary_data, f, indent=2, default=str)
    logger.info(f"Journal saved: {path}")


def get_daily_deals():
    """Query MT5 for all closed deals from today (00:00 UTC to now)."""
    try:
        import MetaTrader5 as mt5
    except ImportError:
        logger.error("MetaTrader5 not installed")
        return None, None

    if not mt5.initialize():
        logger.error(f"MT5 initialize failed: {mt5.last_error()}")
        return None, None

    now = datetime.now(timezone.utc)
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    # Get all deals for today
    deals = mt5.history_deals_get(day_start, now)
    account = mt5.account_info()

    mt5.shutdown()
    return deals, account


def build_summary():
    """Build a complete daily trade summary from MT5 deal history."""
    deals, account = get_daily_deals()
    now = datetime.now(timezone.utc)
    date_str = now.strftime("%Y-%m-%d")

    summary = {
        "date": date_str,
        "timestamp": now.isoformat(),
        "account_balance": 0.0,
        "account_equity": 0.0,
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

    if account:
        summary["account_balance"] = account.balance
        summary["account_equity"] = account.equity

    if deals is None or len(deals) == 0:
        summary["status"] = "NO_TRADES"
        return summary

    # Filter for actual trade closes (DEAL_ENTRY_OUT = 1, not deposits/withdrawals)
    closed_trades = []
    for deal in deals:
        # deal.entry: 0=IN, 1=OUT, 2=INOUT, 3=OUT_BY
        # deal.type: 0=BUY, 1=SELL (we want actual trades, not balance operations)
        if deal.entry == 1 and deal.type in (0, 1) and deal.profit != 0:
            closed_trades.append({
                "ticket": deal.ticket,
                "order": deal.order,
                "symbol": deal.symbol,
                "type": "BUY" if deal.type == 0 else "SELL",
                "volume": deal.volume,
                "price": deal.price,
                "profit": round(deal.profit, 2),
                "commission": round(deal.commission, 2) if deal.commission else 0.0,
                "swap": round(deal.swap, 2) if deal.swap else 0.0,
                "time": datetime.fromtimestamp(deal.time, tz=timezone.utc).strftime("%H:%M:%S UTC"),
                "comment": deal.comment or ""
            })

    summary["total_trades"] = len(closed_trades)
    summary["trades"] = closed_trades

    for trade in closed_trades:
        net = trade["profit"] + trade["commission"] + trade["swap"]
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

    summary["net_pnl"] = round(summary["total_profit"] - summary["total_loss"], 2)
    summary["total_profit"] = round(summary["total_profit"], 2)
    summary["total_loss"] = round(summary["total_loss"], 2)
    summary["largest_win"] = round(summary["largest_win"], 2)
def get_weekly_deals():
    """Query MT5 for all closed deals from the start of the current week (Monday 00:00 UTC to now)."""
    try:
        import MetaTrader5 as mt5
    except ImportError:
        logger.error("MetaTrader5 not installed")
        return None, None

    if not mt5.initialize():
        logger.error(f"MT5 initialize failed: {mt5.last_error()}")
        return None, None

    now = datetime.now(timezone.utc)
    # Find Monday 00:00:00 UTC of current week
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
        summary["profit_factor"] = float("inf")

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
    pf_display = f"{summary['profit_factor']:.2f}" if summary["profit_factor"] != float("inf") else "INF"

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
        f"🎯 <b>Win Rate:</b> <b>{summary['win_rate']}%</b> ({summary['wins']}W - {summary['losses']}L - {summary['breakeven']}BE)\n"
        f"📊 <b>Profit Factor:</b> <b>{pf_display}</b>\n\n"
        f"<b>WEEKLY METRICS:</b>\n"
        f"  • Total Closed Trades: <b>{summary['total_trades']}</b>\n"
        f"  • Gross Profit: <code>+${summary['total_profit']:.2f}</code>\n"
        f"  • Gross Loss: <code>-${summary['total_loss']:.2f}</code>\n"
        f"  • Best Trade: <code>+${summary['largest_win']:.2f}</code>\n"
        f"  • Worst Trade: <code>${summary['largest_loss']:.2f}</code>\n\n"
        f"<b>TRADE LOG:</b>\n"
        f"<code>{trade_block}</code>\n\n"
        f"🛑 <b>WEEKEND MARKET CLOSE STATUS:</b>\n"
        f"  • Open Exposure: <b>0 (100% Flat & Protected)</b>\n"
        f"  • Background Daemons: <b>Terminated / Standby</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"<i>AI Autonomous Trading Firm v3.7.0 • Capital 100% Safe</i>"
    )
    return msg


def kill_all_trading_processes():
    """
    Terminates all active trading background processes on market close.
    Kills: auto_scanner.py, trade_monitor.py, telegram_listener.py, and other background runners.
    """
    my_pid = os.getpid()
    logger.info("Executing Market Close Kill Switch — Terminating all background trading processes...")
    
    # 1. Update session state to inactive
    try:
        session = load_session()
        session["is_active"] = False
        session["shutdown_reason"] = "MARKET_CLOSE_AUTO_TERMINATION"
        session["shutdown_time"] = datetime.now(timezone.utc).isoformat()
        with open(SESSION_PATH, "w", encoding="utf-8") as f:
            json.dump(session, f, indent=2)
        logger.info("Session state marked INACTIVE in session_state.json")
    except Exception as e:
        logger.error(f"Error updating session state on shutdown: {e}")

    # 2. Terminate background processes on Windows (auto_scanner and trade_monitor only; preserve telegram_listener)
    killed_count = 0
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
        killed_count = len(pids)
        logger.info(f"Terminated {killed_count} background process(es): {pids}")
    except Exception as e:
        logger.error(f"Error terminating background processes: {e}")
        
    return killed_count


def send_market_close_summary(is_weekend=False, kill_processes=True):
    """
    Dispatches the appropriate market close summary (Daily or Weekly) and terminates processes.
    """
    from send_alert import broadcast_telegram
    now = datetime.now(timezone.utc)
    
    if is_weekend or now.weekday() in (4, 5, 6): # Friday close or weekend
        logger.info("Generating and sending Weekly Market Close Summary...")
        weekly_summary = build_weekly_summary()
        save_journal_entry(f"weekly_{weekly_summary['week']}", weekly_summary)
        msg = format_telegram_weekly_summary(weekly_summary)
        broadcast_telegram(msg)
        logger.info("Weekly Market Close Summary delivered to Telegram.")
    else:
        logger.info("Generating and sending Daily Market Close Summary...")
        daily_summary = build_summary()
        save_journal_entry(daily_summary["date"], daily_summary)
        msg = format_telegram_summary(daily_summary)
        broadcast_telegram(msg)
        logger.info("Daily Market Close Summary delivered to Telegram.")

    if kill_processes:
        kill_all_trading_processes()


def format_telegram_summary(summary):
    """Format the summary as a Telegram HTML message."""
    date = summary["date"]
    status = summary["status"]

    if status == "NO_TRADES":
        return (
            f"<b>DAILY SUMMARY — {date}</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"No trades executed today.\n"
            f"Balance: <code>${summary['account_balance']:,.2f}</code>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"<i>AI Autonomous Trading Firm v3.7.0</i>"
        )

    pnl = summary["net_pnl"]
    pnl_emoji = "+" if pnl >= 0 else ""
    result_emoji = "PROFIT DAY" if pnl >= 0 else "LOSS DAY"
    bar_emoji = "🟢" if pnl >= 0 else "🔴"

    # Build trade-by-trade breakdown
    trade_lines = []
    for i, t in enumerate(summary["trades"], 1):
        net = t["profit"] + t["commission"] + t["swap"]
        icon = "W" if net > 0 else ("L" if net < 0 else "BE")
        sign = "+" if net >= 0 else ""
        trade_lines.append(
            f"  {i}. {t['symbol']} {t['type']} {t['volume']}L "
            f"@ {t['time']} — [{icon}] {sign}${net:.2f}"
        )
    trade_block = "\n".join(trade_lines) if trade_lines else "  No closed trades"

    # Win streak / loss streak
    streaks = []
    current = 0
    for t in summary["trades"]:
        net = t["profit"] + t["commission"] + t["swap"]
        if net > 0:
            current = max(0, current) + 1
        elif net < 0:
            current = min(0, current) - 1
        streaks.append(current)
    max_win_streak = max(streaks) if streaks else 0
    max_loss_streak = abs(min(streaks)) if streaks else 0

    pf_display = f"{summary['profit_factor']:.2f}" if summary["profit_factor"] != float("inf") else "INF"

    msg = (
        f"<b>{bar_emoji} DAILY TRADE SUMMARY — {date}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"<b>Result:</b> {bar_emoji} <b>{result_emoji}</b>\n"
        f"<b>Net P&amp;L:</b> <code>{pnl_emoji}${pnl:.2f}</code>\n\n"
        f"<b>STATS:</b>\n"
        f"  Total Trades: <b>{summary['total_trades']}</b>\n"
        f"  Wins: <b>{summary['wins']}</b> | Losses: <b>{summary['losses']}</b> | BE: <b>{summary['breakeven']}</b>\n"
        f"  Win Rate: <b>{summary['win_rate']}%</b>\n"
        f"  Gross Profit: <code>+${summary['total_profit']:.2f}</code>\n"
        f"  Gross Loss: <code>-${summary['total_loss']:.2f}</code>\n"
        f"  Profit Factor: <b>{pf_display}</b>\n"
        f"  Largest Win: <code>+${summary['largest_win']:.2f}</code>\n"
        f"  Largest Loss: <code>${summary['largest_loss']:.2f}</code>\n"
        f"  Max Win Streak: <b>{max_win_streak}</b> | Max Loss Streak: <b>{max_loss_streak}</b>\n\n"
        f"<b>TRADE LOG:</b>\n"
        f"<code>{trade_block}</code>\n\n"
        f"<b>ACCOUNT:</b>\n"
        f"  Balance: <code>${summary['account_balance']:,.2f}</code>\n"
        f"  Equity: <code>${summary['account_equity']:,.2f}</code>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"<i>AI Autonomous Trading Firm v3.7.0 — Daily Report</i>"
    )
    return msg


def send_daily_summary():
    """Build, format, save, and broadcast the daily summary."""
    logger.info("Generating daily trade summary...")
    summary = build_summary()

    # Save to journal
    save_journal_entry(summary["date"], summary)

    # Format and send
    msg = format_telegram_summary(summary)
    from send_alert import broadcast_telegram
    delivered = broadcast_telegram(msg)
    logger.info(f"Daily summary sent to {delivered} destination(s)")
    return summary


def run_daily_daemon():
    """
    Background daemon that sends daily/weekly summaries at market close (21:55 UTC)
    and automatically kills running processes on weekend market close.
    """
    target_hour = 21
    target_minute = 55
    logger.info(f"Daily Summary Daemon started (v3.7.0). Market close trigger set for {target_hour:02d}:{target_minute:02d} UTC.")

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
            send_market_close_summary(is_weekend=is_friday, kill_processes=is_friday)
        except Exception as e:
            logger.error(f"Failed to execute market close summary: {e}", exc_info=True)

        time.sleep(120)


if __name__ == "__main__":
    if len(sys.argv) > 1:
        flag = sys.argv[1]
        if flag == "--daemon":
            run_daily_daemon()
        elif flag in ("--weekly", "-w"):
            send_market_close_summary(is_weekend=True, kill_processes=False)
        elif flag in ("--market-close", "-mc"):
            is_weekend = len(sys.argv) > 2 and sys.argv[2] == "--weekend"
            send_market_close_summary(is_weekend=is_weekend, kill_processes=True)
        elif flag in ("--kill-processes", "-k"):
            kill_all_trading_processes()
        else:
            summary = send_daily_summary()
            print(f"\nStatus: {summary['status']} | Net P&L: ${summary['net_pnl']:.2f}")
    else:
        summary = send_daily_summary()
        print(f"\nStatus: {summary['status']} | Net P&L: ${summary['net_pnl']:.2f}")

