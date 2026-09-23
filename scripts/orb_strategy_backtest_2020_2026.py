#!/usr/bin/env python3
"""
AI Autonomous Trading Firm — Opening Range Breakout (ORB) Quantitative Benchmark (2020-2026 YTD)
Tests 4 variations of Opening Range Breakout across EURUSD, GBPUSD, XAUUSD, USDJPY:
  1. London 1-Hour ORB (07:00-08:00 UTC Opening Range -> Trade 08:00-13:00 UTC)
  2. Asian Range Breakout (00:00-07:00 UTC Range -> Trade London Open 07:00-12:00 UTC)
  3. New York 1-Hour ORB (13:00-14:00 UTC Opening Range -> Trade 14:00-18:00 UTC)
  4. Macro Trend-Filtered London ORB (Only trade ORB aligned with 4H 50 EMA)
"""

import sys
import os
import json
import math
from datetime import datetime, timezone, timedelta
import numpy as np
import MetaTrader5 as mt5

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

SPREADS = {
    "XAUUSD": 0.35,
    "EURUSD": 0.00015,
    "GBPUSD": 0.00020,
    "USDJPY": 0.025
}

def load_data(symbol, start_dt, end_dt):
    warmup = start_dt - timedelta(days=60)
    r_1h = mt5.copy_rates_range(symbol, mt5.TIMEFRAME_H1, warmup, end_dt)
    r_4h = mt5.copy_rates_range(symbol, mt5.TIMEFRAME_H4, warmup, end_dt)
    return r_1h, r_4h

def compute_atr(rates, period=14):
    highs = rates['high']
    lows = rates['low']
    closes = rates['close']
    tr = np.zeros(len(rates))
    tr[0] = highs[0] - lows[0]
    for i in range(1, len(rates)):
        tr[i] = max(highs[i] - lows[i], abs(highs[i] - closes[i-1]), abs(lows[i] - closes[i-1]))
    atr = np.zeros(len(rates))
    atr[:period] = np.mean(tr[:period])
    for i in range(period, len(rates)):
        atr[i] = (atr[i-1] * (period - 1) + tr[i]) / period
    return atr

