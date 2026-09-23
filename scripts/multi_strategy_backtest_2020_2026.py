#!/usr/bin/env python3
"""
AI Autonomous Trading Firm — Multi-Strategy 2020-2026 Historical Benchmark (High Speed)
Comprehensive quantitative comparison across 6.6 years (2020-01-01 to 2026-08-28)
Comparing 4 primary institutional trading paradigms:
  1. Strategy A: Multi-Timeframe Structural Breakout
  2. Strategy B: Multi-Timeframe 50% Pullback Retest
  3. Strategy C: 4H Trend-Continuation (4H EMA20 Pullback Rider)
  4. Strategy D: SMC Liquidity Sweep & Range Reversal (Fade Traps)
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

def precompute_swings(rates):
    """Precompute 5-bar fractal swing highs and lows vectorized"""
    highs = rates['high']
    lows = rates['low']
    n = len(rates)
    is_swing_high = np.zeros(n, dtype=bool)
    is_swing_low = np.zeros(n, dtype=bool)
    
    for i in range(2, n - 2):
        if highs[i] > highs[i-1] and highs[i] > highs[i-2] and highs[i] > highs[i+1] and highs[i] > highs[i+2]:
            is_swing_high[i] = True
        if lows[i] < lows[i-1] and lows[i] < lows[i-2] and lows[i] < lows[i+1] and lows[i] < lows[i+2]:
            is_swing_low[i] = True
            
    return is_swing_high, is_swing_low

def run_strategy_backtest(symbol, r_1h, r_4h, is_sh_1h, is_sl_1h, strategy_type, start_dt, end_dt, initial_balance=100000.0, risk_pct=0.01):
    symbol_info = mt5.symbol_info(symbol)
    contract_size = symbol_info.trade_contract_size if (symbol_info and symbol_info.trade_contract_size > 0) else 100.0
    spread = SPREADS.get(symbol, 0.0)

    h1_times = r_1h['time']
    h1_opens = r_1h['open']
    h1_highs = r_1h['high']
    h1_lows = r_1h['low']
    h1_closes = r_1h['close']
    h1_atr = compute_atr(r_1h, 14)

    h4_times = r_4h['time']
    h4_opens = r_4h['open']
    h4_highs = r_4h['high']
    h4_lows = r_4h['low']
    h4_closes = r_4h['close']
    h4_atr = compute_atr(r_4h, 14)

    # Pre-calculate rolling EMAs
    ema20_1h = np.convolve(h1_closes, np.ones(20)/20, mode='same')
    ema50_1h = np.convolve(h1_closes, np.ones(50)/50, mode='same')
    ema20_4h = np.convolve(h4_closes, np.ones(20)/20, mode='same')
    ema50_4h = np.convolve(h4_closes, np.ones(50)/50, mode='same')

    balance = initial_balance
    trades = []
    open_pos = None
    pending_limit = None
    consecutive_losses = 0
    max_consecutive_losses = 0
    locked_until_ts = 0

    start_ts = int(start_dt.timestamp())
    end_ts = int(end_dt.timestamp())
    h4_idx = 0

    daily_returns = []
    current_day = None
    day_start_balance = initial_balance
    bars_in_trade = 0
    total_bars = 0

    for i in range(50, len(r_1h)):
        t1 = h1_times[i]
        
        while h4_idx + 1 < len(h4_times) and h4_times[h4_idx + 1] <= t1:
            h4_idx += 1

        if t1 < start_ts or t1 > end_ts:
            continue

        total_bars += 1
        bar_date = datetime.fromtimestamp(t1, tz=timezone.utc).date()
        if current_day != bar_date:
            if current_day is not None:
                d_ret = (balance - day_start_balance) / day_start_balance
                daily_returns.append(d_ret)
            current_day = bar_date
            day_start_balance = balance

        if open_pos is not None:
            bars_in_trade += 1

        # Process pending limit orders
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
                        pos['sl'] = pos['entry_price'] # Move SL to BE
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
                    max_consecutive_losses = max(max_consecutive_losses, consecutive_losses)
                    if consecutive_losses >= 2:
                        locked_until_ts = t1 + 3600 # 60m lockout
                else:
                    consecutive_losses = 0

                trades.append({
                    "symbol": symbol, "strategy": strategy_type, "direction": direction,
                    "entry_time": datetime.fromtimestamp(pos['entry_time'], tz=timezone.utc).strftime("%Y-%m-%d %H:%M"),
                    "exit_time": datetime.fromtimestamp(t1, tz=timezone.utc).strftime("%Y-%m-%d %H:%M"),
                    "year": datetime.fromtimestamp(pos['entry_time'], tz=timezone.utc).year,
                    "pnl": total_trade_pnl, "r_multiple": r_mult, "exit_reason": exit_reason, "balance": round(balance, 2)
                })
                open_pos = None

        # Entry logic
        if open_pos is None and pending_limit is None and t1 >= locked_until_ts:
            if h4_idx < 30:
                continue

            cur_p = h1_closes[i]
            atr1 = h1_atr[i]
            if atr1 <= 0:
                continue
            min_stop = atr1 * 1.5
            dollar_risk = balance * risk_pct

            # 4H metrics
            e20_4 = ema20_4h[h4_idx]
            e50_4 = ema50_4h[h4_idx]
            h4_window_hi = h4_highs[max(0, h4_idx-30):h4_idx+1]
            h4_window_lo = h4_lows[max(0, h4_idx-30):h4_idx+1]
            range_high_4h = np.max(h4_window_hi)
            range_low_4h = np.min(h4_window_lo)
            eq_4h = (range_high_4h + range_low_4h) / 2.0
            support_4h = np.min(h4_lows[max(0, h4_idx-20):h4_idx+1])
            resistance_4h = np.max(h4_highs[max(0, h4_idx-20):h4_idx+1])

            # 1H metrics
            e20_1 = ema20_1h[i]
            e50_1 = ema50_1h[i]

            # Fast recent swing lookup
            sh_indices = np.where(is_sh_1h[max(0, i-30):i-1])[0]
            sl_indices = np.where(is_sl_1h[max(0, i-30):i-1])[0]
            
            last_sh = h1_highs[max(0, i-30) + sh_indices[-1]] if len(sh_indices) > 0 else None
            last_sl = h1_lows[max(0, i-30) + sl_indices[-1]] if len(sl_indices) > 0 else None

            # -------------------------------------------------------------
            # STRATEGY A: Multi-Timeframe Structural Breakout (v3.1.0)
            # -------------------------------------------------------------
            if strategy_type == "Strategy_A_Breakout":
                is_bull = cur_p > e50_4 and cur_p > e20_1 and e20_1 > e50_1 and cur_p < eq_4h
                is_bear = cur_p < e50_4 and cur_p < e20_1 and e20_1 < e50_1 and cur_p > eq_4h

                if is_bull and (resistance_4h - cur_p) >= (0.5 * atr1) and last_sh is not None:
                    if cur_p > last_sh:
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

                elif is_bear and (cur_p - support_4h) >= (0.5 * atr1) and last_sl is not None:
                    if cur_p < last_sl:
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

            # -------------------------------------------------------------
            # STRATEGY B: Multi-Timeframe 50% Pullback Retest
            # -------------------------------------------------------------
            elif strategy_type == "Strategy_B_Pullback_50":
                is_bull = cur_p > e50_4 and cur_p > e20_1 and cur_p < eq_4h
                is_bear = cur_p < e50_4 and cur_p < e20_1 and cur_p > eq_4h

                if is_bull and (resistance_4h - cur_p) >= (0.5 * atr1) and last_sh is not None:
                    if cur_p > last_sh:
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
                        limit_p = round((cur_p + e20_1) / 2.0, 4)
                        sl_level = last_sh + atr1 * 0.3 if last_sh is not None else limit_p + min_stop
                        sl_dist = max(min_stop, sl_level - limit_p)
                        sl_level = limit_p + sl_dist
                        tp1 = limit_p - sl_dist * 1.5
                        tp2 = limit_p - sl_dist * 2.5
                        tp3 = limit_p - sl_dist * 3.5
                        lots = max(0.01, min(5.0, round(dollar_risk / (sl_dist * contract_size), 2)))
                        pending_limit = ("SELL", limit_p, sl_level, tp1, tp2, tp3, lots, t1 + 4 * 3600, dollar_risk)

            # -------------------------------------------------------------
            # STRATEGY C: 4H Trend Continuation (4H EMA20 Pullback Rider)
            # -------------------------------------------------------------
            elif strategy_type == "Strategy_C_4H_Trend_Rider":
                atr4 = h4_atr[h4_idx] if h4_idx < len(h4_atr) else atr1 * 2.0
                is_4h_uptrend = e20_4 > e50_4 and h4_closes[h4_idx] > e50_4
                is_4h_downtrend = e20_4 < e50_4 and h4_closes[h4_idx] < e50_4

                # BUY on 4H EMA20 test with 1H bullish candle
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

                # SELL on 4H EMA20 test with 1H bearish candle
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

            # -------------------------------------------------------------
            # STRATEGY D: SMC Liquidity Sweep & Range Reversal (Fade Traps)
            # -------------------------------------------------------------
            elif strategy_type == "Strategy_D_SMC_Sweep_Reversal":
                swept_high = h1_highs[i] > range_high_4h and h1_closes[i] < range_high_4h
                swept_low = h1_lows[i] < range_low_4h and h1_closes[i] > range_low_4h

                if swept_high and h1_closes[i] < h1_opens[i]: # Bearish rejection after sweep
                    entry_p = cur_p - spread
                    sl_dist = max(min_stop, (h1_highs[i] + 0.2 * atr1) - entry_p)
                    sl_level = entry_p + sl_dist
                    tp1 = entry_p - (entry_p - eq_4h) * 0.5
                    tp2 = eq_4h
                    tp3 = range_low_4h + 0.5 * atr1
                    lots = max(0.01, min(5.0, round(dollar_risk / (sl_dist * contract_size), 2)))
                    open_pos = {
                        "direction": "SELL", "entry_price": entry_p, "entry_time": t1, "sl": sl_level,
                        "sl_dist": sl_dist, "tp1": tp1, "tp2": tp2, "tp3": tp3, "initial_lots": lots,
                        "remaining_lots": lots, "tp1_hit": False, "tp2_hit": False, "realized_pnl": 0.0, "risk_dollars": dollar_risk
                    }

                elif swept_low and h1_closes[i] > h1_opens[i]: # Bullish rejection after sweep
                    entry_p = cur_p + spread
                    sl_dist = max(min_stop, entry_p - (h1_lows[i] - 0.2 * atr1))
                    sl_level = entry_p - sl_dist
                    tp1 = entry_p + (eq_4h - entry_p) * 0.5
                    tp2 = eq_4h
                    tp3 = range_high_4h - 0.5 * atr1
                    lots = max(0.01, min(5.0, round(dollar_risk / (sl_dist * contract_size), 2)))
                    open_pos = {
                        "direction": "BUY", "entry_price": entry_p, "entry_time": t1, "sl": sl_level,
                        "sl_dist": sl_dist, "tp1": tp1, "tp2": tp2, "tp3": tp3, "initial_lots": lots,
                        "remaining_lots": lots, "tp1_hit": False, "tp2_hit": False, "realized_pnl": 0.0, "risk_dollars": dollar_risk
                    }

    # Summary metrics
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

    if len(daily_returns) > 10:
        mean_d = np.mean(daily_returns)
        std_d = np.std(daily_returns)
        sharpe = round((mean_d / std_d) * math.sqrt(252), 2) if std_d > 0 else 0.0
    else:
        sharpe = 0.0

    exposure_pct = round((bars_in_trade / total_bars) * 100, 2) if total_bars > 0 else 0.0

    yearly = {}
    for y in range(2020, 2027):
        y_trades = [t for t in trades if t['year'] == y]
        y_pnl = sum([t['pnl'] for t in y_trades])
        y_wins = [t for t in y_trades if t['pnl'] > 0]
        y_wr = round(len(y_wins)/len(y_trades)*100, 1) if y_trades else 0.0
        yearly[str(y)] = {"trades": len(y_trades), "pnl": round(y_pnl, 2), "win_rate": y_wr}

    return {
        "symbol": symbol, "strategy": strategy_type, "trades": tot_trades, "wins": len(wins),
        "losses": len(losses), "breakeven": len(be), "win_rate": win_rate, "net_pnl": net_pnl,
        "gross_profit": round(gross_p, 2), "gross_loss": round(gross_l, 2), "pf": pf,
        "expectancy": expectancy, "avg_r": avg_r, "sharpe": sharpe,
        "max_dd_pct": round(max_dd_pct, 2), "max_consecutive_losses": max_consecutive_losses,
        "exposure_pct": exposure_pct, "yearly": yearly
    }

def main():
    if not mt5.initialize():
        print("MT5 Failed")
        sys.exit(1)

    start_dt = datetime(2020, 1, 1, tzinfo=timezone.utc)
    end_dt = datetime(2026, 8, 28, 23, 59, tzinfo=timezone.utc)

    symbols = ["XAUUSD", "EURUSD", "GBPUSD", "USDJPY"]
    strategies = [
        "Strategy_A_Breakout",
        "Strategy_B_Pullback_50",
        "Strategy_C_4H_Trend_Rider",
        "Strategy_D_SMC_Sweep_Reversal"
    ]

    print("="*105)
    print("      MULTI-STRATEGY QUANTITATIVE TOURNAMENT (2020 - 2026 FULL HISTORICAL BENCHMARK)")
    print("="*105)

    all_data = {}
    for sym in symbols:
        r1, r4 = load_data(sym, start_dt, end_dt)
        is_sh, is_sl = precompute_swings(r1)
        all_data[sym] = (r1, r4, is_sh, is_sl)
        print(f"Precomputed {sym}: {len(r1)} 1H bars, {len(r4)} 4H bars.")

    benchmark_matrix = {}

    for strat in strategies:
        strat_results = {}
        strat_tot_trades = 0
        strat_tot_wins = 0
        strat_tot_pnl = 0.0
        strat_tot_gp = 0.0
        strat_tot_gl = 0.0

        for sym in symbols:
            r1, r4, is_sh, is_sl = all_data[sym]
            res = run_strategy_backtest(sym, r1, r4, is_sh, is_sl, strat, start_dt, end_dt)
            strat_results[sym] = res
            strat_tot_trades += res['trades']
            strat_tot_wins += res['wins']
            strat_tot_pnl += res['net_pnl']
            strat_tot_gp += res['gross_profit']
            strat_tot_gl += res['gross_loss']

        port_wr = round((strat_tot_wins / strat_tot_trades) * 100, 2) if strat_tot_trades > 0 else 0.0
        port_pf = round(strat_tot_gp / strat_tot_gl, 2) if strat_tot_gl > 0 else 0.0

        benchmark_matrix[strat] = {
            "assets": strat_results,
            "total_trades": strat_tot_trades,
            "win_rate": port_wr,
            "net_pnl": round(strat_tot_pnl, 2),
            "profit_factor": port_pf,
            "gross_profit": round(strat_tot_gp, 2),
            "gross_loss": round(strat_tot_gl, 2)
        }

    print("\n" + "="*105)
    print(f"{'Strategy Name':30s} | {'Trds':5s} | {'Win%':6s} | {'Portfolio Net P&L':19s} | {'PF':5s} | {'Best Asset':10s} | {'Worst Asset':10s}")
    print("-" * 105)

    for strat, data in benchmark_matrix.items():
        best_sym = max(data['assets'].items(), key=lambda x: x[1]['net_pnl'])[0]
        worst_sym = min(data['assets'].items(), key=lambda x: x[1]['net_pnl'])[0]
        pnl_str = f"${data['net_pnl']:+,.2f}"
        print(f"{strat:30s} | {data['total_trades']:5d} | {data['win_rate']:5.1f}% | {pnl_str:19s} | {data['profit_factor']:5.2f} | {best_sym:10s} | {worst_sym:10s}")

    print("="*105)

    out_path = r"d:\Techwaves-egy\Trading Team Skills\journal\strategy_tournament_2020_2026.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(benchmark_matrix, f, indent=2, default=str)
    print(f"\nFull Tournament Benchmark saved to: {out_path}")

    mt5.shutdown()

if __name__ == "__main__":
    main()
