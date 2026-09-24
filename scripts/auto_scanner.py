#!/usr/bin/env python3
"""
AI Autonomous Trading Firm — Autonomous Scan & Execute Daemon (v3.0.0)
Runs on a configurable interval (default 15 min), queries live MT5 data,
applies all v3.0.0 institutional filters, and auto-executes qualifying trades
in Mode D without user confirmation.

Usage:
    python auto_scanner.py [interval_minutes]
"""

import sys
import os
import time
import json
import logging
import numpy as np
from datetime import datetime, timezone

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - AutoScanner - %(levelname)s - %(message)s"
)
logger = logging.getLogger("AutoScanner")

SESSION_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config", "session_state.json")


def load_session():
    """Load session state."""
    if os.path.exists(SESSION_PATH):
        with open(SESSION_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_session(data):
    """Save session state."""
    with open(SESSION_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def ema(data, period):
    """Compute Exponential Moving Average."""
    k = 2.0 / (period + 1)
    result = [float(data[0])]
    for i in range(1, len(data)):
        result.append(float(data[i]) * k + result[-1] * (1.0 - k))
    return result


def find_swing_points(bars, lookback=20):
    """Find swing highs and lows from OHLC bars."""
    recent = bars[-lookback:] if len(bars) >= lookback else bars
    swing_highs = []
    swing_lows = []
    for i in range(1, len(recent) - 1):
        if recent[i]['high'] > recent[i - 1]['high'] and recent[i]['high'] > recent[i + 1]['high']:
            swing_highs.append(float(recent[i]['high']))
        if recent[i]['low'] < recent[i - 1]['low'] and recent[i]['low'] < recent[i + 1]['low']:
            swing_lows.append(float(recent[i]['low']))
    return swing_highs, swing_lows


def find_fvgs(bars, lookback=10):
    """Find Fair Value Gaps in recent candles."""
    recent = bars[-lookback:] if len(bars) >= lookback else bars
    bull_fvgs = []
    bear_fvgs = []
    for i in range(1, len(recent) - 1):
        prev_high = float(recent[i - 1]['high'])
        next_low = float(recent[i + 1]['low'])
        prev_low = float(recent[i - 1]['low'])
        next_high = float(recent[i + 1]['high'])
        if prev_high < next_low:
            bull_fvgs.append((prev_high, next_low))
        if next_high < prev_low:
            bear_fvgs.append((next_high, prev_low))
    return bull_fvgs, bear_fvgs


def escape_html(text):
    """Escape < and > for Telegram HTML."""
    return str(text).replace("<", "&lt;").replace(">", "&gt;")


def run_scan_and_execute(symbol_override=None):
    """
    Full v3.0.0 autonomous scan cycle:
    1. Query MT5 live data
    2. Detect regime, compute ATR, check confirmation, check lockout
    3. If qualifying trade found → auto-execute and alert Telegram
    4. If no trade → log and wait
    """
    try:
        import MetaTrader5 as mt5
    except ImportError:
        logger.error("MetaTrader5 not installed")
        return

    from mt5_connector import (
        MT5Bridge, calculate_atr, detect_regime,
        check_confirmation, check_asset_lockout, execute_mt5_order
    )
    from send_alert import broadcast_telegram

    session = load_session()
    symbol = symbol_override or session.get("active_market", "XAUUSD")
    if symbol == "ALL":
        symbol = "XAUUSD"  # fallback if called without override
    dollar_risk = float(session.get("risk_per_trade_dollars", 10.0))
    max_trades = int(session.get("max_trades", 4))
    trades_done = int(session.get("trades_executed", 0))
    max_daily_loss = float(session.get("max_daily_loss_dollars", 50.0))

    # Check trade count ceiling
    if trades_done >= max_trades:
        logger.info(f"Trade ceiling reached ({trades_done}/{max_trades}). Session complete.")
        broadcast_telegram(
            f"<b>SESSION COMPLETE</b>\n"
            f"Trade ceiling reached: {trades_done}/{max_trades}\n"
            f"<i>No further trades will be executed.</i>"
        )
        return "SESSION_COMPLETE"

    # Connect to MT5
    bridge = MT5Bridge()
    if not bridge.initialize():
        logger.error("Failed to connect to MT5")
        return "MT5_ERROR"

    try:
        tick = mt5.symbol_info_tick(symbol)
        if not tick:
            logger.error(f"No tick data for {symbol}")
            return "NO_DATA"

        symbol_info = mt5.symbol_info(symbol)
        price = tick.bid
        now_str = datetime.now(timezone.utc).strftime("%H:%M UTC")

        # === v3.5.2 GATE 0.0: Cryptographic Anti-Tamper & Skill Integrity Gate ===
        from skill_integrity_guard import verify_skill_integrity
        is_intact, discrepancies = verify_skill_integrity(silent=False)
        if not is_intact:
            logger.critical(f"[SECURITY VIOLATION] Skill integrity check failed: {discrepancies}")
            return "INTEGRITY_VIOLATION"

        # === v3.5.2 GATE 0: Asset Disablement & Policy Filter ===
        if symbol.upper() == "USDJPY":
            logger.info("[ASSET POLICY] USDJPY is disabled due to negative empirical expectancy (7-Year Benchmark PF 0.75). Skipping.")
            return "DISABLED_ASSET"

        if symbol.upper() == "GBPUSD":
            cur_hour = datetime.now(timezone.utc).hour
            if cur_hour < 7 or cur_hour > 16:
                logger.info(f"[SESSION FILTER] GBPUSD restricted outside London/NY active window (Current: {cur_hour}:00 UTC). Skipping.")
                return "OFF_SESSION"

        # === v3.8.3 GATE 0.1: Strict Sequential Anti-Stacking Engine ===
        all_open_pos = mt5.positions_get()
        if all_open_pos and len(all_open_pos) > 0:
            active_p = all_open_pos[0]
            logger.info(
                f"[SEQUENTIAL PIPELINE] Active trade #{active_p.ticket} ({active_p.symbol} {active_p.volume}L) "
                f"is running. Waiting for trade to exit before opening next sequential round."
            )
            return "ACTIVE_TRADE_IN_PROGRESS"

        # === v3.3.0 GATE 1: Lockout Check ===
        locked, locked_until = check_asset_lockout(symbol)
        if locked:
            logger.info(f"[LOCKOUT] {symbol} is locked until {locked_until}")
            broadcast_telegram(
                f"<b>SCAN {now_str} — {symbol}</b>\n"
                f"VERDICT: NO TRADE\n"
                f"Reason: 2-Strike Lockout active until {escape_html(str(locked_until))}"
            )
            return "LOCKED"

        # === v3.4.0 GATE 2: Multi-Engine Strategy Selection ===
        regime = detect_regime(symbol)
        logger.info(f"[REGIME] {symbol}: {regime}")

        # Compute Bollinger Bands & ATR
        rates_1h = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_H1, 0, 50)
        if rates_1h is None or len(rates_1h) < 25:
            logger.error("Not enough 1H rates")
            return "NO_DATA"

        closes_1h = np.array([r['close'] for r in rates_1h])
        bb_mid = np.mean(closes_1h[-20:])
        bb_std = np.std(closes_1h[-20:])
        bb_upper = bb_mid + 2.0 * bb_std
        bb_lower = bb_mid - 2.0 * bb_std

        atr_1h = calculate_atr(symbol, mt5.TIMEFRAME_H1, 14)
        if atr_1h is None or atr_1h <= 0:
            logger.error("Could not compute ATR")
            return "ATR_ERROR"
        min_stop = atr_1h * 1.5
        logger.info(f"[BB] Mid={bb_mid:.4f} | Upper={bb_upper:.4f} | Lower={bb_lower:.4f} | ATR={atr_1h:.4f}")

        # Strategy Selection:
        # Engine 1 (Primary): Bollinger 2.0-StdDev Mean Reversion (#1 Tournament Winner: 67% WR, PF 2.36-2.95)
        # Engine 2 (Secondary): Multi-Timeframe Structural Trend Breakout
        strategy_active = None
        direction = None
        last_bar = rates_1h[-1]

        # Check Bollinger Rebound
        if last_bar['low'] <= bb_lower and price > bb_lower and last_bar['close'] > last_bar['open']:
            strategy_active = "Bollinger_Mean_Reversion"
            direction = "BUY"
            logger.info(f"[ENGINE 1] Bullish Bollinger 2.0-StdDev Rebound detected on {symbol}")
        elif last_bar['high'] >= bb_upper and price < bb_upper and last_bar['close'] < last_bar['open']:
            strategy_active = "Bollinger_Mean_Reversion"
            direction = "SELL"
            logger.info(f"[ENGINE 1] Bearish Bollinger 2.0-StdDev Rebound detected on {symbol}")
        elif regime in ["UPTREND", "DOWNTREND"]:
            strategy_active = "Structural_Trend_Breakout"
            direction = "BUY" if regime == "UPTREND" else "SELL"
            logger.info(f"[ENGINE 2] Structural Trend Breakout active on {symbol} ({direction})")
        else:
            logger.info("Market is consolidating inside Bollinger Bands without extreme extension — skipping")
            return "NO_TRADE_CONSOLIDATION"

        # === v3.4.0 GATE 4: Confirmation Entry ===
        confirmed, reason = check_confirmation(symbol, direction, mt5.TIMEFRAME_M15)
        logger.info(f"[CONFIRM] {direction} ({strategy_active}): confirmed={confirmed}, reason={reason}")

        if not confirmed and strategy_active != "Bollinger_Mean_Reversion":
            broadcast_telegram(
                f"<b>SCAN {now_str} — {symbol}</b>\n"
                f"Strategy: <code>{strategy_active}</code>\n"
                f"Regime: <code>{regime}</code> | ATR: ${atr_1h:.2f}\n"
                f"Direction: {direction}\n"
                f"Confirmation: NOT YET — {escape_html(reason)}\n"
                f"<b>VERDICT: MONITORING</b>"
            )
            return "NO_CONFIRMATION"

        # === v3.0.0 GATE 5: Structure-Based SL/TP ===
        bars_1h = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_H1, 0, 50)
        if bars_1h is None or len(bars_1h) < 10:
            logger.error("Not enough 1H bars for structure analysis")
            return "NO_BARS"

        swing_highs, swing_lows = find_swing_points(bars_1h)

        digits = symbol_info.digits if symbol_info else (5 if "USD" in symbol and "XAU" not in symbol else 2)

        # === v3.8.3 Sizing & Target Engine ($25.00 Fixed Profit / Trade) ===
        is_gold = "XAU" in symbol or "GOLD" in symbol
        contract_size = symbol_info.trade_contract_size if symbol_info.trade_contract_size > 0 else (100.0 if is_gold else 100000.0)

        quota = int(session.get("leverage_trades_quota", 9999))
        used = int(session.get("leverage_trades_used", 0))
        baseline_lev = float(session.get("baseline_leverage", 1.0))

        if used < quota:
            active_lev = float(session.get("leverage_multiplier", 1.0))
        else:
            active_lev = baseline_lev
            logger.info(f"[LEVERAGE QUOTA] Quota reached ({quota} trades). Reverted to {baseline_lev}x baseline.")

        target_dollars = float(session.get("target_profit_per_trade", 25.0))
        dollar_risk = float(session.get("risk_per_trade_dollars", 25.0)) * active_lev

        if is_gold:
            base_gold_lots = float(session.get("default_lots", 0.01))
            safe_lots = round(base_gold_lots * active_lev, 2)
            safe_lots = max(symbol_info.volume_min, min(symbol_info.volume_max, safe_lots))
        else:
            base_lots = float(session.get("default_lots", 0.01))
            safe_lots = round(base_lots * active_lev, 2)
            safe_lots = max(symbol_info.volume_min, min(symbol_info.volume_max, safe_lots))
            step = symbol_info.volume_step
            if step > 0:
                safe_lots = round(safe_lots / step) * step
            safe_lots = min(safe_lots, 0.50)

        # Dynamic target distance in price to produce EXACTLY target_dollars ($25.00)
        target_dist = round(target_dollars / (safe_lots * contract_size), digits)

        if direction == "SELL":
            # SL above nearest swing high + ATR buffer
            candidates = [h for h in swing_highs if h > price]
            if not candidates:
                sl_level = round(price + min_stop, digits)
            else:
                sl_level = round(min(candidates) + atr_1h * 0.3, digits)
            sl_distance = round(sl_level - price, digits)

            if sl_distance < min_stop:
                sl_level = round(price + min_stop, digits)
                sl_distance = min_stop

            if is_gold:
                # Target $25.00 profit dynamically sized per lot
                tp1 = round(price - target_dist, digits)
                tp2 = round(price - target_dist * 1.25, digits)
                tp3 = round(price - target_dist * 1.50, digits)
            elif strategy_active == "Bollinger_Mean_Reversion" and bb_mid < price:
                tp1 = round(bb_mid, digits)
                tp2 = round(bb_lower, digits) if bb_lower < bb_mid else round(price - sl_distance * 1.8, digits)
                tp3 = round(price - sl_distance * 2.5, digits)
            else:
                tp1 = round(price - sl_distance * 1.0, digits) # Fast 1.0R initial target
                tp2 = round(price - sl_distance * 2.0, digits)
                tp3 = round(price - sl_distance * 3.0, digits)

        else:  # BUY
            # SL below nearest swing low - ATR buffer
            candidates = [l for l in swing_lows if l < price]
            if not candidates:
                sl_level = round(price - min_stop, digits)
            else:
                sl_level = round(max(candidates) - atr_1h * 0.3, digits)
            sl_distance = round(price - sl_level, digits)

            if sl_distance < min_stop:
                sl_level = round(price - min_stop, digits)
                sl_distance = min_stop

            if is_gold:
                # Target $25.00 profit dynamically sized per lot
                tp1 = round(price + target_dist, digits)
                tp2 = round(price + target_dist * 1.25, digits)
                tp3 = round(price + target_dist * 1.50, digits)
            elif strategy_active == "Bollinger_Mean_Reversion" and bb_mid > price:
                tp1 = round(bb_mid, digits)
                tp2 = round(bb_upper, digits) if bb_upper > bb_mid else round(price + sl_distance * 1.8, digits)
                tp3 = round(price + sl_distance * 2.5, digits)
            else:
                tp1 = round(price + sl_distance * 1.0, digits) # Fast 1.0R initial target
                tp2 = round(price + sl_distance * 2.0, digits)
                tp3 = round(price + sl_distance * 3.0, digits)

        # === v3.8.3 Execution & Risk Evaluation ===
        actual_risk = round(safe_lots * contract_size * sl_distance, 2)

        # === v3.6.0 GATE 7: R:R Check ===
        rr_ratio = round((abs(tp1 - price)) / sl_distance, 2) if sl_distance > 0 else 0
        min_req_rr = 0.7 if is_gold else (0.8 if strategy_active == "Bollinger_Mean_Reversion" else 0.95)
        if rr_ratio < min_req_rr:
            logger.info(f"R:R ratio {rr_ratio} below minimum {min_req_rr}, rejecting")
            return "LOW_RR"

        # === ALL GATES PASSED — EXECUTE ===
        ticket_id = f"TRD-{symbol[:3]}-{datetime.now(timezone.utc).strftime('%H%M')}"
        ticket = {
            "ticket_id": ticket_id,
            "symbol": symbol,
            "order_type": direction,
            "sl": float(sl_level),
            "tp": float(tp1),
            "lots": float(safe_lots),
            "strategy": strategy_active,
        }

        logger.info(f"ALL v3.8.3 GATES PASSED — Executing {direction} {symbol} @ {price}")
        logger.info(f"SL={sl_level} ({sl_distance} dist) | TP1={tp1} | Lots={safe_lots} | Risk=${actual_risk} | Target=${target_dollars}")

        # Execute in MT5
        result = execute_mt5_order(ticket)
        logger.info(f"MT5 execution result: {result}")

        success = isinstance(result, dict) and result.get("status") == "SUCCESS"

        if success:
            # Update session counter and leverage quota
            session["trades_executed"] = trades_done + 1
            session["leverage_trades_used"] = used + 1
            
            if session["leverage_trades_used"] == quota:
                broadcast_telegram(
                    f"<b>ℹ️ LEVERAGE QUOTA REACHED</b>\n"
                    f"━━━━━━━━━━━━━━━━━━━━\n"
                    f"Completed <b>{quota} trades</b> at <b>{session.get('leverage_multiplier')}x leverage</b>.\n"
                    f"Reverting automatically to baseline <b>{baseline_lev}x leverage</b>."
                )
            
            save_session(session)

            # Send execution alert to Telegram
            dir_emoji = "SHORT" if direction == "SELL" else "LONG"
            round_idx = trades_done + 1
            alert_msg = (
                f"<b>TRADE EXECUTED — {symbol} {dir_emoji} (ROUND {round_idx}/{max_trades})</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"<b>Ticket:</b> <code>{ticket_id}</code>\n"
                f"<b>Direction:</b> {direction}\n"
                f"<b>Entry:</b> <code>${price:.2f}</code>\n"
                f"<b>Stop Loss:</b> <code>${sl_level}</code> (${sl_distance:.2f} distance)\n"
                f"<b>Take Profit:</b> <code>${tp1}</code> (<b>+${target_dollars:.2f} Target</b>)\n"
                f"<b>Profit Guard:</b> 80/70 (Arm: +${target_dollars * 0.80:.2f} | Floor: +${target_dollars * 0.70:.2f})\n"
                f"<b>Lots:</b> <code>{safe_lots}</code> | <b>Risk:</b> <code>${actual_risk}</code>\n"
                f"<b>R:R:</b> <code>1:{rr_ratio}</code>\n"
                f"<b>Regime:</b> <code>{regime}</code>\n"
                f"<b>Sequential Progress:</b> <b>{round_idx}/{max_trades} Trades</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"<i>v3.8.3 Sequential Multi-Trade Architecture Active</i>"
            )
            broadcast_telegram(alert_msg)
            logger.info(f"Trade {ticket_id} executed and alert sent. ({round_idx}/{max_trades})")
            return "EXECUTED"
        else:
            logger.error(f"MT5 order execution failed for {ticket_id}")
            broadcast_telegram(
                f"<b>EXECUTION FAILED — {symbol}</b>\n"
                f"Order rejected by MT5 terminal.\n"
                f"<i>Check terminal for details.</i>"
            )
            return "EXEC_FAILED"

    except Exception as e:
        logger.error(f"Scan cycle error: {e}", exc_info=True)
        return "ERROR"
    finally:
        try:
            mt5.shutdown()
        except Exception:
            pass