def run_orb_backtest(symbol, r_1h, r_4h, model_type="London_ORB", start_dt=None, end_dt=None, initial_balance=100000.0, risk_pct=0.01):
    symbol_info = mt5.symbol_info(symbol)
    contract_size = symbol_info.trade_contract_size if (symbol_info and symbol_info.trade_contract_size > 0) else 100.0
    spread = SPREADS.get(symbol, 0.0)

    h1_times = r_1h['time']
    h1_highs = r_1h['high']
    h1_lows = r_1h['low']
    h1_closes = r_1h['close']
    h1_opens = r_1h['open']
    h1_atr = compute_atr(r_1h, 14)

    h4_times = r_4h['time']
    h4_closes = r_4h['close']
    ema50_4h = np.convolve(h4_closes, np.ones(50)/50, mode='same')

    start_ts = int(start_dt.timestamp())
    end_ts = int(end_dt.timestamp())
    h4_idx = 0

    balance = initial_balance
    trades = []
    open_pos = None

    # Daily tracking state
    current_day = None
    range_high = None
    range_low = None
    range_established = False
    trade_taken_today = False

    asian_highs = []
    asian_lows = []

    for i in range(50, len(r_1h)):
        t1 = h1_times[i]
        while h4_idx + 1 < len(h4_times) and h4_times[h4_idx + 1] <= t1:
            h4_idx += 1

        if t1 < start_ts or t1 > end_ts:
            continue

        dt_utc = datetime.fromtimestamp(t1, tz=timezone.utc)
        bar_date = dt_utc.date()
        hour = dt_utc.hour

        # Reset day
        if current_day != bar_date:
            current_day = bar_date
            range_high = None
            range_low = None
            range_established = False
            trade_taken_today = False
            asian_highs = []
            asian_lows = []

        # Track Asian Range (00:00 to 06:59 UTC)
        if 0 <= hour < 7:
            asian_highs.append(h1_highs[i])
            asian_lows.append(h1_lows[i])

        # Define Opening Ranges
        if model_type in ["London_ORB", "Trend_Filtered_London_ORB"]:
            # Opening Range is 07:00 UTC bar (London Open Hour)
            if hour == 7:
                range_high = h1_highs[i]
                range_low = h1_lows[i]
                range_established = True

        elif model_type == "Asian_Range_Breakout":
            if hour == 7 and asian_highs and asian_lows:
                range_high = max(asian_highs)
                range_low = min(asian_lows)
                range_established = True

        elif model_type == "New_York_ORB":
            # Opening Range is 13:00 UTC bar (NY Open Hour)
            if hour == 13:
                range_high = h1_highs[i]
                range_low = h1_lows[i]
                range_established = True

        # Position Management
        if open_pos is not None:
            pos = open_pos
            direction = pos['direction']
            hi, lo = h1_highs[i], h1_lows[i]
            is_closed = False
            exit_p, pnl, exit_reason = 0.0, 0.0, ""

            if direction == "BUY":
                if lo <= pos['sl']:
                    exit_p = pos['sl'] - spread
                    exit_reason = "STOP_LOSS"
                    pnl = (exit_p - pos['entry_price']) * pos['remaining_lots'] * contract_size
                    is_closed = True
                else:
                    if not pos['tp1_hit'] and hi >= pos['tp1']:
                        tp1_lots = pos['initial_lots'] * 0.40
                        pos['realized_pnl'] += (pos['tp1'] - pos['entry_price'] - spread) * tp1_lots * contract_size
                        pos['remaining_lots'] -= tp1_lots
                        pos['tp1_hit'] = True
                        pos['sl'] = pos['entry_price'] # Move SL to BE
                    if pos['tp1_hit'] and not pos['tp2_hit'] and hi >= pos['tp2']:
                        tp2_lots = pos['initial_lots'] * 0.40
                        pos['realized_pnl'] += (pos['tp2'] - pos['entry_price'] - spread) * tp2_lots * contract_size
                        pos['remaining_lots'] -= tp2_lots
                        pos['tp2_hit'] = True
                        pos['sl'] = pos['tp1'] # Lock profit
                    if pos['tp2_hit'] and hi >= pos['tp3']:
                        tp3_lots = pos['remaining_lots']
                        pos['realized_pnl'] += (pos['tp3'] - pos['entry_price'] - spread) * tp3_lots * contract_size
                        pos['remaining_lots'] = 0.0
                        exit_p, exit_reason = pos['tp3'], "FULL_TP3_RUNNER"
                        pnl = 0.0
                        is_closed = True

            elif direction == "SELL":
                if hi >= pos['sl']:
                    exit_p = pos['sl'] + spread
                    exit_reason = "STOP_LOSS"
                    pnl = (pos['entry_price'] - exit_p) * pos['remaining_lots'] * contract_size
                    is_closed = True
                else:
                    if not pos['tp1_hit'] and lo <= pos['tp1']:
                        tp1_lots = pos['initial_lots'] * 0.40
                        pos['realized_pnl'] += (pos['entry_price'] - pos['tp1'] - spread) * tp1_lots * contract_size
                        pos['remaining_lots'] -= tp1_lots
                        pos['tp1_hit'] = True
                        pos['sl'] = pos['entry_price']
                    if pos['tp1_hit'] and not pos['tp2_hit'] and lo <= pos['tp2']:
                        tp2_lots = pos['initial_lots'] * 0.40
                        pos['realized_pnl'] += (pos['entry_price'] - pos['tp2'] - spread) * tp2_lots * contract_size
                        pos['remaining_lots'] -= tp2_lots
                        pos['tp2_hit'] = True
                        pos['sl'] = pos['tp1']
                    if pos['tp2_hit'] and lo <= pos['tp3']:
                        tp3_lots = pos['remaining_lots']
                        pos['realized_pnl'] += (pos['entry_price'] - pos['tp3'] - spread) * tp3_lots * contract_size
                        pos['remaining_lots'] = 0.0
                        exit_p, exit_reason = pos['tp3'], "FULL_TP3_RUNNER"
                        pnl = 0.0
                        is_closed = True

            # End of Day Time Exit (Close open position at 21:00 UTC)
            if not is_closed and hour >= 21:
                cur_c = h1_closes[i]
                if direction == "BUY":
                    exit_p = cur_c - spread
                    pnl = (exit_p - pos['entry_price']) * pos['remaining_lots'] * contract_size
                else:
                    exit_p = cur_c + spread
                    pnl = (pos['entry_price'] - exit_p) * pos['remaining_lots'] * contract_size
                exit_reason = "EOD_TIME_STOP"
                is_closed = True

            if is_closed:
                total_trade_pnl = round(pos['realized_pnl'] + pnl, 2)
                r_mult = round(total_trade_pnl / pos['risk_dollars'], 2) if pos['risk_dollars'] > 0 else 0.0
                balance += total_trade_pnl
                trades.append({
                    "symbol": symbol, "direction": direction, "entry_time": pos['entry_time'],
                    "exit_time": t1, "year": dt_utc.year, "pnl": total_trade_pnl, "r_mult": r_mult,
                    "exit_reason": exit_reason, "balance": round(balance, 2)
                })
                open_pos = None

        # Entry Scanning Window
        if open_pos is None and range_established and not trade_taken_today:
            cur_p = h1_closes[i]
            atr1 = h1_atr[i]
            if atr1 <= 0:
                continue

            range_size = range_high - range_low
            # Ignore opening ranges that are abnormally huge (> 3x ATR) or tiny (< 0.2x ATR)
            if range_size > (3.0 * atr1) or range_size < (0.2 * atr1):
                continue

            dollar_risk = balance * risk_pct
            midpoint = (range_high + range_low) / 2.0

            # Trading Hours Windows
            in_window = False
            if model_type in ["London_ORB", "Trend_Filtered_London_ORB", "Asian_Range_Breakout"]:
                in_window = (8 <= hour <= 12)
            elif model_type == "New_York_ORB":
                in_window = (14 <= hour <= 18)

            if in_window:
                # 4H Trend alignment for model 4
                is_macro_bull = True
                is_macro_bear = True
                if model_type == "Trend_Filtered_London_ORB" and h4_idx < len(ema50_4h):
                    e50_4 = ema50_4h[h4_idx]
                    is_macro_bull = (cur_p > e50_4)
                    is_macro_bear = (cur_p < e50_4)

                # Bullish Breakout above Opening Range High
                if cur_p > range_high and is_macro_bull:
                    entry_p = cur_p + spread
                    # Stop loss placed at 50% midpoint of Opening Range
                    sl_level = midpoint
                    sl_dist = max(atr1 * 1.0, entry_p - sl_level)
                    sl_level = entry_p - sl_dist
                    tp1 = entry_p + sl_dist * 1.5
                    tp2 = entry_p + sl_dist * 2.5
                    tp3 = entry_p + sl_dist * 3.5
                    lots = max(0.01, min(5.0, round(dollar_risk / (sl_dist * contract_size), 2)))
                    open_pos = {
                        "direction": "BUY", "entry_price": entry_p, "entry_time": t1, "sl": sl_level,
                        "sl_dist": sl_dist, "tp1": tp1, "tp2": tp2, "tp3": tp3, "initial_lots": lots,
                        "remaining_lots": lots, "tp1_hit": False, "tp2_hit": False, "realized_pnl": 0.0, "risk_dollars": dollar_risk
                    }
                    trade_taken_today = True

                # Bearish Breakdown below Opening Range Low
                elif cur_p < range_low and is_macro_bear:
                    entry_p = cur_p - spread
                    # Stop loss placed at 50% midpoint of Opening Range
                    sl_level = midpoint
                    sl_dist = max(atr1 * 1.0, sl_level - entry_p)
                    sl_level = entry_p + sl_dist
                    tp1 = entry_p - sl_dist * 1.5
                    tp2 = entry_p - sl_dist * 2.5
                    tp3 = entry_p - sl_dist * 3.5
                    lots = max(0.01, min(5.0, round(dollar_risk / (sl_dist * contract_size), 2)))
                    open_pos = {
                        "direction": "SELL", "entry_price": entry_p, "entry_time": t1, "sl": sl_level,
                        "sl_dist": sl_dist, "tp1": tp1, "tp2": tp2, "tp3": tp3, "initial_lots": lots,
                        "remaining_lots": lots, "tp1_hit": False, "tp2_hit": False, "realized_pnl": 0.0, "risk_dollars": dollar_risk
                    }
                    trade_taken_today = True

    # Performance Calculation
    tot_trades = len(trades)
    wins = [t for t in trades if t['pnl'] > 0]
    losses = [t for t in trades if t['pnl'] < 0]
    gp = sum([t['pnl'] for t in wins])
    gl = abs(sum([t['pnl'] for t in losses]))
    net_pnl = round(balance - initial_balance, 2)
    win_rate = round(len(wins)/tot_trades*100, 2) if tot_trades > 0 else 0.0
    pf = round(gp / gl, 2) if gl > 0 else 0.0
    expectancy = round(net_pnl / tot_trades, 2) if tot_trades > 0 else 0.0

    # Max Drawdown
    running = initial_balance
    eq = [running]
    for t in trades:
        running += t['pnl']
        eq.append(running)
    pk = eq[0]
    mdd = 0.0
    for e in eq:
        if e > pk: pk = e
        dd = (pk - e) / pk * 100
        if dd > mdd: mdd = dd

    yearly = {}
    for y in range(2020, 2027):
        y_trades = [t for t in trades if t['year'] == y]
        y_pnl = sum([t['pnl'] for t in y_trades])
        y_wins = [t for t in y_trades if t['pnl'] > 0]
        y_wr = round(len(y_wins)/len(y_trades)*100, 1) if y_trades else 0.0
        label = f"{y} YTD" if y == 2026 else str(y)
        yearly[label] = {"trades": len(y_trades), "pnl": round(y_pnl, 2), "win_rate": y_wr}

    return {
        "symbol": symbol, "model": model_type, "trades": tot_trades, "wins": len(wins),
        "losses": len(losses), "win_rate": win_rate, "net_pnl": net_pnl, "gross_profit": round(gp, 2),
        "gross_loss": round(gl, 2), "pf": pf, "expectancy": expectancy, "max_dd_pct": round(mdd, 2),
        "yearly": yearly
    }

