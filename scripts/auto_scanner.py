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

        # === v3.8.7 GATE 0.1: Smart Concurrency & Anti-Stacking Engine ===
        batch_size = int(session.get("concurrent_batch_size", 1))
        all_open_pos = mt5.positions_get()
        open_count = len(all_open_pos) if all_open_pos else 0
        if open_count >= batch_size:
            logger.info(
                f"[CONCURRENCY ENGINE] Active batch ({open_count}/{batch_size} trades) currently running. "
                f"Waiting for batch completion before opening next daily round."
            )
            return "ACTIVE_BATCH_IN_PROGRESS"

        # Check intra-symbol stacking (Max 1 active trade permitted per symbol to eliminate correlated drawdown)
        symbol_pos = [p for p in (all_open_pos or []) if p.symbol == symbol]
        if len(symbol_pos) >= 1:
            logger.info(f"[SMART CONCURRENCY] Position already open on {symbol} (Ticket #{symbol_pos[0].ticket}). Correlated stacking blocked.")
            return "SYMBOL_ALREADY_ACTIVE"

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
        # Engine 1 (Primary): Bollinger 2.0-StdDev Mean Reversion (v3.8.7 Closed-Candle Rule)
        # Engine 2 (Secondary): Multi-Timeframe Structural Trend Breakout
        strategy_active = None
        direction = None

        last_closed_1h = rates_1h[-2]  # fully closed 1H bar
        rates_m15 = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M15, 0, 15)
        last_closed_m15 = rates_m15[-2] if (rates_m15 is not None and len(rates_m15) >= 2) else None

        # Check Bollinger Rebound on completed bars
        tested_lower = (last_closed_1h['low'] <= bb_lower) or (last_closed_m15 and last_closed_m15['low'] <= bb_lower) or (price <= bb_lower * 1.001)
        tested_upper = (last_closed_1h['high'] >= bb_upper) or (last_closed_m15 and last_closed_m15['high'] >= bb_upper) or (price >= bb_upper * 0.999)

        if tested_lower and last_closed_m15 and last_closed_m15['close'] > last_closed_m15['open'] and price >= last_closed_m15['close']:
            strategy_active = "Bollinger_Mean_Reversion"
            direction = "BUY"
            logger.info(f"[ENGINE 1] Bullish Bollinger Rebound confirmed on closed M15 candle for {symbol}")
        elif tested_upper and last_closed_m15 and last_closed_m15['close'] < last_closed_m15['open'] and price <= last_closed_m15['close']:
            strategy_active = "Bollinger_Mean_Reversion"
            direction = "SELL"
            logger.info(f"[ENGINE 1] Bearish Bollinger Rebound confirmed on closed M15 candle for {symbol}")
        elif regime in ["UPTREND", "DOWNTREND"]:
            strategy_active = "Structural_Trend_Breakout"
            direction = "BUY" if regime == "UPTREND" else "SELL"
            logger.info(f"[ENGINE 2] Structural Trend Breakout active on {symbol} ({direction})")
        else:
            logger.info("Market consolidating inside Bollinger Bands or awaiting closed-candle rejection — skipping")
            return "NO_TRADE_CONSOLIDATION"

        # === v3.8.7 GATE 4: Multi-Timeframe Closed-Candle Confirmation ===
        if strategy_active == "Bollinger_Mean_Reversion":
            from mt5_connector import check_bollinger_confirmation
            confirmed, reason = check_bollinger_confirmation(symbol, direction)
        else:
            confirmed, reason = check_confirmation(symbol, direction, mt5.TIMEFRAME_M15)
        logger.info(f"[CONFIRM] {direction} ({strategy_active}): confirmed={confirmed}, reason={reason}")

        if not confirmed:
            broadcast_telegram(
                f"<b>SCAN {now_str} — {symbol}</b>\n"
                f"Strategy: <code>{strategy_active}</code>\n"
                f"Regime: <code>{regime}</code> | ATR: ${atr_1h:.2f}\n"
                f"Direction: {direction}\n"
                f"Confirmation: AWAITING — {escape_html(reason)}\n"
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

        # === ALL GATES PASSED — EXECUTE (SMART CONCURRENCY: 1 TRADE PER SYMBOL) ===
        trades_to_open = 1  # Exactly 1 trade per symbol to eliminate correlated stacking
        executed_orders = []
        now_ts = datetime.now(timezone.utc).strftime('%H%M%S')

        logger.info(f"ALL v3.8.7 GATES PASSED — Executing {direction} {symbol} order @ {price}")
        logger.info(f"SL={sl_level} ({sl_distance} dist) | TP1={tp1} | Lots={safe_lots} / trade | Risk=${actual_risk} | Target=${target_dollars}/trade")

        last_fail_reason = "Order rejected by MT5 terminal"
        for idx in range(trades_to_open):
            ticket_id = f"TRD-{symbol[:3]}-{now_ts}-{idx+1}"
            ticket = {
                "ticket_id": ticket_id,
                "symbol": symbol,
                "order_type": direction,
                "sl": float(sl_level),
                "tp": float(tp1),
                "lots": float(safe_lots),
                "strategy": strategy_active,
                "batch_size": batch_size,
            }
            res = execute_mt5_order(ticket)
            logger.info(f"MT5 execution result ({idx+1}/{trades_to_open}): {res}")
            if isinstance(res, dict):
                if res.get("status") == "SUCCESS":
                    executed_orders.append((ticket_id, res))
                    session["trades_executed"] = int(session.get("trades_executed", 0)) + 1
                    session["leverage_trades_used"] = used + len(executed_orders)
                    save_session(session)
                else:
                    last_fail_reason = res.get("reason") or last_fail_reason
            time.sleep(0.1)

        success = len(executed_orders) > 0

        if success:
            trades_done_now = int(session.get("trades_executed", 0))
            active_batch_size = int(session.get("concurrent_batch_size", 1))
            daily_rounds = int(session.get("daily_rounds", (max_trades // active_batch_size) if active_batch_size > 0 else max_trades))
            current_round = ((trades_done_now - 1) // active_batch_size) + 1 if active_batch_size > 0 else trades_done_now
            total_rounds = max(1, daily_rounds)

            if quota > 0 and session.get("leverage_trades_used", 0) >= quota:
                broadcast_telegram(
                    f"<b>ℹ️ LEVERAGE QUOTA REACHED</b>\n"
                    f"━━━━━━━━━━━━━━━━━━━━\n"
                    f"Completed <b>{quota} trades</b> at <b>{session.get('leverage_multiplier')}x leverage</b>.\n"
                    f"Reverting automatically to baseline <b>{baseline_lev}x leverage</b>."
                )

            save_session(session)

            # Send execution alert to Telegram
            dir_emoji = "🔴 SHORT" if direction == "SELL" else "🟢 LONG"
            ticket_ids_str = ", ".join([f"<code>{t[0]}</code>" for t in executed_orders])
            total_batch_target = target_dollars * len(executed_orders)
            daily_goal = target_dollars * max_trades

            alert_msg = (
                f"<b>🚀 BATCH TRADE EXECUTED — {symbol} {dir_emoji}</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"<b>Batch Size:</b> <b>{len(executed_orders)}x Concurrent Trades</b>\n"
                f"<b>Tickets:</b> {ticket_ids_str}\n"
                f"<b>Direction:</b> {direction}\n"
                f"<b>Entry Price:</b> <code>${price:.2f}</code>\n"
                f"<b>Stop Loss:</b> <code>${sl_level}</code> (${sl_distance:.2f} distance)\n"
                f"<b>Take Profit:</b> <code>${tp1}</code> (<b>+${target_dollars:.2f} / trade</b>)\n"
                f"<b>Batch Profit Target:</b> <b>+${total_batch_target:.2f}</b>\n"
                f"<b>Profit Guard:</b> 80/70 (Arm: +${target_dollars * 0.80:.2f} | Floor: +${target_dollars * 0.70:.2f} per trade)\n"
                f"<b>Lots:</b> <code>{safe_lots}</code> each (Total: <code>{safe_lots * len(executed_orders):.2f}</code>) | <b>Risk:</b> <code>${actual_risk * len(executed_orders):.2f}</code>\n"
                f"<b>R:R:</b> <code>1:{rr_ratio}</code> | <b>Regime:</b> <code>{regime}</code>\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"<b>Execution Progress:</b> <b>Round {current_round}/{total_rounds}</b> ({trades_done_now}/{max_trades} Total Trades)\n"
                f"<b>Daily Profit Goal:</b> <b>+${daily_goal:.2f}</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"<i>v3.8.4 Batch Concurrency & Multi-Round Architecture Active</i>"
            )
            broadcast_telegram(alert_msg)
            logger.info(f"Batch executed ({len(executed_orders)} trades): {ticket_ids_str}. Round {current_round}/{total_rounds}")
            return "EXECUTED"
        else:
            logger.error(f"MT5 order execution failed for batch of {trades_to_open} trades. Reason: {last_fail_reason}")
            action_tip = ""
            if "autotrading" in last_fail_reason.lower() or "10027" in str(last_fail_reason):
                action_tip = "\n👉 <b>ACTION:</b> Click the <b>'Algo Trading'</b> button in MetaTrader 5 (or press <b>Ctrl+E</b>) to turn it green."
            broadcast_telegram(
                f"<b>⚠️ EXECUTION FAILED — {symbol}</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"<b>Reason:</b> <code>{last_fail_reason}</code>\n"
                f"{action_tip}\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"<i>Scanner remains active and will retry on next setup.</i>"
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

