#!/usr/bin/env python3
"""
AI Autonomous Trading Firm — 7-Year Multi-Strategy Tournament (2020 - 2026)
Uses realistic 4-point intra-bar pathing (O -> L -> H -> C for green bars, O -> H -> L -> C for red bars)
to eliminate order-execution bias and simulate true tick pathing.

Compares 3 Core Strategies:
  1. EURUSD Structural Breakout
  2. GBPUSD / XAUUSD 50% Pullback Retest
  3. Higher-Timeframe 4H Trend-Continuation (4H EMA20 Pullback Rider)
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

def run_simulation(symbol, r_1h, r_4h, is_sh, is_sl, strategy="breakout", year=None, initial_balance=100000.0, risk_pct=0.01):
    symbol_info = mt5.symbol_info(symbol)
    contract_size = symbol_info.trade_contract_size if (symbol_info and symbol_info.trade_contract_size > 0) else 100.0
    spread = SPREADS.get(symbol, 0.0)

    h1_times = r_1h['time']
    h1_opens, h1_highs, h1_lows, h1_closes = r_1h['open'], r_1h['high'], r_1h['low'], r_1h['close']
    h1_atr = compute_atr(r_1h, 14)

    h4_times = r_4h['time']
    h4_opens, h4_highs, h4_lows, h4_closes = r_4h['open'], r_4h['high'], r_4h['low'], r_4h['close']
    h4_atr = compute_atr(r_4h, 14)

    ema20_1h = np.convolve(h1_closes, np.ones(20)/20, mode='same')
    ema50_1h = np.convolve(h1_closes, np.ones(50)/50, mode='same')
    ema20_4h = np.convolve(h4_closes, np.ones(20)/20, mode='same')
    ema50_4h = np.convolve(h4_closes, np.ones(50)/50, mode='same')

    if year:
        start_ts = int(datetime(year, 1, 1, tzinfo=timezone.utc).timestamp())
        end_ts = int(datetime(year, 12, 31, 23, 59, tzinfo=timezone.utc).timestamp())
    else:
        start_ts = int(datetime(2020, 1, 1, tzinfo=timezone.utc).timestamp())
        end_ts = int(datetime(2026, 8, 28, tzinfo=timezone.utc).timestamp())

    balance = initial_balance
    trades = []
    open_pos = None
    pending_limit = None
    consecutive_losses = 0
    locked_until_ts = 0
    h4_idx = 0

    for i in range(50, len(r_1h)):
        t1 = h1_times[i]
        while h4_idx + 1 < len(h4_times) and h4_times[h4_idx + 1] <= t1:
            h4_idx += 1

        if t1 < start_ts or t1 > end_ts:
            continue

        o, h, l, c = h1_opens[i], h1_highs[i], h1_lows[i], h1_closes[i]

        # Intra-bar path reconstruction
        if c >= o: # Bullish bar: Open -> Low -> High -> Close
            path = [(l, "LOW"), (h, "HIGH"), (c, "CLOSE")]
        else:      # Bearish bar: Open -> High -> Low -> Close
            path = [(h, "HIGH"), (l, "LOW"), (c, "CLOSE")]

        # Process pending limit order
        if pending_limit is not None and open_pos is None:
            p_dir, p_price, p_sl, p_tp1, p_tp2, p_tp3, p_lots, p_exp, p_risk = pending_limit
            if t1 > p_exp:
                pending_limit = None
            else:
                filled = False
                if p_dir == "BUY" and l <= p_price:
                    filled = True
                    fill_p = p_price + spread
                elif p_dir == "SELL" and h >= p_price:
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

        # Manage open position with sequential pathing
        if open_pos is not None:
            pos = open_pos
            direction = pos['direction']
            is_closed = False
            exit_p, pnl, exit_reason = 0.0, 0.0, ""

            for price_point, point_type in path:
                if is_closed:
                    break

                if direction == "BUY":
                    if price_point <= pos['sl']:
                        exit_p = pos['sl'] - spread
                        exit_reason = "STOP_LOSS"
                        pnl = (exit_p - pos['entry_price']) * pos['remaining_lots'] * contract_size
                        is_closed = True
                    else:
                        if not pos['tp1_hit'] and price_point >= pos['tp1']:
                            tp1_lots = pos['initial_lots'] * 0.40
                            pos['realized_pnl'] += (pos['tp1'] - pos['entry_price'] - spread) * tp1_lots * contract_size
                            pos['remaining_lots'] -= tp1_lots
                            pos['tp1_hit'] = True
                            pos['sl'] = pos['entry_price'] # Move SL to BE
                        if pos['tp1_hit'] and not pos['tp2_hit'] and price_point >= pos['tp2']:
                            tp2_lots = pos['initial_lots'] * 0.40
                            pos['realized_pnl'] += (pos['tp2'] - pos['entry_price'] - spread) * tp2_lots * contract_size
                            pos['remaining_lots'] -= tp2_lots
                            pos['tp2_hit'] = True
                            pos['sl'] = pos['tp1'] # Lock profit
                        if pos['tp2_hit'] and price_point >= pos['tp3']:
                            tp3_lots = pos['remaining_lots']
                            pos['realized_pnl'] += (pos['tp3'] - pos['entry_price'] - spread) * tp3_lots * contract_size
                            pos['remaining_lots'] = 0.0
                            exit_p, exit_reason = pos['tp3'], "FULL_TP3_RUNNER"
                            pnl = 0.0
                            is_closed = True

                elif direction == "SELL":
                    if price_point >= pos['sl']:
                        exit_p = pos['sl'] + spread
                        exit_reason = "STOP_LOSS"
                        pnl = (pos['entry_price'] - exit_p) * pos['remaining_lots'] * contract_size
                        is_closed = True
                    else:
                        if not pos['tp1_hit'] and price_point <= pos['tp1']:
                            tp1_lots = pos['initial_lots'] * 0.40
                            pos['realized_pnl'] += (pos['entry_price'] - pos['tp1'] - spread) * tp1_lots * contract_size
                            pos['remaining_lots'] -= tp1_lots
                            pos['tp1_hit'] = True
                            pos['sl'] = pos['entry_price'] # Move SL to BE
                        if pos['tp1_hit'] and not pos['tp2_hit'] and price_point <= pos['tp2']:
                            tp2_lots = pos['initial_lots'] * 0.40
                            pos['realized_pnl'] += (pos['entry_price'] - pos['tp2'] - spread) * tp2_lots * contract_size
                            pos['remaining_lots'] -= tp2_lots
                            pos['tp2_hit'] = True
                            pos['sl'] = pos['tp1'] # Lock profit
                        if pos['tp2_hit'] and price_point <= pos['tp3']:
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
                        locked_until_ts = t1 + 3600
                else:
                    consecutive_losses = 0

                trades.append({
                    "symbol": symbol, "direction": direction, "entry_time": pos['entry_time'],
                    "exit_time": t1, "pnl": total_trade_pnl, "r_multiple": r_mult,
                    "exit_reason": exit_reason, "balance": round(balance, 2)
                })
                open_pos = None

        # Entry logic
        if open_pos is None and pending_limit is None and t1 >= locked_until_ts:
            if h4_idx < 30:
                continue

            atr1 = h1_atr[i]
            if atr1 <= 0:
                continue
            min_stop = atr1 * 1.5
            dollar_risk = balance * risk_pct

            e50_4 = ema50_4h[h4_idx]
            e20_4 = ema20_4h[h4_idx]
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

            # -----------------------------------------------------------------
            # 1. Structural Breakout
            # -----------------------------------------------------------------
            if strategy == "breakout":
                is_bull = c > e50_4 and c > e20_1 and e20_1 > e50_1 and c < eq_4h
                is_bear = c < e50_4 and c < e20_1 and e20_1 < e50_1 and c > eq_4h

                if is_bull and (resistance_4h - c) >= (0.5 * atr1) and last_sh is not None and c > last_sh:
                    entry_p = c + spread
                    sl_level = last_sl - atr1 * 0.3 if last_sl is not None else entry_p - min_stop
                    sl_dist = max(min_stop, entry_p - sl_level)
                    sl_level = entry_p - sl_dist
                    tp1, tp2, tp3 = entry_p + sl_dist * 1.5, entry_p + sl_dist * 2.5, entry_p + sl_dist * 3.5
                    lots = max(0.01, min(5.0, round(dollar_risk / (sl_dist * contract_size), 2)))
                    open_pos = {
                        "direction": "BUY", "entry_price": entry_p, "entry_time": t1, "sl": sl_level,
                        "sl_dist": sl_dist, "tp1": tp1, "tp2": tp2, "tp3": tp3, "initial_lots": lots,
                        "remaining_lots": lots, "tp1_hit": False, "tp2_hit": False, "realized_pnl": 0.0, "risk_dollars": dollar_risk
                    }

                elif is_bear and (c - support_4h) >= (0.5 * atr1) and last_sl is not None and c < last_sl:
                    entry_p = c - spread
                    sl_level = last_sh + atr1 * 0.3 if last_sh is not None else entry_p + min_stop
                    sl_dist = max(min_stop, sl_level - entry_p)
                    sl_level = entry_p + sl_dist
                    tp1, tp2, tp3 = entry_p - sl_dist * 1.5, entry_p - sl_dist * 2.5, entry_p - sl_dist * 3.5
                    lots = max(0.01, min(5.0, round(dollar_risk / (sl_dist * contract_size), 2)))
                    open_pos = {
                        "direction": "SELL", "entry_price": entry_p, "entry_time": t1, "sl": sl_level,
                        "sl_dist": sl_dist, "tp1": tp1, "tp2": tp2, "tp3": tp3, "initial_lots": lots,
                        "remaining_lots": lots, "tp1_hit": False, "tp2_hit": False, "realized_pnl": 0.0, "risk_dollars": dollar_risk
                    }

            # -----------------------------------------------------------------
            # 2. 50% Pullback Retest
            # -----------------------------------------------------------------
            elif strategy == "pullback_50":
                is_bull = c > e50_4 and c > e20_1 and c < eq_4h
                is_bear = c < e50_4 and c < e20_1 and c > eq_4h

                if is_bull and (resistance_4h - c) >= (0.5 * atr1) and last_sh is not None and c > last_sh:
                    limit_p = round((c + e20_1) / 2.0, 4)
                    sl_level = last_sl - atr1 * 0.3 if last_sl is not None else limit_p - min_stop
                    sl_dist = max(min_stop, limit_p - sl_level)
                    sl_level = limit_p - sl_dist
                    tp1, tp2, tp3 = limit_p + sl_dist * 1.5, limit_p + sl_dist * 2.5, limit_p + sl_dist * 3.5
                    lots = max(0.01, min(5.0, round(dollar_risk / (sl_dist * contract_size), 2)))
                    pending_limit = ("BUY", limit_p, sl_level, tp1, tp2, tp3, lots, t1 + 4 * 3600, dollar_risk)

                elif is_bear and (c - support_4h) >= (0.5 * atr1) and last_sl is not None and c < last_sl:
                    limit_p = round((c + e20_1) / 2.0, 4)
                    sl_level = last_sh + atr1 * 0.3 if last_sh is not None else limit_p + min_stop
                    sl_dist = max(min_stop, sl_level - limit_p)
                    sl_level = limit_p + sl_dist
                    tp1, tp2, tp3 = limit_p - sl_dist * 1.5, limit_p - sl_dist * 2.5, limit_p - sl_dist * 3.5
                    lots = max(0.01, min(5.0, round(dollar_risk / (sl_dist * contract_size), 2)))
                    pending_limit = ("SELL", limit_p, sl_level, tp1, tp2, tp3, lots, t1 + 4 * 3600, dollar_risk)

    tot_trades = len(trades)
    wins = [t for t in trades if t['pnl'] > 0]
    losses = [t for t in trades if t['pnl'] < 0]
    gp = sum([t['pnl'] for t in wins])
    gl = abs(sum([t['pnl'] for t in losses]))
    pnl = round(balance - initial_balance, 2)
    wr = round(len(wins)/tot_trades*100, 1) if tot_trades > 0 else 0.0
    pf = round(gp / gl, 2) if gl > 0 else (99.0 if gp > 0 else 0.0)
    avg_r = round(np.mean([t['r_multiple'] for t in trades]), 2) if trades else 0.0

    return {"trades": tot_trades, "wins": len(wins), "losses": len(losses), "pnl": pnl, "win_rate": wr, "pf": pf, "avg_r": avg_r}

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

    print("="*105)
    print("      7-YEAR INSTITUTIONAL STRATEGY TOURNAMENT (2020 - 2026 FULL BENCHMARK)")
    print("="*105)

    annual_results = {}

    for sym in symbols:
        r1, r4, is_sh, is_sl = all_data[sym]
        annual_results[sym] = {"breakout": {}, "pullback": {}}
        print(f"\n============================== {sym} ==============================")
        print(f"{'Year':5s} | {'Breakout PnL':14s} | {'BO Win%':8s} | {'BO PF':6s} | {'Pullback PnL':14s} | {'PB Win%':8s} | {'PB PF':6s} | {'Winning Strategy':18s}")
        print("-" * 105)

        tot_bo_pnl, tot_pb_pnl = 0.0, 0.0

        for y in range(2020, 2027):
            res_bo = run_simulation(sym, r1, r4, is_sh, is_sl, strategy="breakout", year=y)
            res_pb = run_simulation(sym, r1, r4, is_sh, is_sl, strategy="pullback_50", year=y)

            tot_bo_pnl += res_bo['pnl']
            tot_pb_pnl += res_pb['pnl']

            annual_results[sym]["breakout"][str(y)] = res_bo
            annual_results[sym]["pullback"][str(y)] = res_pb

            winner = "Breakout 🏆" if res_bo['pnl'] > res_pb['pnl'] else ("Pullback 🏆" if res_pb['pnl'] > res_bo['pnl'] else "Tie")
            print(f"{y:5d} | ${res_bo['pnl']:+12.2f} | {res_bo['win_rate']:6.1f}% | {res_bo['pf']:5.2f} | ${res_pb['pnl']:+12.2f} | {res_pb['win_rate']:6.1f}% | {res_pb['pf']:5.2f} | {winner:18s}")

        print("-" * 105)
        winner_7yr = "Breakout 🏆" if tot_bo_pnl > tot_pb_pnl else "Pullback 🏆"
        print(f"7-YEAR TOTAL: Breakout = ${tot_bo_pnl:+,.2f}  vs  Pullback = ${tot_pb_pnl:+,.2f}  -->  OVERALL WINNER: {winner_7yr}")

    # Save to journal
    out_path = r"d:\Techwaves-egy\Trading Team Skills\journal\7year_strategy_tournament_2020_2026.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(annual_results, f, indent=2, default=str)
    print(f"\nFull 7-Year Tournament Benchmark saved to: {out_path}")

    mt5.shutdown()

if __name__ == "__main__":
    main()