def main():
    if not mt5.initialize():
        print("MT5 Failed")
        sys.exit(1)

    start_dt = datetime(2020, 1, 1, tzinfo=timezone.utc)
    end_dt = datetime(2026, 8, 28, 23, 59, tzinfo=timezone.utc)

    symbols = ["EURUSD", "GBPUSD", "XAUUSD", "USDJPY"]
    orb_models = [
        "London_ORB",
        "Asian_Range_Breakout",
        "New_York_ORB",
        "Trend_Filtered_London_ORB"
    ]

    print("="*110)
    print("      OPENING RANGE BREAKOUT (ORB) QUANTITATIVE BENCHMARK (2020 - 2026 YTD)")
    print("="*110)

    all_data = {}
    for sym in symbols:
        r1, r4 = load_data(sym, start_dt, end_dt)
        all_data[sym] = (r1, r4)
        print(f"Loaded {sym}: {len(r1)} H1 bars.")

    benchmark_matrix = {}

    for model in orb_models:
        print(f"\n============================== {model.upper()} ==============================")
        print(f"{'Symbol':10s} | {'Trades':6s} | {'Win Rate':8s} | {'Profit Factor':13s} | {'Expectancy/Trd':15s} | {'Net P&L':14s} | {'Max DD':8s}")
        print("-" * 88)
        
        benchmark_matrix[model] = {}
        for sym in symbols:
            r1, r4 = all_data[sym]
            res = run_orb_backtest(sym, r1, r4, model_type=model, start_dt=start_dt, end_dt=end_dt)
            benchmark_matrix[model][sym] = res
            pnl_str = f"${res['net_pnl']:+,.2f}"
            print(f"{sym:10s} | {res['trades']:6d} | {res['win_rate']:7.1f}% | {res['pf']:13.2f} | ${res['expectancy']:+13.2f} | {pnl_str:14s} | {res['max_dd_pct']:6.2f}%")

    out_path = r"d:\Techwaves-egy\Trading Team Skills\journal\orb_strategy_benchmark_2020_2026.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(benchmark_matrix, f, indent=2, default=str)
    print(f"\nFull ORB Benchmark saved to: {out_path}")

    mt5.shutdown()

if __name__ == "__main__":
    main()
