#!/usr/bin/env python3
"""
AI Autonomous Trading Firm — Multi-Year M15 High-Precision Strategy Tournament (2020 - 2026)
Executes bar-by-bar on true M15 candles to eliminate intra-bar 1H order bias.
Compares:
  - Model 1: Structural Breakout (v3.1.0)
  - Model 2: 50% Pullback Retest
  - Model 3: 4H Trend Rider
Year-by-Year from 2020 through 2026 across EURUSD, GBPUSD, XAUUSD, USDJPY.
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

def load_rates(symbol, start_dt, end_dt):
    warmup = start_dt - timedelta(days=45)
    r_m15 = mt5.copy_rates_range(symbol, mt5.TIMEFRAME_M15, warmup, end_dt)
    r_h1 = mt5.copy_rates_range(symbol, mt5.TIMEFRAME_H1, warmup, end_dt)
    r_h4 = mt5.copy_rates_range(symbol, mt5.TIMEFRAME_H4, warmup, end_dt)
    return r_m15, r_h1, r_h4

def compute_atr(rates, period=14):
    highs, lows, closes = rates['high'], rates['low'], rates['close']
    tr = np.zeros(len(rates))
    tr[0] = highs[0] - lows[0]
    for i in range(1, len(rates)):
        tr[i] = max(highs[i] - lows[i], abs(highs[i] - closes[i-1]), abs(lows[i] - closes[i-1]))
    atr = np.zeros(len(rates))
    atr[:period] = np.mean(tr[:period])
    for i in range(period, len(rates)):
        atr[i] = (atr[i-1] * (period - 1) + tr[i]) / period
    return atr

def evaluate_year(symbol, r_m15, r_h1, r_h4, year, model="breakout"):
    symbol_info = mt5.symbol_info(symbol)
    contract_size = symbol_info.trade_contract_size if (symbol_info and symbol_info.trade_contract_size > 0) else 100.0
    spread = SPREADS.get(symbol, 0.0)

    h1_times, h1_closes, h1_highs, h1_lows = r_h1['time'], r_h1['close'], r_h1['high'], r_h1['low']
    h1_atr = compute_atr(r_h1, 14)
    h4_times, h4_closes, h4_highs, h4_lows = r_h4['time'], r_h4['close'], r_h4['high'], r_h4['low']

    start_dt = datetime(year, 1, 1, tzinfo=timezone.utc)
    end_dt = datetime(year, 12, 31, 23, 59, tzinfo=timezone.utc)
    start_ts = int(start_dt.timestamp())
    end_ts = int(end_dt.timestamp())

    balance = 100000.0
    trades = []
    open_pos = None
    pending_limit = None
    consecutive_losses = 0
    locked_until_ts = 0

    h1_idx, h4_idx = 0, 0

    for m_idx in range(len(r_m15)):
        m_bar = r_m15[m_idx]
        m_time = m_bar['time']

        while h1_idx + 1 < len(h1_times) and h1_times[h1_idx + 1] <= m_time:
            h1_idx += 1
        while h4_idx + 1 < len(h4_times) and h4_times[h4_idx + 1] <= m_time:
            h4_idx += 1

        if m_time < start_ts or m_time > end_ts:
            continue

        # Process limit order fill on M15
        if pending_limit is not None and open_pos is None:
            p_dir, p_price, p_sl, p_tp1, p_tp2, p_tp3, p_lots, p_exp, p_risk = pending_limit
            if m_time > p_exp:
                pending_limit = None
            else:
                filled = False
                if p_dir == "BUY" and m_bar['low'] <= p_price:
                    filled = True
                    fill_p = p_price + spread
                elif p_dir == "SELL" and m_bar['high'] >= p_price:
                    filled = True
                    fill_p = p_price - spread

                if filled:
                    open_pos = {
                        "direction": p_dir, "entry_price": fill_p, "entry_time": m_time,
                        "sl": p_sl, "sl_dist": abs(fill_p - p_sl), "tp1": p_tp1, "tp2": p_tp2, "tp3": p_tp3,
                        "initial_lots": p_lots, "remaining_lots": p_lots, "tp1_hit": False, "tp2_hit": False,
                        "realized_pnl": 0.0, "risk_dollars": p_risk
                    }
                    pending_limit = None

        # Manage open position on M15
        if open_pos is not None:
            pos = open_pos
            direction = pos['direction']
            hi, lo = m_bar['high'], m_bar['low']
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
                        pos['sl'] = pos['entry_price'] # BE
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
                        pos['sl'] = pos['entry_price'] # BE
                    if pos['tp1_hit'] and not pos['tp2_hit'] and lo <= pos['tp2']:
                        tp2_lots = pos['initial_lots'] * 0.40
                        pos['realized_pnl'] += (pos['entry_price'] - pos['tp2'] - spread) * tp2_lots * contract_size
                        pos['remaining_lots'] -= tp2_lots
                        pos['tp2_hit'] = True
                        pos['sl'] = pos['tp1'] # Lock profit
                    if pos['tp2_hit'] and lo <= pos['tp3']:
                        tp3_lots = pos['remaining_lots']
                        pos['realized_pnl'] += (pos['entry_price'] - pos['tp3'] - spread) * tp3_lots * contract_size
                        pos['remaining_lots'] = 0.0
                        exit_p, exit_reason = pos['tp3'], "FULL_TP3_RUNNER"
                        pnl = 0.0
                        is_closed = True

            if is_closed:
                total_trade_pnl = round(pos['realized_pnl'] + pnl, 2)
                r_mult = round(total_trade_pnl / pos['risk_dollars'], 2) if pos['risk_dollars'] > 0 else 0.0
                balance += total_trade_pnl
                if total_trade_pnl < 0:
                    consecutive_losses += 1
                    if consecutive_losses >= 2:
                        locked_until_ts = m_time + 3600
                else:
                    consecutive_losses = 0

                trades.append({"pnl": total_trade_pnl, "r_mult": r_mult})
                open_pos = None

        # Entry logic
        if open_pos is None and pending_limit is None and m_time >= locked_until_ts:
            if h1_idx < 30 or h4_idx < 30:
                continue

            c4 = h4_closes[max(0, h4_idx-50):h4_idx+1]
            ema50_4h = np.mean(c4[-50:]) if len(c4) >= 50 else np.mean(c4)
            eq_4h = (np.max(h4_highs[max(0, h4_idx-30):h4_idx+1]) + np.min(h4_lows[max(0, h4_idx-30):h4_idx+1])) / 2.0
            
            c1 = h1_closes[max(0, h1_idx-50):h1_idx+1]
            ema20_1h = np.mean(c1[-20:])
            ema50_1h = np.mean(c1[-50:]) if len(c1) >= 50 else np.mean(c1)
            atr_val = h1_atr[h1_idx]
            if atr_val <= 0:
                continue
            min_stop = atr_val * 1.5
            cur_p = m_bar['close']

            is_4h_bull = cur_p > ema50_4h
            is_4h_bear = cur_p < ema50_4h
            is_1h_bull = cur_p > ema20_1h and ema20_1h > ema50_1h
            is_1h_bear = cur_p < ema20_1h and ema20_1h < ema50_1h

            support_4h = np.min(h4_lows[max(0, h4_idx-20):h4_idx+1])
            resistance_4h = np.max(h4_highs[max(0, h4_idx-20):h4_idx+1])

            h1_rates_sub = r_h1[max(0, h1_idx-30):h1_idx+1]
            swing_highs = [h1_rates_sub[k]['high'] for k in range(2, len(h1_rates_sub)-2) 
                           if h1_rates_sub[k]['high'] == max([h1_rates_sub[j]['high'] for j in range(k-2, k+3)])]
            swing_lows = [h1_rates_sub[k]['low'] for k in range(2, len(h1_rates_sub)-2) 
                          if h1_rates_sub[k]['low'] == min([h1_rates_sub[j]['low'] for j in range(k-2, k+3)])]

            dollar_risk = balance * 0.01

            if is_4h_bull and is_1h_bull and cur_p < eq_4h:
                if (resistance_4h - cur_p) >= (0.5 * atr_val) and swing_highs:
                    if cur_p > swing_highs[-1]:
                        if model == "breakout":
                            entry_p = cur_p + spread
                            candidates = [l for l in swing_lows if l < entry_p]
                            sl_level = max(candidates) - atr_val * 0.3 if candidates else entry_p - min_stop
                            sl_dist = max(min_stop, entry_p - sl_level)
                            sl_level = entry_p - sl_dist
                            tp1 = entry_p + sl_dist * 1.5
                            tp2 = entry_p + sl_dist * 2.5
                            tp3 = entry_p + sl_dist * 3.5
                            lots = max(0.01, min(5.0, round(dollar_risk / (sl_dist * contract_size), 2)))
                            open_pos = {
                                "direction": "BUY", "entry_price": entry_p, "entry_time": m_time, "sl": sl_level,
                                "sl_dist": sl_dist, "tp1": tp1, "tp2": tp2, "tp3": tp3, "initial_lots": lots,
                                "remaining_lots": lots, "tp1_hit": False, "tp2_hit": False, "realized_pnl": 0.0, "risk_dollars": dollar_risk
                            }
                        elif model == "pullback_50":
                            limit_p = round((cur_p + ema20_1h) / 2.0, 4)
                            candidates = [l for l in swing_lows if l < limit_p]
                            sl_level = max(candidates) - atr_val * 0.3 if candidates else limit_p - min_stop
                            sl_dist = max(min_stop, limit_p - sl_level)
                            sl_level = limit_p - sl_dist
                            tp1 = limit_p + sl_dist * 1.5
                            tp2 = limit_p + sl_dist * 2.5
                            tp3 = limit_p + sl_dist * 3.5
                            lots = max(0.01, min(5.0, round(dollar_risk / (sl_dist * contract_size), 2)))
                            pending_limit = ("BUY", limit_p, sl_level, tp1, tp2, tp3, lots, m_time + 4 * 3600, dollar_risk)

            elif is_4h_bear and is_1h_bear and cur_p > eq_4h:
                if (cur_p - support_4h) >= (0.5 * atr_val) and swing_lows:
                    if cur_p < swing_lows[-1]:
                        if model == "breakout":
                            entry_p = cur_p - spread
                            candidates = [h for h in swing_highs if h > entry_p]
                            sl_level = min(candidates) + atr_val * 0.3 if candidates else entry_p + min_stop
                            sl_dist = max(min_stop, sl_level - entry_p)
                            sl_level = entry_p + sl_dist
                            tp1 = entry_p - sl_dist * 1.5
                            tp2 = entry_p - sl_dist * 2.5
                            tp3 = entry_p - sl_dist * 3.5
                            lots = max(0.01, min(5.0, round(dollar_risk / (sl_dist * contract_size), 2)))
                            open_pos = {
                                "direction": "SELL", "entry_price": entry_p, "entry_time": m_time, "sl": sl_level,
                                "sl_dist": sl_dist, "tp1": tp1, "tp2": tp2, "tp3": tp3, "initial_lots": lots,
                                "remaining_lots": lots, "tp1_hit": False, "tp2_hit": False, "realized_pnl": 0.0, "risk_dollars": dollar_risk
                            }
                        elif model == "pullback_50":
                            limit_p = round((cur_p + ema20_1h) / 2.0, 4)
                            candidates = [h for h in swing_highs if h > limit_p]
                            sl_level = min(candidates) + atr_val * 0.3 if candidates else limit_p + min_stop
                            sl_dist = max(min_stop, sl_level - limit_p)
                            sl_level = limit_p + sl_dist
                            tp1 = limit_p - sl_dist * 1.5
                            tp2 = limit_p - sl_dist * 2.5
                            tp3 = limit_p - sl_dist * 3.5
                            lots = max(0.01, min(5.0, round(dollar_risk / (sl_dist * contract_size), 2)))
                            pending_limit = ("SELL", limit_p, sl_level, tp1, tp2, tp3, lots, m_time + 4 * 3600, dollar_risk)

    tot_trades = len(trades)
    wins = [t for t in trades if t['pnl'] > 0]
    losses = [t for t in trades if t['pnl'] < 0]
    gp = sum([t['pnl'] for t in wins])
    gl = abs(sum([t['pnl'] for t in losses]))
    pnl = round(balance - 100000.0, 2)
    wr = round(len(wins)/tot_trades*100, 1) if tot_trades > 0 else 0.0
    pf = round(gp / gl, 2) if gl > 0 else (99.0 if gp > 0 else 0.0)
    avg_r = round(np.mean([t['r_mult'] for t in trades]), 2) if trades else 0.0

    return {"year": year, "trades": tot_trades, "wins": len(wins), "losses": len(losses), "pnl": pnl, "win_rate": wr, "pf": pf, "avg_r": avg_r}

def main():
    if not mt5.initialize():
        print("MT5 Failed")
        sys.exit(1)

    symbols = ["EURUSD", "GBPUSD", "XAUUSD"]
    start_dt = datetime(2020, 1, 1, tzinfo=timezone.utc)
    end_dt = datetime(2026, 8, 28, 23, 59, tzinfo=timezone.utc)

    print("="*95)
    print("   MULTI-YEAR M15-PRECISION BENCHMARK (2020 - 2026 ANNUAL MATRIX)")
    print("="*95)

    all_data = {}
    for sym in symbols:
        r_m15, r_h1, r_h4 = load_rates(sym, start_dt, end_dt)
        all_data[sym] = (r_m15, r_h1, r_h4)
        print(f"Loaded {sym}: {len(r_m15)} M15 bars, {len(r_h1)} H1 bars, {len(r_h4)} H4 bars.")

    matrix = {}

    for sym in symbols:
        r_m15, r_h1, r_h4 = all_data[sym]
        matrix[sym] = {"breakout": {}, "pullback": {}}
        print(f"\n==================== {sym} (2020 - 2026) ====================")
        print(f"{'Year':5s} | {'Model':10s} | {'Trds':4s} | {'Win%':6s} | {'Net P&L':11s} | {'PF':5s} | {'Avg R':6s}")
        print("-" * 65)

        for y in range(2020, 2027):
            res_bo = evaluate_year(sym, r_m15, r_h1, r_h4, y, model="breakout")
            res_pb = evaluate_year(sym, r_m15, r_h1, r_h4, y, model="pullback_50")
            matrix[sym]["breakout"][str(y)] = res_bo
            matrix[sym]["pullback"][str(y)] = res_pb

            print(f"{y:5d} | {'Breakout':10s} | {res_bo['trades']:4d} | {res_bo['win_rate']:5.1f}% | ${res_bo['pnl']:+10.2f} | {res_bo['pf']:5.2f} | {res_bo['avg_r']:+5.2f}R")
            print(f"{y:5d} | {'Pullback':10s} | {res_pb['trades']:4d} | {res_pb['win_rate']:5.1f}% | ${res_pb['pnl']:+10.2f} | {res_pb['pf']:5.2f} | {res_pb['avg_r']:+5.2f}R")
            print("-" * 65)

    out_file = r"d:\Techwaves-egy\Trading Team Skills\journal\m15_multi_year_benchmark_2020_2026.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(matrix, f, indent=2, default=str)
    print(f"\nSaved results to: {out_file}")
    mt5.shutdown()

if __name__ == "__main__":
    main()
