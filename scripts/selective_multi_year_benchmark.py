#!/usr/bin/env python3
"""
AI Autonomous Trading Firm — Selective Multi-Year Benchmark (2020 - 2026)
Tests selective institutional models with:
- London / NY Session Timing Filter (07:00 - 17:00 UTC)
- 4H Macro Trend Confluence
- True 1H Fractal Swing Breakout vs 50% Pullback Retest
- Year-by-Year breakdown across all 7 years (2020, 2021, 2022, 2023, 2024, 2025, 2026)
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

def precompute_swings(rates):
    highs, lows = rates['high'], rates['low']
    n = len(rates)
    is_sh = np.zeros(n, dtype=bool)
    is_sl = np.zeros(n, dtype=bool)
    for i in range(2, n - 2):
        if highs[i] > highs[i-1] and highs[i] > highs[i-2] and highs[i] > highs[i+1] and highs[i] > highs[i+2]:
            is_sh[i] = True
        if lows[i] < lows[i-1] and lows[i] < lows[i-2] and lows[i] < lows[i+1] and lows[i] < lows[i+2]:
            is_sl[i] = True
    return is_sh, is_sl

def run_selective_backtest(symbol, r_1h, r_4h, is_sh, is_sl, model_type="breakout", initial_balance=100000.0, risk_pct=0.01):
    symbol_info = mt5.symbol_info(symbol)
    contract_size = symbol_info.trade_contract_size if (symbol_info and symbol_info.trade_contract_size > 0) else 100.0
    spread = SPREADS.get(symbol, 0.0)

    h1_times = r_1h['time']
    h1_highs, h1_lows, h1_closes = r_1h['high'], r_1h['low'], r_1h['close']
    h1_atr = compute_atr(r_1h, 14)

    h4_times = r_4h['time']
    h4_highs, h4_lows, h4_closes = r_4h['high'], r_4h['low'], r_4h['close']

    ema20_1h = np.convolve(h1_closes, np.ones(20)/20, mode='same')
    ema50_1h = np.convolve(h1_closes, np.ones(50)/50, mode='same')
    ema50_4h = np.convolve(h4_closes, np.ones(50)/50, mode='same')

    balance = initial_balance
    trades = []
    open_pos = None
    pending_limit = None
    consecutive_losses = 0
    max_consecutive_losses = 0
    locked_until_ts = 0

    start_ts = int(datetime(2020, 1, 1, tzinfo=timezone.utc).timestamp())
    end_ts = int(datetime(2026, 8, 28, tzinfo=timezone.utc).timestamp())
    h4_idx = 0

    for i in range(50, len(r_1h)):
        t1 = h1_times[i]
        
        while h4_idx + 1 < len(h4_times) and h4_times[h4_idx + 1] <= t1:
            h4_idx += 1

        if t1 < start_ts or t1 > end_ts:
            continue

        dt_utc = datetime.fromtimestamp(t1, tz=timezone.utc)
        hour = dt_utc.hour

        # Check pending limit
        if pending_limit is not None and open_pos is None:
            p_dir, p_price, p_sl, p_tp1, p_tp2, p_tp3, p_lots, p_exp, p_risk = pending_limit
            if t1 > p_exp:
                pending_limit = None
            else:
                filled = False
                if p_dir == "BUY" and h1_lows[i] <= p_price:
                    filled = True
                    fill_p = p_price + spread
                elif p_dir == "SELL" and h1_highs[i] >= p_price:
                    filled = True
                    fill_p = p_price - spread

                if filled:
                    open_pos = {
                        "direction": p_dir, "entry_price": fill_p, "entry_time": t1,
                        "sl": p_sl, "sl_dist": abs(fill_p - p_sl), "tp1": p_tp1, "tp2": p_tp2, "tp3": p_tp3,
                        "initial_lots": p_lots, "remaining_lots": p_lots, "tp1_hit": False, "tp2_hit": False,
                        "realized_pnl": 0.0, "risk_dollars": p_risk
                    }
                    pending_limit = None

        # Manage open position
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
                        pos['sl'] = pos['entry_price']
                    if pos['tp1_hit'] and not pos['tp2_hit'] and hi >= pos['tp2']:
                        tp2_lots = pos['initial_lots'] * 0.40
                        pos['realized_pnl'] += (pos['tp2'] - pos['entry_price'] - spread) * tp2_lots * contract_size
                        pos['remaining_lots'] -= tp2_lots
                        pos['tp2_hit'] = True
                        pos['sl'] = pos['tp1']
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

            if is_closed:
                total_trade_pnl = round(pos['realized_pnl'] + pnl, 2)
                r_mult = round(total_trade_pnl / pos['risk_dollars'], 2) if pos['risk_dollars'] > 0 else 0.0
                balance += total_trade_pnl
                
                if total_trade_pnl < 0:
                    consecutive_losses += 1
                    max_consecutive_losses = max(max_consecutive_losses, consecutive_losses)
                    if consecutive_losses >= 2:
                        locked_until_ts = t1 + 3600
                else:
                    consecutive_losses = 0

                trades.append({
                    "symbol": symbol, "direction": direction, "entry_time": pos['entry_time'],
                    "exit_time": t1, "year": dt_utc.year, "pnl": total_trade_pnl, "r_multiple": r_mult,
                    "exit_reason": exit_reason, "balance": round(balance, 2)
                })
                open_pos = None

        # Entry logic with London/NY session filter (07:00 to 17:00 UTC)
        if open_pos is None and pending_limit is None and t1 >= locked_until_ts:
            if h4_idx < 30 or hour < 7 or hour > 17:
                continue

            cur_p = h1_closes[i]
            atr1 = h1_atr[i]
            if atr1 <= 0:
                continue
            min_stop = atr1 * 1.5
            dollar_risk = balance * risk_pct

            e50_4 = ema50_4h[h4_idx]
            h4_window_hi = h4_highs[max(0, h4_idx-30):h4_idx+1]
            h4_window_lo = h4_lows[max(0, h4_idx-30):h4_idx+1]
            range_high_4h = np.max(h4_window_hi)
            range_low_4h = np.min(h4_window_lo)
            eq_4h = (range_high_4h + range_low_4h) / 2.0
            support_4h = np.min(h4_lows[max(0, h4_idx-20):h4_idx+1])
            resistance_4h = np.max(h4_highs[max(0, h4_idx-20):h4_idx+1])

            e20_1 = ema20_1h[i]
            e50_1 = ema50_1h[i]

            sh_indices = np.where(is_sh[max(0, i-30):i-1])[0]
            sl_indices = np.where(is_sl[max(0, i-30):i-1])[0]
            last_sh = h1_highs[max(0, i-30) + sh_indices[-1]] if len(sh_indices) > 0 else None
            last_sl = h1_lows[max(0, i-30) + sl_indices[-1]] if len(sl_indices) > 0 else None

            is_bull = cur_p > e50_4 and cur_p > e20_1 and e20_1 > e50_1 and cur_p < eq_4h
            is_bear = cur_p < e50_4 and cur_p < e20_1 and e20_1 < e50_1 and cur_p > eq_4h

            if is_bull and (resistance_4h - cur_p) >= (0.5 * atr1) and last_sh is not None:
                if cur_p > last_sh:
                    if model_type == "breakout":
                        entry_p = cur_p + spread
                        sl_level = last_sl - atr1 * 0.3 if last_sl is not None else entry_p - min_stop
                        sl_dist = max(min_stop, entry_p - sl_level)
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
                    elif model_type == "pullback_50":
                        limit_p = round((cur_p + e20_1) / 2.0, 4)
                        sl_level = last_sl - atr1 * 0.3 if last_sl is not None else limit_p - min_stop
                        sl_dist = max(min_stop, limit_p - sl_level)
                        sl_level = limit_p - sl_dist
                        tp1 = limit_p + sl_dist * 1.5
                        tp2 = limit_p + sl_dist * 2.5
                        tp3 = limit_p + sl_dist * 3.5
                        lots = max(0.01, min(5.0, round(dollar_risk / (sl_dist * contract_size), 2)))
                        pending_limit = ("BUY", limit_p, sl_level, tp1, tp2, tp3, lots, t1 + 4 * 3600, dollar_risk)

            elif is_bear and (cur_p - support_4h) >= (0.5 * atr1) and last_sl is not None:
                if cur_p < last_sl:
                    if model_type == "breakout":
                        entry_p = cur_p - spread
                        sl_level = last_sh + atr1 * 0.3 if last_sh is not None else entry_p + min_stop
                        sl_dist = max(min_stop, sl_level - entry_p)
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
                    elif model_type == "pullback_50":
                        limit_p = round((cur_p + e20_1) / 2.0, 4)
                        sl_level = last_sh + atr1 * 0.3 if last_sh is not None else limit_p + min_stop
                        sl_dist = max(min_stop, sl_level - limit_p)
                        sl_level = limit_p + sl_dist
                        tp1 = limit_p - sl_dist * 1.5
                        tp2 = limit_p - sl_dist * 2.5
                        tp3 = limit_p - sl_dist * 3.5
                        lots = max(0.01, min(5.0, round(dollar_risk / (sl_dist * contract_size), 2)))
                        pending_limit = ("SELL", limit_p, sl_level, tp1, tp2, tp3, lots, t1 + 4 * 3600, dollar_risk)

    tot_trades = len(trades)
    wins = [t for t in trades if t['pnl'] > 0]
    losses = [t for t in trades if t['pnl'] < 0]
    gross_p = sum([t['pnl'] for t in wins])
    gross_l = abs(sum([t['pnl'] for t in losses]))
    net_pnl = round(balance - initial_balance, 2)
    win_rate = round(len(wins) / tot_trades * 100, 2) if tot_trades > 0 else 0.0
    pf = round(gross_p / gross_l, 2) if gross_l > 0 else 0.0
    r_multiples = [t['r_multiple'] for t in trades]
    avg_r = round(np.mean(r_multiples), 2) if r_multiples else 0.0

    yearly = {}
    for y in range(2020, 2027):
        y_t = [t for t in trades if t['year'] == y]
        y_w = [t for t in y_t if t['pnl'] > 0]
        y_pnl = sum([t['pnl'] for t in y_t])
        y_wr = round(len(y_w)/len(y_t)*100, 1) if y_t else 0.0
        yearly[str(y)] = {"trades": len(y_t), "pnl": round(y_pnl, 2), "win_rate": y_wr}

    return {
        "symbol": symbol, "model": model_type, "trades": tot_trades, "wins": len(wins),
        "losses": len(losses), "win_rate": win_rate, "net_pnl": net_pnl, "gross_profit": round(gross_p, 2),
        "gross_loss": round(gross_l, 2), "pf": pf, "avg_r": avg_r, "yearly": yearly
    }

def main():
    if not mt5.initialize():
        print("MT5 Failed")
        sys.exit(1)

    start_dt = datetime(2020, 1, 1, tzinfo=timezone.utc)
    end_dt = datetime(2026, 8, 28, 23, 59, tzinfo=timezone.utc)

    symbols = ["EURUSD", "GBPUSD", "XAUUSD", "USDJPY"]
    all_data = {}
    for sym in symbols:
        r1, r4 = load_data(sym, start_dt, end_dt)
        is_sh, is_sl = precompute_swings(r1)
        all_data[sym] = (r1, r4, is_sh, is_sl)

    print("="*95)
    print("      SELECTIVE INSTITUTIONAL BENCHMARK (2020 - 2026 FULL 7-YEAR EVALUATION)")
    print("="*95)

    comparison_results = {}

    for sym in symbols:
        r1, r4, is_sh, is_sl = all_data[sym]
        res_bo = run_selective_backtest(sym, r1, r4, is_sh, is_sl, model_type="breakout")
        res_pb = run_selective_backtest(sym, r1, r4, is_sh, is_sl, model_type="pullback_50")
        comparison_results[sym] = {"breakout": res_bo, "pullback": res_pb}

        print(f"\n--- {sym} (2020 - 2026 TOTALS) ---")
        print(f"  [Breakout]: {res_bo['trades']:3d} Trades | Win: {res_bo['win_rate']:5.1f}% | Net PnL: ${res_bo['net_pnl']:+9.2f} | PF: {res_bo['pf']:4.2f} | Avg R: {res_bo['avg_r']:+4.2f}R")
        print(f"  [Pullback]: {res_pb['trades']:3d} Trades | Win: {res_pb['win_rate']:5.1f}% | Net PnL: ${res_pb['net_pnl']:+9.2f} | PF: {res_pb['pf']:4.2f} | Avg R: {res_pb['avg_r']:+4.2f}R")
        
        print(f"  Year-by-Year (Breakout vs Pullback):")
        for y in range(2020, 2027):
            y_s = str(y)
            bo_y = res_bo['yearly'].get(y_s, {'trades':0, 'pnl':0.0})
            pb_y = res_pb['yearly'].get(y_s, {'trades':0, 'pnl':0.0})
            print(f"    {y}: BO {bo_y['trades']:2d}T (${bo_y['pnl']:+8.2f})  vs  PB {pb_y['trades']:2d}T (${pb_y['pnl']:+8.2f})")

    out_path = r"d:\Techwaves-egy\Trading Team Skills\journal\selective_multi_year_benchmark_2020_2026.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(comparison_results, f, indent=2, default=str)
    print(f"\nReport saved to: {out_path}")
    mt5.shutdown()

if __name__ == "__main__":
    main()
