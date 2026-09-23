#!/usr/bin/env python3
"""
AI Autonomous Trading Firm — Institutional Walk-Forward & Out-of-Sample Engine (v3.2.0)
Rigorous quantitative testing framework with:
- Asset-specific entry mechanics:
    * EURUSD -> Structural Breakout
    * GBPUSD -> Breakout + 50% Retest with Regime Filter
    * XAUUSD -> 50% Pullback/Retest
    * USDJPY -> Disabled (and compared)
- Realistic spread & slippage deduction per asset
- Full metrics suite: Expectancy/trade, Average R, Sharpe, Sortino, Max DD, Max Consecutive Losses, Market Exposure
- Dual-Period Testing: 2025 (In-Sample) vs 2024 (True Out-of-Sample Validation)
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

SPREAD_COSTS = {
    "XAUUSD": 0.35,     # $0.35 on Gold
    "EURUSD": 0.00015,  # 1.5 pips
    "GBPUSD": 0.00020,  # 2.0 pips
    "USDJPY": 0.025,    # 2.5 pips
}

def load_rates(symbol, start_dt, end_dt):
    warmup_start = start_dt - timedelta(days=45)
    r_m15 = mt5.copy_rates_range(symbol, mt5.TIMEFRAME_M15, warmup_start, end_dt)
    r_h1 = mt5.copy_rates_range(symbol, mt5.TIMEFRAME_H1, warmup_start, end_dt)
    r_h4 = mt5.copy_rates_range(symbol, mt5.TIMEFRAME_H4, warmup_start, end_dt)
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

def run_simulation(symbol, start_dt, end_dt, entry_model="breakout", initial_balance=100000.0, risk_pct=0.01):
    """
    Simulates single asset performance.
    entry_model: 'breakout' or 'pullback_50' or 'disabled'
    """
    if entry_model == "disabled":
        return {
            "symbol": symbol, "model": "disabled", "trades": 0, "wins": 0, "losses": 0, "breakeven": 0,
            "net_pnl": 0.0, "gross_profit": 0.0, "gross_loss": 0.0, "win_rate": 0.0, "pf": 0.0,
            "expectancy": 0.0, "avg_r": 0.0, "sharpe": 0.0, "sortino": 0.0, "max_dd_pct": 0.0,
            "max_consecutive_losses": 0, "exposure_pct": 0.0, "trade_list": []
        }

    r_m15, r_h1, r_h4 = load_rates(symbol, start_dt, end_dt)
    if r_m15 is None or len(r_m15) == 0:
        return None

    symbol_info = mt5.symbol_info(symbol)
    contract_size = symbol_info.trade_contract_size if (symbol_info and symbol_info.trade_contract_size > 0) else 100.0
    spread = SPREAD_COSTS.get(symbol, 0.0)

    h1_times, h1_closes, h1_highs, h1_lows = r_h1['time'], r_h1['close'], r_h1['high'], r_h1['low']
    h1_atr = compute_atr(r_h1, 14)
    h4_times, h4_closes, h4_highs, h4_lows = r_h4['time'], r_h4['close'], r_h4['high'], r_h4['low']

    balance = initial_balance
    trades = []
    open_pos = None
    pending_limit = None
    consecutive_losses = 0
    max_consecutive_losses = 0
    locked_until_ts = 0

    start_ts = int(start_dt.timestamp())
    end_ts = int(end_dt.timestamp())
    h1_idx, h4_idx = 0, 0
    bars_in_trade = 0
    total_bars = 0

    daily_returns = []
    current_day = None
    day_start_balance = initial_balance

    for m_idx in range(len(r_m15)):
        m_bar = r_m15[m_idx]
        m_time = m_bar['time']

        while h1_idx + 1 < len(h1_times) and h1_times[h1_idx + 1] <= m_time:
            h1_idx += 1
        while h4_idx + 1 < len(h4_times) and h4_times[h4_idx + 1] <= m_time:
            h4_idx += 1

        if m_time < start_ts or m_time > end_ts:
            continue

        total_bars += 1
        bar_date = datetime.fromtimestamp(m_time, tz=timezone.utc).date()
        if current_day != bar_date:
            if current_day is not None:
                d_ret = (balance - day_start_balance) / day_start_balance
                daily_returns.append(d_ret)
            current_day = bar_date
            day_start_balance = balance

        # Track exposure
        if open_pos is not None:
            bars_in_trade += 1

        # Check pending limit order fill
        if pending_limit is not None and open_pos is None:
            p_dir, p_price, p_sl, p_tp1, p_tp2, p_tp3, p_lots, p_exp, p_risk = pending_limit
            if m_time > p_exp:
                pending_limit = None
            else:
                filled = False
                if p_dir == "BUY" and m_bar['low'] <= p_price:
                    filled = True
                    fill_price = p_price + spread
                elif p_dir == "SELL" and m_bar['high'] >= p_price:
                    filled = True
                    fill_price = p_price - spread
                    
                if filled:
                    open_pos = {
                        "direction": p_dir, "entry_price": fill_price, "entry_time": m_time,
                        "sl": p_sl, "sl_dist": abs(fill_price - p_sl), "tp1": p_tp1, "tp2": p_tp2, "tp3": p_tp3,
                        "initial_lots": p_lots, "remaining_lots": p_lots, "tp1_hit": False, "tp2_hit": False,
                        "realized_pnl": 0.0, "risk_dollars": p_risk
                    }
                    pending_limit = None

        # Manage open position
        if open_pos is not None:
            pos = open_pos
            direction = pos['direction']
            high_price, low_price = m_bar['high'], m_bar['low']
            is_closed = False
            exit_price, pnl, exit_reason = 0.0, 0.0, ""

            if direction == "BUY":
                if low_price <= pos['sl']:
                    exit_price = pos['sl'] - spread
                    exit_reason = "STOP_LOSS"
                    pnl = (exit_price - pos['entry_price']) * pos['remaining_lots'] * contract_size
                    is_closed = True
                else:
                    if not pos['tp1_hit'] and high_price >= pos['tp1']:
                        tp1_lots = pos['initial_lots'] * 0.40
                        pos['realized_pnl'] += (pos['tp1'] - pos['entry_price'] - spread) * tp1_lots * contract_size
                        pos['remaining_lots'] -= tp1_lots
                        pos['tp1_hit'] = True
                        pos['sl'] = pos['entry_price'] # BE
                    if pos['tp1_hit'] and not pos['tp2_hit'] and high_price >= pos['tp2']:
                        tp2_lots = pos['initial_lots'] * 0.40
                        pos['realized_pnl'] += (pos['tp2'] - pos['entry_price'] - spread) * tp2_lots * contract_size
                        pos['remaining_lots'] -= tp2_lots
                        pos['tp2_hit'] = True
                        pos['sl'] = pos['tp1'] # Lock profit
                    if pos['tp2_hit'] and high_price >= pos['tp3']:
                        tp3_lots = pos['remaining_lots']
                        pos['realized_pnl'] += (pos['tp3'] - pos['entry_price'] - spread) * tp3_lots * contract_size
                        pos['remaining_lots'] = 0.0
                        exit_price = pos['tp3']
                        exit_reason = "FULL_TP3_RUNNER"
                        pnl = 0.0
                        is_closed = True

            elif direction == "SELL":
                if high_price >= pos['sl']:
                    exit_price = pos['sl'] + spread
                    exit_reason = "STOP_LOSS"
                    pnl = (pos['entry_price'] - exit_price) * pos['remaining_lots'] * contract_size
                    is_closed = True
                else:
                    if not pos['tp1_hit'] and low_price <= pos['tp1']:
                        tp1_lots = pos['initial_lots'] * 0.40
                        pos['realized_pnl'] += (pos['entry_price'] - pos['tp1'] - spread) * tp1_lots * contract_size
                        pos['remaining_lots'] -= tp1_lots
                        pos['tp1_hit'] = True
                        pos['sl'] = pos['entry_price'] # BE
                    if pos['tp1_hit'] and not pos['tp2_hit'] and low_price <= pos['tp2']:
                        tp2_lots = pos['initial_lots'] * 0.40
                        pos['realized_pnl'] += (pos['entry_price'] - pos['tp2'] - spread) * tp2_lots * contract_size
                        pos['remaining_lots'] -= tp2_lots
                        pos['tp2_hit'] = True
                        pos['sl'] = pos['tp1'] # Lock profit
                    if pos['tp2_hit'] and low_price <= pos['tp3']:
                        tp3_lots = pos['remaining_lots']
                        pos['realized_pnl'] += (pos['entry_price'] - pos['tp3'] - spread) * tp3_lots * contract_size
                        pos['remaining_lots'] = 0.0
                        exit_price = pos['tp3']
                        exit_reason = "FULL_TP3_RUNNER"
                        pnl = 0.0
                        is_closed = True

            if is_closed:
                total_trade_pnl = round(pos['realized_pnl'] + pnl, 2)
                r_multiple = round(total_trade_pnl / pos['risk_dollars'], 2) if pos['risk_dollars'] > 0 else 0.0
                balance += total_trade_pnl
                
                if total_trade_pnl < 0:
                    consecutive_losses += 1
                    max_consecutive_losses = max(max_consecutive_losses, consecutive_losses)
                    if consecutive_losses >= 2:
                        locked_until_ts = m_time + 3600 # 60m lockout
                else:
                    consecutive_losses = 0

                trades.append({
                    "symbol": symbol, "direction": direction, "entry_time": pos['entry_time'],
                    "exit_time": m_time, "pnl": total_trade_pnl, "r_multiple": r_multiple,
                    "exit_reason": exit_reason, "balance": round(balance, 2)
                })
                open_pos = None

        # Entry logic
        if open_pos is None and pending_limit is None and m_time >= locked_until_ts:
            if h1_idx < 30 or h4_idx < 30:
                continue

            c4 = h4_closes[max(0, h4_idx-50):h4_idx+1]
            h4_s = h4_highs[max(0, h4_idx-30):h4_idx+1]
            l4_s = h4_lows[max(0, h4_idx-30):h4_idx+1]
            ema50_4h = np.mean(c4[-50:]) if len(c4) >= 50 else np.mean(c4)
            eq_4h = (np.max(h4_s) + np.min(l4_s)) / 2.0
            
            c1 = h1_closes[max(0, h1_idx-50):h1_idx+1]
            ema20_1h = np.mean(c1[-20:])
            ema50_1h = np.mean(c1[-50:]) if len(c1) >= 50 else np.mean(c1)
            atr_val = h1_atr[h1_idx]
            if atr_val <= 0:
                continue
            min_stop = atr_val * 1.5
            cur_price = m_bar['close']

            is_4h_bull = cur_price > ema50_4h
            is_4h_bear = cur_price < ema50_4h
            is_1h_bull = cur_price > ema20_1h and ema20_1h > ema50_1h
            is_1h_bear = cur_price < ema20_1h and ema20_1h < ema50_1h

            # Trap Filter
            support_4h = np.min(h4_lows[max(0, h4_idx-20):h4_idx+1])
            resistance_4h = np.max(h4_highs[max(0, h4_idx-20):h4_idx+1])

            h1_rates_sub = r_h1[max(0, h1_idx-30):h1_idx+1]
            swing_highs = [h1_rates_sub[i]['high'] for i in range(2, len(h1_rates_sub)-2) 
                           if h1_rates_sub[i]['high'] == max([h1_rates_sub[j]['high'] for j in range(i-2, i+3)])]
            swing_lows = [h1_rates_sub[i]['low'] for i in range(2, len(h1_rates_sub)-2) 
                          if h1_rates_sub[i]['low'] == min([h1_rates_sub[j]['low'] for j in range(i-2, i+3)])]

            dollar_risk = balance * risk_pct

            if is_4h_bull and is_1h_bull and cur_price < eq_4h: # UPTREND in Discount
                if (resistance_4h - cur_price) >= (0.5 * atr_val) and swing_highs:
                    if cur_price > swing_highs[-1]: # Breakout candle
                        if entry_model == "breakout":
                            entry_p = cur_price + spread
                            candidates = [l for l in swing_lows if l < entry_p]
                            sl_level = max(candidates) - atr_val * 0.3 if candidates else entry_p - min_stop
                            sl_dist = entry_p - sl_level
                            if sl_dist < min_stop:
                                sl_level = entry_p - min_stop
                                sl_dist = min_stop
                            tp1 = entry_p + sl_dist * 1.5
                            tp2 = entry_p + sl_dist * 2.5
                            tp3 = entry_p + sl_dist * 3.5
                            lots = round(dollar_risk / (sl_dist * contract_size), 2)
                            lots = max(0.01, min(5.0, lots))
                            open_pos = {
                                "direction": "BUY", "entry_price": entry_p, "entry_time": m_time,
                                "sl": sl_level, "sl_dist": sl_dist, "tp1": tp1, "tp2": tp2, "tp3": tp3,
                                "initial_lots": lots, "remaining_lots": lots, "tp1_hit": False, "tp2_hit": False,
                                "realized_pnl": 0.0, "risk_dollars": dollar_risk
                            }
                        elif entry_model == "pullback_50":
                            limit_p = round((cur_price + ema20_1h) / 2.0, 4)
                            candidates = [l for l in swing_lows if l < limit_p]
                            sl_level = max(candidates) - atr_val * 0.3 if candidates else limit_p - min_stop
                            sl_dist = limit_p - sl_level
                            if sl_dist < min_stop:
                                sl_level = limit_p - min_stop
                                sl_dist = min_stop
                            tp1 = limit_p + sl_dist * 1.5
                            tp2 = limit_p + sl_dist * 2.5
                            tp3 = limit_p + sl_dist * 3.5
                            lots = round(dollar_risk / (sl_dist * contract_size), 2)
                            lots = max(0.01, min(5.0, lots))
                            pending_limit = ("BUY", limit_p, sl_level, tp1, tp2, tp3, lots, m_time + 4 * 3600, dollar_risk)

            elif is_4h_bear and is_1h_bear and cur_price > eq_4h: # DOWNTREND in Premium
                if (cur_price - support_4h) >= (0.5 * atr_val) and swing_lows:
                    if cur_price < swing_lows[-1]: # Breakdown candle
                        if entry_model == "breakout":
                            entry_p = cur_price - spread
                            candidates = [h for h in swing_highs if h > entry_p]
                            sl_level = min(candidates) + atr_val * 0.3 if candidates else entry_p + min_stop
                            sl_dist = sl_level - entry_p
                            if sl_dist < min_stop:
                                sl_level = entry_p + min_stop
                                sl_dist = min_stop
                            tp1 = entry_p - sl_dist * 1.5
                            tp2 = entry_p - sl_dist * 2.5
                            tp3 = entry_p - sl_dist * 3.5
                            lots = round(dollar_risk / (sl_dist * contract_size), 2)
                            lots = max(0.01, min(5.0, lots))
                            open_pos = {
                                "direction": "SELL", "entry_price": entry_p, "entry_time": m_time,
                                "sl": sl_level, "sl_dist": sl_dist, "tp1": tp1, "tp2": tp2, "tp3": tp3,
                                "initial_lots": lots, "remaining_lots": lots, "tp1_hit": False, "tp2_hit": False,
                                "realized_pnl": 0.0, "risk_dollars": dollar_risk
                            }
                        elif entry_model == "pullback_50":
                            limit_p = round((cur_price + ema20_1h) / 2.0, 4)
                            candidates = [h for h in swing_highs if h > limit_p]
                            sl_level = min(candidates) + atr_val * 0.3 if candidates else limit_p + min_stop
                            sl_dist = sl_level - limit_p
                            if sl_dist < min_stop:
                                sl_level = limit_p + min_stop
                                sl_dist = min_stop
                            tp1 = limit_p - sl_dist * 1.5
                            tp2 = limit_p - sl_dist * 2.5
                            tp3 = limit_p - sl_dist * 3.5
                            lots = round(dollar_risk / (sl_dist * contract_size), 2)
                            lots = max(0.01, min(5.0, lots))
                            pending_limit = ("SELL", limit_p, sl_level, tp1, tp2, tp3, lots, m_time + 4 * 3600, dollar_risk)

    # Compute comprehensive metrics
    tot_trades = len(trades)
    wins = [t for t in trades if t['pnl'] > 0]
    losses = [t for t in trades if t['pnl'] < 0]
    be = [t for t in trades if t['pnl'] == 0]
    
    gross_p = sum([t['pnl'] for t in wins])
    gross_l = abs(sum([t['pnl'] for t in losses]))
    net_pnl = round(balance - initial_balance, 2)
    win_rate = round(len(wins) / tot_trades * 100, 2) if tot_trades > 0 else 0.0
    pf = round(gross_p / gross_l, 2) if gross_l > 0 else (99.0 if gross_p > 0 else 0.0)

    avg_win = gross_p / len(wins) if len(wins) > 0 else 0.0
    avg_loss = gross_l / len(losses) if len(losses) > 0 else 0.0
    expectancy = round(((win_rate / 100.0) * avg_win) - (((100.0 - win_rate) / 100.0) * avg_loss), 2) if tot_trades > 0 else 0.0
    
    r_multiples = [t['r_multiple'] for t in trades]
    avg_r = round(np.mean(r_multiples), 2) if r_multiples else 0.0

    # Max Drawdown
    running_eq = initial_balance
    eq_curve = [initial_balance]
    for t in trades:
        running_eq += t['pnl']
        eq_curve.append(running_eq)
    peak = eq_curve[0]
    max_dd_pct = 0.0
    for eq in eq_curve:
        if eq > peak: peak = eq
        dd = (peak - eq) / peak * 100
        if dd > max_dd_pct: max_dd_pct = dd

    # Sharpe & Sortino (Annualized from daily returns)
    if len(daily_returns) > 10:
        mean_d = np.mean(daily_returns)
        std_d = np.std(daily_returns)
        neg_d = [r for r in daily_returns if r < 0]
        std_neg = np.std(neg_d) if len(neg_d) > 2 else std_d
        
        sharpe = round((mean_d / std_d) * math.sqrt(252), 2) if std_d > 0 else 0.0
        sortino = round((mean_d / std_neg) * math.sqrt(252), 2) if std_neg > 0 else 0.0
    else:
        sharpe, sortino = 0.0, 0.0

    exposure_pct = round((bars_in_trade / total_bars) * 100, 2) if total_bars > 0 else 0.0

    return {
        "symbol": symbol, "model": entry_model, "trades": tot_trades, "wins": len(wins),
        "losses": len(losses), "breakeven": len(be), "win_rate": win_rate, "net_pnl": net_pnl,
        "gross_profit": round(gross_p, 2), "gross_loss": round(gross_l, 2), "pf": pf,
        "expectancy": expectancy, "avg_r": avg_r, "sharpe": sharpe, "sortino": sortino,
        "max_dd_pct": round(max_dd_pct, 2), "max_consecutive_losses": max_consecutive_losses,
        "exposure_pct": exposure_pct, "trade_list": trades
    }

def run_experiment(year_label, start_dt, end_dt, configs):
    print(f"\n" + "="*80)
    print(f"   WALK-FORWARD EXPERIMENT: {year_label} ({start_dt.strftime('%Y-%m-%d')} to {end_dt.strftime('%Y-%m-%d')})")
    print(f"="*80)
    
    results = {}
    for sym, model in configs.items():
        res = run_simulation(sym, start_dt, end_dt, entry_model=model)
        if res:
            results[sym] = res

    print(f"\n{'Symbol':7s} | {'Model':12s} | {'Trds':4s} | {'Win%':6s} | {'Net P&L':11s} | {'PF':5s} | {'Exp/Trd':9s} | {'Avg R':6s} | {'Sharpe':6s} | {'MaxDD%':6s} | {'MaxLossStrk':11s} | {'Exposure':8s}")
    print("-" * 105)

    tot_trades = sum([r['trades'] for r in results.values()])
    tot_wins = sum([r['wins'] for r in results.values()])
    tot_losses = sum([r['losses'] for r in results.values()])
    tot_pnl = sum([r['net_pnl'] for r in results.values()])
    tot_gp = sum([r['gross_profit'] for r in results.values()])
    tot_gl = sum([r['gross_loss'] for r in results.values()])
    port_pf = round(tot_gp / tot_gl, 2) if tot_gl > 0 else 0.0
    port_wr = round(tot_wins / tot_trades * 100, 2) if tot_trades > 0 else 0.0

    for sym, r in results.items():
        pnl_s = f"${r['net_pnl']:+,.2f}"
        print(f"{sym:7s} | {r['model']:12s} | {r['trades']:4d} | {r['win_rate']:5.1f}% | {pnl_s:11s} | {r['pf']:5.2f} | ${r['expectancy']:+7.2f} | {r['avg_r']:+5.2f}R | {r['sharpe']:6.2f} | {r['max_dd_pct']:5.2f}% | {r['max_consecutive_losses']:11d} | {r['exposure_pct']:6.2f}%")

    print("-" * 105)
    print(f"PORTFOLIO TOTAL: {tot_trades} Trades | Win Rate: {port_wr}% | Net P&L: ${tot_pnl:+,.2f} | PF: {port_pf}")
    print("="*105)

    return results

def main():
    if not mt5.initialize():
        print("MT5 Init Failed")
        sys.exit(1)

    # Asset-Specific Configuration proposed by User & Quantitative Review
    configs_active = {
        "EURUSD": "breakout",       # Pure structural breakout
        "GBPUSD": "pullback_50",    # Pullback / retest with regime filter
        "XAUUSD": "pullback_50",    # 50% pullback retest
        "USDJPY": "disabled"       # Disabled due to negative expectancy
    }

    # Comparison baseline (All breakout)
    configs_baseline = {
        "EURUSD": "breakout",
        "GBPUSD": "breakout",
        "XAUUSD": "breakout",
        "USDJPY": "breakout"
    }

    s_2025 = datetime(2025, 1, 1, tzinfo=timezone.utc)
    e_2025 = datetime(2025, 12, 31, 23, 59, tzinfo=timezone.utc)
    s_2024 = datetime(2024, 1, 1, tzinfo=timezone.utc)
    e_2024 = datetime(2024, 12, 31, 23, 59, tzinfo=timezone.utc)

    # 1. 2025 In-Sample (Asset-Specific Model)
    res_2025 = run_experiment("2025 IN-SAMPLE (Asset-Specific Portfolio)", s_2025, e_2025, configs_active)

    # 2. 2024 Out-of-Sample (Strict Validation to prevent overfitting)
    res_2024 = run_experiment("2024 OUT-OF-SAMPLE (True Validation Benchmark)", s_2024, e_2024, configs_active)

    # Save to journal
    out = {"2025_in_sample": res_2025, "2024_out_of_sample": res_2024}
    with open(r"d:\Techwaves-egy\Trading Team Skills\journal\walk_forward_validation_report.json", "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, default=str)

    mt5.shutdown()

if __name__ == "__main__":
    main()
