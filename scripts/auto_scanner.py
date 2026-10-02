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
from datetime import datetime, timezone, timedelta

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
        check_confirmation, check_asset_lockout, execute_mt5_order,
        get_daily_realized_pnl
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
        # === v4.0.0 GATE 0.00: Real-Time Max Daily Loss Circuit Breaker ===
        today_realized_pnl = get_daily_realized_pnl()
        open_pos_all = mt5.positions_get()
        floating_pnl = sum(p.profit for p in open_pos_all) if open_pos_all else 0.0
        total_today_pnl = round(today_realized_pnl + floating_pnl, 2)

        if total_today_pnl <= -max_daily_loss:
            logger.critical(
                f"[CIRCUIT BREAKER TRIGGERED] Max daily loss ceiling breached! "
                f"Realized: ${today_realized_pnl:.2f}, Floating: ${floating_pnl:.2f}, Net Today: ${total_today_pnl:.2f} "
                f"<= Ceiling: -${max_daily_loss:.2f}. Halting automated trading."
            )
            broadcast_telegram(
                f"🛑 <b>CIRCUIT BREAKER: MAX DAILY LOSS BREACHED</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"<b>Today Realized PnL:</b> <code>${today_realized_pnl:.2f}</code>\n"
                f"<b>Floating PnL:</b> <code>${floating_pnl:.2f}</code>\n"
                f"<b>Net Today:</b> <b>${total_today_pnl:.2f} USD</b>\n"
                f"<b>Daily Loss Ceiling:</b> <code>-${max_daily_loss:.2f} USD</code>\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"<b>Status:</b> 🔒 <b>AUTOMATED TRADING HALTED FOR 24H</b>\n"
                f"<i>Capital preservation rule enforced. No further orders permitted.</i>"
            )
            return "MAX_DAILY_LOSS_EXCEEDED"

        # === v5.0.0 GATE 0.06: Precision Institutional Killzones & Session Filter ===
        now_utc = datetime.now(timezone.utc)
        cur_min_of_day = now_utc.hour * 60 + now_utc.minute
        is_gold = "XAU" in symbol.upper() or "GOLD" in symbol.upper()

        if is_gold:
            # London Open Killzone: 07:00 UTC (420 min) to 10:30 UTC (630 min)
            # New York Active Killzone: 12:30 UTC (750 min) to 16:30 UTC (990 min)
            in_london_kz = (420 <= cur_min_of_day <= 630)
            in_ny_kz = (750 <= cur_min_of_day <= 990)

            if not (in_london_kz or in_ny_kz):
                if 630 < cur_min_of_day < 750:
                    kz_reason = "European Midday Lunch Lull (10:30 - 12:30 UTC)"
                elif cur_min_of_day > 990 or cur_min_of_day < 420:
                    kz_reason = "Asian / Overnight Illiquidity & NY-Close (16:30 - 07:00 UTC)"
                else:
                    kz_reason = "Off-Killzone Consolidation"

                logger.info(
                    f"[PRECISION KILLZONE] Gold (XAUUSD) trading suspended outside institutional killzones "
                    f"(Current: {now_utc.strftime('%H:%M UTC')} | {kz_reason}). "
                    f"Active Killzones: London Open (07:00-10:30 UTC) & New York Active (12:30-16:30 UTC). Skipping."
                )
                return "OFF_SESSION_GOLD"

        # === v4.1.0 GATE 0.02: Macroeconomic News & High-Impact Event Blackout Gate ===
        try:
            from news_analyzer import check_news_blackout
            is_blackout, blackout_event, blackout_reason, diff_m = check_news_blackout(symbol)
            if is_blackout:
                logger.warning(f"[NEWS BLACKOUT] Trading suspended on {symbol}: {blackout_reason}")
                evt_title = blackout_event.get('title', 'Tier-1 News') if blackout_event else 'Tier-1 News'
                evt_country = blackout_event.get('country', 'USD') if blackout_event else 'USD'
                broadcast_telegram(
                    f"📰 <b>MACRO NEWS BLACKOUT: {symbol}</b>\n"
                    f"━━━━━━━━━━━━━━━━━━━━\n"
                    f"<b>Event:</b> <code>{evt_title}</code> [{evt_country}]\n"
                    f"<b>Status:</b> 🔴 <b>{blackout_reason}</b>\n"
                    f"<b>Action:</b> Automated order execution suspended to prevent slippage and spread spikes.\n"
                    f"<i>Advisory dispatched to Chief Risk Officer @wtalaat.</i>"
                )
                return "NEWS_BLACKOUT"
        except Exception as ex_news:
            logger.warning(f"[NEWS GATE] Could not evaluate news calendar: {ex_news}")

        # === v4.0.0 GATE 0.0: Account Equity Floor & Dynamic Batch Scaling ===
        acc = mt5.account_info()
        if not acc:
            logger.error("Failed to query MT5 account info for equity check")
            return "ACCOUNT_INFO_ERROR"

        if acc.equity < 25.0:
            logger.critical(f"[EQUITY GATE] Account equity (${acc.equity:.2f}) below operating floor ($25.00). Aborting to prevent liquidation.")
            return "INSUFFICIENT_EQUITY"

        configured_batch = int(session.get("concurrent_batch_size", 1))
        if acc.equity < 150.0:
            max_safe_batch = 1
        elif acc.equity < 300.0:
            max_safe_batch = 2
        elif acc.equity < 500.0:
            max_safe_batch = 3
        else:
            max_safe_batch = configured_batch

        batch_size = min(configured_batch, max_safe_batch)
        if batch_size < configured_batch:
            logger.info(f"[EQUITY SIZING] Configured batch ({configured_batch}x) scaled down to {batch_size}x due to equity (${acc.equity:.2f} < threshold).")

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

        # === v3.8.10 GATE 0.1: Concurrency Batch Engine ===
        all_open_pos = mt5.positions_get()
        open_count = len(all_open_pos) if all_open_pos else 0
        if open_count >= batch_size:
            logger.info(
                f"[CONCURRENCY ENGINE] Active batch ({open_count}/{batch_size} trades) currently running. "
                f"Waiting for batch completion before opening next daily round."
            )
            return "ACTIVE_BATCH_IN_PROGRESS"

        symbol_pos = [p for p in (all_open_pos or []) if p.symbol == symbol]
        if len(symbol_pos) >= batch_size:
            logger.info(f"[CONCURRENCY ENGINE] Active trades for {symbol} ({len(symbol_pos)}/{batch_size}) reached limit. Skipping.")
            return "ACTIVE_BATCH_IN_PROGRESS"

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

        # === v5.0.0 GATE 2.1: Paul Tudor Jones 4H 200 EMA Macro Bias Gate ===
        from mt5_connector import get_macro_trend_bias
        macro_info = get_macro_trend_bias(symbol, mt5.TIMEFRAME_H4)
        macro_bias = macro_info.get("bias", "NEUTRAL")
        logger.info(f"[PTJ MACRO GATE] {symbol} 4H Macro Bias: {macro_bias} ({macro_info.get('reason')})")

        if direction == "BUY" and macro_bias == "BEARISH":
            logger.warning(f"[PTJ MACRO REJECTION] Counter-trend BUY blocked on {symbol}: {macro_info.get('reason')}")
            broadcast_telegram(
                f"<b>SCAN {now_str} — {symbol}</b>\n"
                f"VERDICT: REJECTED (PTJ 4H 200 EMA RULE)\n"
                f"Direction: BUY (Lower Band Bounce Attempt)\n"
                f"Status: 🔒 <b>COUNTER-TREND BUY BLOCKED</b>\n"
                f"Reason: <i>{escape_html(macro_info.get('reason'))}</i>\n"
                f"<i>Paul Tudor Jones Rule: Never buy in a macro 4H bear regime below 200 EMA.</i>"
            )
            return "PTJ_MACRO_BEAR_BUY_REJECTED"

        if direction == "SELL" and macro_bias == "BULLISH":
            logger.warning(f"[PTJ MACRO REJECTION] Counter-trend SELL blocked on {symbol}: {macro_info.get('reason')}")
            broadcast_telegram(
                f"<b>SCAN {now_str} — {symbol}</b>\n"
                f"VERDICT: REJECTED (PTJ 4H 200 EMA RULE)\n"
                f"Direction: SELL (Upper Band Bounce Attempt)\n"
                f"Status: 🔒 <b>COUNTER-TREND SELL BLOCKED</b>\n"
                f"Reason: <i>{escape_html(macro_info.get('reason'))}</i>\n"
                f"<i>Paul Tudor Jones Rule: Never short in a macro 4H bull regime above 200 EMA.</i>"
            )
            return "PTJ_MACRO_BULL_SELL_REJECTED"

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

        # === v5.0.0 Dynamic Structure & Volatility-Based SL / TP Engine ===
        # Min SL distance: 1.0 * ATR_1H
        min_stop = atr_1h * 1.0

        if direction == "SELL":
            candidates = [h for h in swing_highs if h > price]
            if not candidates:
                sl_level = round(price + min_stop, digits)
            else:
                sl_level = round(min(candidates) + atr_1h * 0.3, digits)
            sl_distance = round(sl_level - price, digits)

            if sl_distance < min_stop:
                sl_level = round(price + min_stop, digits)
                sl_distance = min_stop

            # Engine-Decided Dynamic Targets:
            # Banker Leg (TP1): Minimum 1.2R or distance to Bollinger midline
            bb_target_dist = abs(price - bb_mid) if (strategy_active == "Bollinger_Mean_Reversion" and bb_mid < price) else (sl_distance * 1.2)
            banker_dist = round(max(sl_distance * 1.2, bb_target_dist), digits)
            tp_banker = round(price - banker_dist, digits)

            # Runner Leg (TP2): 3.5R extension (uncapped runner trailed by trade_monitor)
            runner_dist = round(sl_distance * 3.5, digits)
            tp_runner = round(price - runner_dist, digits)

            tp1 = tp_banker
            tp2 = tp_runner
            tp3 = round(price - sl_distance * 5.0, digits)

        else:  # BUY
            candidates = [l for l in swing_lows if l < price]
            if not candidates:
                sl_level = round(price - min_stop, digits)
            else:
                sl_level = round(max(candidates) - atr_1h * 0.3, digits)
            sl_distance = round(price - sl_level, digits)

            if sl_distance < min_stop:
                sl_level = round(price - min_stop, digits)
                sl_distance = min_stop

            # Engine-Decided Dynamic Targets:
            # Banker Leg (TP1): Minimum 1.2R or distance to Bollinger midline
            bb_target_dist = abs(bb_mid - price) if (strategy_active == "Bollinger_Mean_Reversion" and bb_mid > price) else (sl_distance * 1.2)
            banker_dist = round(max(sl_distance * 1.2, bb_target_dist), digits)
            tp_banker = round(price + banker_dist, digits)

            # Runner Leg (TP2): 3.5R extension (uncapped runner trailed by trade_monitor)
            runner_dist = round(sl_distance * 3.5, digits)
            tp_runner = round(price + runner_dist, digits)

            tp1 = tp_banker
            tp2 = tp_runner
            tp3 = round(price + sl_distance * 5.0, digits)

        # === v5.0.0 Execution & Risk Evaluation ===
        actual_risk = round(safe_lots * contract_size * sl_distance, 2)
        banker_dollars = round(safe_lots * contract_size * (abs(tp_banker - price)), 2)
        runner_dollars = round(safe_lots * contract_size * (abs(tp_runner - price)), 2)

        # === v4.0.0 GATE 7: Symmetrical R:R Check (Minimum 1.0:1 Standard) ===
        rr_ratio = round((abs(tp_banker - price)) / sl_distance, 2) if sl_distance > 0 else 0
        min_req_rr = 1.0  # Institutional 1.0:1 standard (Never risk more than reward)
        if rr_ratio < min_req_rr:
            logger.info(f"[R:R GATE] Dynamic R:R ratio {rr_ratio}:1 below minimum {min_req_rr}:1, rejecting trade")
            return "LOW_RR"

        # === ALL GATES PASSED — PREPARE CONCURRENT BATCH ===
        trades_to_open = max(1, min(batch_size - open_count, max_trades - trades_done))

        # === v4.0.0 GATE 8: Free Margin Buffer & Projected Margin Level Check ===
        mt5_order_type = mt5.ORDER_TYPE_BUY if direction == "BUY" else mt5.ORDER_TYPE_SELL
        margin_per_trade = mt5.order_calc_margin(mt5_order_type, symbol, safe_lots, price)
        if margin_per_trade is None or margin_per_trade <= 0:
            margin_per_trade = (safe_lots * contract_size * price) / (acc.leverage or 100)

        total_required_margin = margin_per_trade * trades_to_open

        # Free Margin Buffer Check (3x required margin)
        if acc.margin_free < 3.0 * total_required_margin:
            logger.warning(
                f"[MARGIN BUFFER GATE] Free margin (${acc.margin_free:.2f}) < 3x required margin "
                f"(${total_required_margin:.2f} for {trades_to_open} trades). Downscaling batch..."
            )
            safe_cnt = int(acc.margin_free // (3.0 * margin_per_trade))
            trades_to_open = max(1, safe_cnt) if safe_cnt > 0 else 1
            total_required_margin = margin_per_trade * trades_to_open
            if acc.margin_free < 2.0 * total_required_margin:
                logger.error(f"[MARGIN GATE REJECTION] Insufficient free margin (${acc.margin_free:.2f}) for even 1 safe trade. Aborting.")
                return "INSUFFICIENT_MARGIN"

        # Projected Margin Level Check (Minimum 400% after opening)
        projected_used_margin = acc.margin + total_required_margin
        projected_margin_level = (acc.equity / projected_used_margin) * 100.0 if projected_used_margin > 0 else 9999.0
        if projected_margin_level < 400.0:
            logger.error(
                f"[MARGIN LEVEL GATE] Projected margin level ({projected_margin_level:.1f}%) < 400% safety buffer "
                f"(Equity: ${acc.equity:.2f}, Projected Margin: ${projected_used_margin:.2f}). Rejecting to prevent stop-out."
            )
            return "LOW_PROJECTED_MARGIN_LEVEL"

        # Account Equity Risk Capping: Max allowed batch risk in dollars (Max 15% equity on small accounts)
        max_batch_risk_allowed = min(max_daily_loss * 0.5, acc.equity * 0.15)
        if (actual_risk * trades_to_open) > max_batch_risk_allowed:
            safe_trades = int(max_batch_risk_allowed // actual_risk)
            if safe_trades < 1:
                logger.error(
                    f"[EQUITY RISK REJECTION] Single trade risk (${actual_risk:.2f}) exceeds max allowed batch risk "
                    f"(${max_batch_risk_allowed:.2f} = 15% of equity ${acc.equity:.2f}). Rejecting to prevent account liquidation."
                )
                return "RISK_EXCEEDS_EQUITY_LIMIT"
            trades_to_open = safe_trades

        executed_orders = []
        now_ts = datetime.now(timezone.utc).strftime('%H%M%S')

        logger.info(f"ALL v5.0.0 GATES PASSED — Executing batch of {trades_to_open} {direction} {symbol} orders @ {price}")
        logger.info(f"SL={sl_level} ({sl_distance} dist) | Banker TP={tp_banker} (+${banker_dollars}) | Runner TP={tp_runner} (+${runner_dollars}) | Lots={safe_lots}/trade")

        last_fail_reason = "Order rejected by MT5 terminal"
        for idx in range(trades_to_open):
            ticket_id = f"TRD-{symbol[:3]}-{now_ts}-{idx+1}"
            is_runner = (idx > 0)
            target_tp = tp_runner if is_runner else tp_banker
            leg_name = "Runner" if is_runner else "Banker"

            ticket = {
                "ticket_id": ticket_id,
                "symbol": symbol,
                "order_type": direction,
                "sl": float(sl_level),
                "tp": float(target_tp),
                "lots": float(safe_lots),
                "strategy": strategy_active,
                "batch_size": batch_size,
                "comment": f"v5.0.0-{leg_name}"
            }
            res = execute_mt5_order(ticket)
            logger.info(f"MT5 execution result ({idx+1}/{trades_to_open}) [{leg_name}]: {res}")
            if isinstance(res, dict):
                if res.get("status") == "SUCCESS":
                    executed_orders.append((ticket_id, res, leg_name, target_tp))
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
            ticket_ids_str = ", ".join([f"<code>{t[0]}</code> ({t[2]})" for t in executed_orders])
            leg_details = f"<b>Leg 1 (Banker TP):</b> <code>${tp_banker}</code> (<b>+${banker_dollars:.2f} USD</b> | 1:{round(abs(tp_banker-price)/sl_distance, 1)}R)\n"
            if len(executed_orders) > 1:
                leg_details += f"<b>Leg 2 (Runner TP):</b> <code>${tp_runner}</code> (<b>+${runner_dollars:.2f} USD</b> | 1:{round(abs(tp_runner-price)/sl_distance, 1)}R Uncapped)\n"

            alert_msg = (
                f"<b>🚀 ASYMMETRIC BATCH EXECUTED — {symbol} {dir_emoji}</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"<b>Batch Structure:</b> <b>{len(executed_orders)}x Concurrent Orders</b>\n"
                f"<b>Tickets:</b> {ticket_ids_str}\n"
                f"<b>Direction:</b> {direction} | <b>Strategy:</b> <code>{strategy_active}</code>\n"
                f"<b>Entry Price:</b> <code>${price:.2f}</code>\n"
                f"<b>Stop Loss:</b> <code>${sl_level}</code> (${sl_distance:.2f} distance)\n"
                f"{leg_details}"
                f"<b>Profit Protection:</b> 80/70 Server SL Armed on Banker | BE+$2 Lock on Runner\n"
                f"<b>Lots:</b> <code>{safe_lots}</code> each (Total: <code>{safe_lots * len(executed_orders):.2f}</code>) | <b>Risk:</b> <code>${actual_risk * len(executed_orders):.2f}</code>\n"
                f"<b>4H Macro Trend:</b> <code>{macro_bias}</code>\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"<b>Execution Progress:</b> <b>Round {current_round}/{total_rounds}</b> ({trades_done_now}/{max_trades} Total Trades)\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"<i>v5.0.0 Institutional Trend & Asymmetric Runner Engine</i>"
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
    # Sunday before 22:00 UTC (Gold opens at 5:00 PM New York = 22:00 UTC)
    if weekday == 6 and hour < 22:
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
                now_utc = datetime.now(timezone.utc)
                if reason == "WEEKEND_CLOSE_FRIDAY":
                    logger.info(f"Market is closed ({reason}). Executing Friday Close Protocol.")
                    try:
                        from daily_summary import send_market_close_summary
                        send_market_close_summary(is_weekend=True, kill_processes=True)
                    except Exception as ex:
                        logger.error(f"Error in market close summary handler: {ex}")
                    break
                else:
                    # Weekend Standby (Saturday or Sunday before 20:55 UTC)
                    # Calculate time remaining until Sunday 20:55 UTC
                    days_ahead = (6 - now_utc.weekday()) % 7
                    target_open = now_utc.replace(hour=22, minute=0, second=0, microsecond=0) + timedelta(days=days_ahead)
                    if target_open <= now_utc:
                        target_open += timedelta(days=7)
                    wait_sec = max(60, int((target_open - now_utc).total_seconds()))
                    wait_hours = wait_sec / 3600.0
                    sleep_chunk = min(900, wait_sec)
                    logger.info(
                        f"[WEEKEND STANDBY] Markets closed ({reason}). "
                        f"Next market open at Sunday 20:55 UTC (in {wait_hours:.1f}h). "
                        f"Engine sleeping for {sleep_chunk // 60}m..."
                    )
                    time.sleep(sleep_chunk)
                    continue

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

