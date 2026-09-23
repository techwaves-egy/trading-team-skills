#!/usr/bin/env python3
"""
AI Autonomous Trading Firm — Direct Engine Ablation & Stress-Testing Suite (v3.3.1)
Directly tests the EXACT v3.3.0 engine from multi_strategy_backtest_2020_2026.py under:
  1. GBPUSD Session Filter Ablation: All Hours vs 07:00-16:00 UTC
  2. Gate 3 (S/R Trap Filter) Ablation: With Gate 3 vs Without Gate 3 on EURUSD
  3. XAUUSD (Gold) Stress Tests:
     - Baseline ($0.35 spread)
     - +25% Spread ($0.44), +50% Spread ($0.52)
     - Slippage (+2 ticks, +5 ticks)
     - Jackknife Outlier Removal (Drop Top 5, Drop Top 10 Wins)
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

def run_parameterized_engine(symbol, r_1h, r_4h, is_sh_1h, is_sl_1h, strategy_type, start_dt, end_dt,
                             spread_val=None, extra_slippage=0.0, use_gate3=True, session_filter=False,
                             rejected_only=False, drop_top_n=0):
    symbol_info = mt5.symbol_info(symbol)
    contract_size = symbol_info.trade_contract_size if (symbol_info and symbol_info.trade_contract_size > 0) else 100.0
    
    spreads = {"XAUUSD": 0.35, "EURUSD": 0.00015, "GBPUSD": 0.00020, "USDJPY": 0.025}
    base_spread = spreads.get(symbol, 0.0) if spread_val is None else spread_val
    spread = base_spread + extra_slippage

    h1_times = r_1h['time']
    h1_highs = r_1h['high']
    h1_lows = r_1h['low']
    h1_closes = r_1h['close']
    h1_opens = r_1h['open']
    h1_atr = compute_atr(r_1h, 14)

    h4_times = r_4h['time']
    h4_highs = r_4h['high']
    h4_lows = r_4h['low']
    h4_closes = r_4h['close']
    h4_opens = r_4h['open']
    h4_atr = compute_atr(r_4h, 14)

    ema20_1h = np.convolve(h1_closes, np.ones(20)/20, mode='same')
    ema50_1h = np.convolve(h1_closes, np.ones(50)/50, mode='same')
    ema20_4h = np.convolve(h4_closes, np.ones(20)/20, mode='same')
    ema50_4h = np.convolve(h4_closes, np.ones(50)/50, mode='same')

    balance = 100000.0
    trades = []
    open_pos = None
    pending_limit = None
    consecutive_losses = 0
    max_consecutive_losses = 0
    locked_until_ts = 0

    start_ts = int(start_dt.timestamp())
    end_ts = int(end_dt.timestamp())
    h4_idx = 0

    for i in range(50, len(r_1h)):
        t1 = h1_times[i]
        while h4_idx + 1 < len(h4_times) and h4_times[h4_idx + 1] <= t1:
            h4_idx += 1

        if t1 < start_ts or t1 > end_ts:
            continue

        dt_utc = datetime.fromtimestamp(t1, tz=timezone.utc)
        hour = dt_utc.hour

        # Pending limit orders
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

        # Position management
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
                    "pnl": total_trade_pnl, "r_mult": r_mult, "year": dt_utc.year
                })
                open_pos = None

        # Entry logic
        if open_pos is None and pending_limit is None and t1 >= locked_until_ts:
            if h4_idx < 30:
                continue

            if session_filter and (hour < 7 or hour > 16):
                continue

            cur_p = h1_closes[i]
            atr1 = h1_atr[i]
            if atr1 <= 0:
                continue
            min_stop = atr1 * 1.5
            dollar_risk = balance * 0.01

            e20_4 = ema20_4h[h4_idx]
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

            sh_indices = np.where(is_sh_1h[max(0, i-30):i-1])[0]
            sl_indices = np.where(is_sl_1h[max(0, i-30):i-1])[0]
            last_sh = h1_highs[max(0, i-30) + sh_indices[-1]] if len(sh_indices) > 0 else None
            last_sl = h1_lows[max(0, i-30) + sl_indices[-1]] if len(sl_indices) > 0 else None

            # Strategy A: Breakout
            if strategy_type == "Strategy_A_Breakout":
                is_bull = cur_p > e50_4 and cur_p > e20_1 and e20_1 > e50_1 and cur_p < eq_4h
                is_bear = cur_p < e50_4 and cur_p < e20_1 and e20_1 < e50_1 and cur_p > eq_4h

                near_res = (resistance_4h - cur_p) < (0.5 * atr1)
                near_sup = (cur_p - support_4h) < (0.5 * atr1)

                should_buy = False
                should_sell = False

                if is_bull and last_sh is not None and cur_p > last_sh:
                    if use_gate3 and not near_res:
                        should_buy = True
                    elif not use_gate3:
                        should_buy = True
                    elif rejected_only and near_res:
                        should_buy = True

                elif is_bear and last_sl is not None and cur_p < last_sl:
                    if use_gate3 and not near_sup:
                        should_sell = True
                    elif not use_gate3:
                        should_sell = True
                    elif rejected_only and near_sup:
                        should_sell = True

                if should_buy:
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

                elif should_sell:
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

            # Strategy C: 4H Trend Rider
            elif strategy_type == "Strategy_C_4H_Trend_Rider":
                atr4 = h4_atr[h4_idx] if h4_idx < len(h4_atr) else atr1 * 2.0
                is_4h_uptrend = e20_4 > e50_4 and h4_closes[h4_idx] > e50_4
                is_4h_downtrend = e20_4 < e50_4 and h4_closes[h4_idx] < e50_4

                if is_4h_uptrend and abs(h1_lows[i] - e20_4) < (0.3 * atr4) and h1_closes[i] > h1_opens[i]:
                    entry_p = cur_p + spread
                    sl_dist = max(atr4 * 1.0, entry_p - (e20_4 - 0.5 * atr4))
                    sl_level = entry_p - sl_dist
                    tp1 = entry_p + sl_dist * 1.5
                    tp2 = entry_p + sl_dist * 3.0
                    tp3 = entry_p + sl_dist * 5.0
                    lots = max(0.01, min(5.0, round(dollar_risk / (sl_dist * contract_size), 2)))
                    open_pos = {
                        "direction": "BUY", "entry_price": entry_p, "entry_time": t1, "sl": sl_level,
                        "sl_dist": sl_dist, "tp1": tp1, "tp2": tp2, "tp3": tp3, "initial_lots": lots,
                        "remaining_lots": lots, "tp1_hit": False, "tp2_hit": False, "realized_pnl": 0.0, "risk_dollars": dollar_risk
                    }

                elif is_4h_downtrend and abs(h1_highs[i] - e20_4) < (0.3 * atr4) and h1_closes[i] < h1_opens[i]:
                    entry_p = cur_p - spread
                    sl_dist = max(atr4 * 1.0, (e20_4 + 0.5 * atr4) - entry_p)
                    sl_level = entry_p + sl_dist
                    tp1 = entry_p - sl_dist * 1.5
                    tp2 = entry_p - sl_dist * 3.0
                    tp3 = entry_p - sl_dist * 5.0
                    lots = max(0.01, min(5.0, round(dollar_risk / (sl_dist * contract_size), 2)))
                    open_pos = {
                        "direction": "SELL", "entry_price": entry_p, "entry_time": t1, "sl": sl_level,
                        "sl_dist": sl_dist, "tp1": tp1, "tp2": tp2, "tp3": tp3, "initial_lots": lots,
                        "remaining_lots": lots, "tp1_hit": False, "tp2_hit": False, "realized_pnl": 0.0, "risk_dollars": dollar_risk
                    }

    trade_pnls = [t['pnl'] for t in trades]
    if drop_top_n > 0 and len(trade_pnls) > drop_top_n:
        trade_pnls = sorted(trade_pnls)[:-drop_top_n]

    tot_trades = len(trade_pnls)
    wins = [p for p in trade_pnls if p > 0]
    losses = [p for p in trade_pnls if p < 0]
    gp = sum(wins)
    gl = abs(sum(losses))
    net_pnl = round(sum(trade_pnls), 2)
    win_rate = round(len(wins)/tot_trades*100, 2) if tot_trades > 0 else 0.0
    pf = round(gp / gl, 2) if gl > 0 else 0.0
    expectancy = round(net_pnl / tot_trades, 2) if tot_trades > 0 else 0.0

    # Max Drawdown
    running = 100000.0
    eq = [running]
    for p in trade_pnls:
        running += p
        eq.append(running)
    pk = eq[0]
    mdd = 0.0
    for e in eq:
        if e > pk: pk = e
        dd = (pk - e) / pk * 100
        if dd > mdd: mdd = dd

    return {
        "trades": tot_trades, "wins": len(wins), "losses": len(losses), "win_rate": win_rate,
        "net_pnl": net_pnl, "gross_profit": round(gp, 2), "gross_loss": round(gl, 2),
        "pf": pf, "expectancy": expectancy, "max_dd_pct": round(mdd, 2),
        "max_consecutive_losses": max_consecutive_losses
    }

def main():
    if not mt5.initialize():
        print("MT5 Failed")
        sys.exit(1)

    start_dt = datetime(2020, 1, 1, tzinfo=timezone.utc)
    end_dt = datetime(2026, 8, 28, 23, 59, tzinfo=timezone.utc)

    print("="*105)
    print("      INSTITUTIONAL VALIDATION & STRESS-TESTING SUITE (2020 - 2026 YTD)")
    print("="*105)

    # -------------------------------------------------------------------------
    # 1. GBPUSD SESSION ABLATION (ALL HOURS VS 07-16 UTC)
    # -------------------------------------------------------------------------
    r1_gbp, r4_gbp = load_data("GBPUSD", start_dt, end_dt)
    sh_gbp, sl_gbp = precompute_swings(r1_gbp)

    res_gbp_all = run_parameterized_engine("GBPUSD", r1_gbp, r4_gbp, sh_gbp, sl_gbp, "Strategy_A_Breakout", start_dt, end_dt, session_filter=False)
    res_gbp_sess = run_parameterized_engine("GBPUSD", r1_gbp, r4_gbp, sh_gbp, sl_gbp, "Strategy_A_Breakout", start_dt, end_dt, session_filter=True)

    print("\n1. GBPUSD SESSION FILTER ABLATION (2020 - 2026 YTD):")
    print(f"{'Metric':20s} | {'All Hours':15s} | {'07:00 - 16:00 UTC':20s} | {'Verdict / Impact'}")
    print("-" * 85)
    print(f"{'Trades':20s} | {res_gbp_all['trades']:15d} | {res_gbp_sess['trades']:20d} | Reduced trade count by {res_gbp_all['trades'] - res_gbp_sess['trades']}")
    print(f"{'Win Rate':20s} | {res_gbp_all['win_rate']:14.1f}% | {res_gbp_sess['win_rate']:19.1f}% | {'Shift: ' + str(round(res_gbp_sess['win_rate'] - res_gbp_all['win_rate'], 1)) + '%'}")
    print(f"{'Profit Factor':20s} | {res_gbp_all['pf']:15.2f} | {res_gbp_sess['pf']:20.2f} | {'Remains < 1.0 (Negative Expectancy)' if res_gbp_sess['pf'] < 1.0 else 'Positive'}")
    print(f"{'Expectancy / Trade':20s} | ${res_gbp_all['expectancy']:+14.2f} | ${res_gbp_sess['expectancy']:+19.2f} | {'No edge found' if res_gbp_sess['expectancy'] < 0 else 'Edge exists'}")
    print(f"{'Net P&L':20s} | ${res_gbp_all['net_pnl']:+14.2f} | ${res_gbp_sess['net_pnl']:+19.2f} | {'Capital Bleed Reduced' if res_gbp_sess['net_pnl'] > res_gbp_all['net_pnl'] else 'Worse'}")
    print(f"{'Max Drawdown':20s} | {res_gbp_all['max_dd_pct']:14.2f}% | {res_gbp_sess['max_dd_pct']:19.2f}% | {'Lower Drawdown' if res_gbp_sess['max_dd_pct'] < res_gbp_all['max_dd_pct'] else 'Higher'}")

    # -------------------------------------------------------------------------
    # 2. GATE 3 (S/R TRAP FILTER) ABLATION & COUNTERFACTUAL
    # -------------------------------------------------------------------------
    r1_eur, r4_eur = load_data("EURUSD", start_dt, end_dt)
    sh_eur, sl_eur = precompute_swings(r1_eur)

    res_eur_with_gate3 = run_parameterized_engine("EURUSD", r1_eur, r4_eur, sh_eur, sl_eur, "Strategy_A_Breakout", start_dt, end_dt, use_gate3=True)
    res_eur_no_gate3 = run_parameterized_engine("EURUSD", r1_eur, r4_eur, sh_eur, sl_eur, "Strategy_A_Breakout", start_dt, end_dt, use_gate3=False)
    res_eur_rejected_only = run_parameterized_engine("EURUSD", r1_eur, r4_eur, sh_eur, sl_eur, "Strategy_A_Breakout", start_dt, end_dt, use_gate3=False, rejected_only=True)

    print("\n2. GATE 3 (S/R TRAP FILTER) CONTROLLED ABLATION ON EURUSD (2020 - 2026 YTD):")
    print(f"{'Configuration':30s} | {'Trades':6s} | {'Win Rate':8s} | {'Profit Factor':13s} | {'Expectancy/Trd':15s} | {'Net P&L':12s} | {'Max DD':8s}")
    print("-" * 105)
    print(f"{'With Gate 3 (Live Standard)':30s} | {res_eur_with_gate3['trades']:6d} | {res_eur_with_gate3['win_rate']:7.1f}% | {res_eur_with_gate3['pf']:13.2f} | ${res_eur_with_gate3['expectancy']:+13.2f} | ${res_eur_with_gate3['net_pnl']:+11.2f} | {res_eur_with_gate3['max_dd_pct']:6.2f}%")
    print(f"{'Without Gate 3 (Raw Breakout)':30s} | {res_eur_no_gate3['trades']:6d} | {res_eur_no_gate3['win_rate']:7.1f}% | {res_eur_no_gate3['pf']:13.2f} | ${res_eur_no_gate3['expectancy']:+13.2f} | ${res_eur_no_gate3['net_pnl']:+11.2f} | {res_eur_no_gate3['max_dd_pct']:6.2f}%")
    print(f"{'REJECTED SETUPS ONLY (Counterfactual)':30s} | {res_eur_rejected_only['trades']:6d} | {res_eur_rejected_only['win_rate']:7.1f}% | {res_eur_rejected_only['pf']:13.2f} | ${res_eur_rejected_only['expectancy']:+13.2f} | ${res_eur_rejected_only['net_pnl']:+11.2f} | {res_eur_rejected_only['max_dd_pct']:6.2f}%")

    # -------------------------------------------------------------------------
    # 3. XAUUSD (GOLD) ROBUSTNESS & STRESS-TESTING
    # -------------------------------------------------------------------------
    r1_xau, r4_xau = load_data("XAUUSD", start_dt, end_dt)
    sh_xau, sl_xau = precompute_swings(r1_xau)

    scenarios = {
        "1. Baseline (Standard Spread $0.35)": {"spread": 0.35, "slip": 0.0, "drop": 0},
        "2. Spread Stress (+25% Spread = $0.44)": {"spread": 0.44, "slip": 0.0, "drop": 0},
        "3. Spread Stress (+50% Spread = $0.52)": {"spread": 0.52, "slip": 0.0, "drop": 0},
        "4. Execution Slippage (+2 Ticks = $0.20)": {"spread": 0.35, "slip": 0.20, "drop": 0},
        "5. Extreme Slippage (+5 Ticks = $0.50)": {"spread": 0.35, "slip": 0.50, "drop": 0},
        "6. Outlier Jackknife (Drop Top 5 Wins)": {"spread": 0.35, "slip": 0.0, "drop": 5},
        "7. Outlier Jackknife (Drop Top 10 Wins)": {"spread": 0.35, "slip": 0.0, "drop": 10},
    }

    print("\n3. XAUUSD (GOLD) 4H TREND-RIDER STRESS-TESTING & OUTLIER JACKKNIFE (2020 - 2026 YTD):")
    print(f"{'Stress Scenario':42s} | {'Trades':6s} | {'Win Rate':8s} | {'Profit Factor':13s} | {'Expectancy/Trd':15s} | {'Net P&L':12s} | {'Max DD':8s}")
    print("-" * 105)
    gold_stress_results = {}
    for sc_name, p in scenarios.items():
        res_xau = run_parameterized_engine("XAUUSD", r1_xau, r4_xau, sh_xau, sl_xau, "Strategy_C_4H_Trend_Rider", start_dt, end_dt,
                                           spread_val=p['spread'], extra_slippage=p['slip'], drop_top_n=p['drop'])
        gold_stress_results[sc_name] = res_xau
        print(f"{sc_name:42s} | {res_xau['trades']:6d} | {res_xau['win_rate']:7.1f}% | {res_xau['pf']:13.2f} | ${res_xau['expectancy']:+13.2f} | ${res_xau['net_pnl']:+11.2f} | {res_xau['max_dd_pct']:6.2f}%")

    out_json = {
        "gbpusd_ablation": {"all_hours": res_gbp_all, "session_hours": res_gbp_sess},
        "eurusd_gate3_ablation": {"with_gate3": res_eur_with_gate3, "without_gate3": res_eur_no_gate3, "rejected_only": res_eur_rejected_only},
        "gold_stress_tests": gold_stress_results
    }
    with open(r"d:\Techwaves-egy\Trading Team Skills\journal\rigorous_validation_report_2020_2026.json", "w", encoding="utf-8") as f:
        json.dump(out_json, f, indent=2, default=str)

    mt5.shutdown()

if __name__ == "__main__":
    main()