def is_market_closed():
    """
    Checks if global Forex & Metals markets are closed for the weekend.
    Friday >= 21:55 UTC through Sunday < 21:00 UTC.
    """
    now = datetime.now(timezone.utc)
    weekday = now.weekday()  # 0=Mon, 4=Fri, 5=Sat, 6=Sun
    hour = now.hour
    minute = now.minute

    # Friday after 21:55 UTC
    if weekday == 4 and (hour > 21 or (hour == 21 and minute >= 55)):
        return True, "WEEKEND_CLOSE_FRIDAY"
    # Saturday (all day)
    if weekday == 5:
        return True, "WEEKEND_CLOSE_SATURDAY"
    # Sunday before 21:00 UTC
    if weekday == 6 and (hour < 20 or (hour == 20 and minute < 55)):
        return True, "WEEKEND_CLOSE_SUNDAY"

    return False, "MARKET_OPEN"


def start_auto_scanner(interval_minutes=15):
    """Main daemon loop — scans and auto-executes on interval with market close awareness."""
    logger.info(f"Auto-Scanner Daemon v3.7.0 started. Interval: {interval_minutes} min.")
    logger.info("All v3.7.0 gates active: ATR Floor, Confirmation, Lockout, Regime, R:R, Market-Close Safe Shutdown")

    while True:
        try:
            # Check for weekend market closure
            closed, reason = is_market_closed()
            if closed:
                logger.info(f"Market is closed ({reason}). Executing Market Close Protocol and terminating.")
                try:
                    from daily_summary import send_market_close_summary
                    send_market_close_summary(is_weekend=True, kill_processes=True)
                except Exception as ex:
                    logger.error(f"Error in market close summary handler: {ex}")
                break

            session = load_session()
            if not session.get("is_active", True):
                logger.info("Session is marked INACTIVE. Daemon stopping.")
                break

            trades_done = int(session.get("trades_executed", 0))
            max_trades = int(session.get("max_trades", 4))

            if trades_done >= max_trades:
                logger.info(f"Session complete ({trades_done}/{max_trades}). Daemon stopping.")
                break

            # Resolve watchlist from session state
            raw_watchlist = session.get("watchlist", [])
            if raw_watchlist and isinstance(raw_watchlist, list):
                watchlist = raw_watchlist
            else:
                active = session.get("active_market", "EURUSD, XAUUSD")
                if active == "ALL":
                    watchlist = ["EURUSD", "XAUUSD"]
                elif "," in str(active):
                    watchlist = [s.strip() for s in str(active).split(",")]
                else:
                    watchlist = [str(active)]

            for sym in watchlist:
                # Re-check trade ceiling before each symbol
                session = load_session()
                if int(session.get("trades_executed", 0)) >= max_trades:
                    logger.info(f"Trade ceiling reached during multi-asset scan.")
                    break

                logger.info(f"--- Scanning {sym} ---")
                result = run_scan_and_execute(symbol_override=sym)
                logger.info(f"[{sym}] Scan result: {result}")

                if result == "SESSION_COMPLETE":
                    break

        except Exception as e:
            logger.error(f"Daemon loop error: {e}", exc_info=True)

        time.sleep(interval_minutes * 60)

    logger.info("Auto-Scanner Daemon shutting down.")


if __name__ == "__main__":
    interval = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 15
    start_auto_scanner(interval)

