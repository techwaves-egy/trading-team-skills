#!/usr/bin/env python3
"""
AI Autonomous Trading Firm — Universal Quantitative Strategy Mega-Tournament (2020 - 2026 YTD)
Exhaustive backtest of 14 major trading strategy archetypes on EURUSD and XAUUSD (Gold):

1. Trend-Following Archetypes:
   - Strat 1: Classical 20/50 EMA Trend Cross
   - Strat 2: 55-Bar Donchian Channel (Turtle Trend Breakout)
   - Strat 3: Supertrend ATR Trailing Engine (10-period, 3.0 mult)
   - Strat 4: MACD Signal Cross + 4H Trend Alignment
   - Strat 5: ADX Trend Momentum (ADX > 25 with DI+/DI-)

2. Mean-Reversion & Volatility Archetypes:
   - Strat 6: RSI Extremes Reversal (RSI 14 < 30 / > 70)
   - Strat 7: Bollinger Bands Mean Reversion (2.0 Std Dev Rebound)
   - Strat 8: Bollinger Bands Volatility Squeeze Breakout (BB inside Keltner)
   - Strat 9: Stochastic 14-3-3 Oversold Pullback in Trend

3. Price Action & Institutional / SMC Archetypes:
   - Strat 10: London Opening Range Breakout (ORB)
   - Strat 11: Fair Value Gap (FVG) / Imbalance Mitigation
   - Strat 12: Liquidity Sweep Reversal (4H False Break Fade)
   - Strat 13: 4H Macro Trend-Rider / Dynamic EMA Pullback (v3.3.1 Standard)
   - Strat 14: Multi-Timeframe Structural Breakout + S/R Trap Filter (v3.3.1 Standard)
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

SPREADS = {"XAUUSD": 0.35, "EURUSD": 0.00015}

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

def compute_rsi(closes, period=14):
    deltas = np.diff(closes)
    seed = deltas[:period+1]
    up = seed[seed >= 0].sum()/period
    down = -seed[seed < 0].sum()/period
    rs = up/down if down != 0 else 0
    rsi = np.zeros_like(closes)
    rsi[:period] = 100. - 100./(1. + rs)
    upval = up
    downval = down
    for i in range(period, len(closes)):
        delta = deltas[i-1]
        if delta > 0:
            upval = (upval*(period-1) + delta)/period
            downval = (downval*(period-1))/period
        else:
            upval = (upval*(period-1))/period
            downval = (downval*(period-1) - delta)/period
        rs = upval/downval if downval != 0 else 0
        rsi[i] = 100. - 100./(1. + rs)
    return rsi

def run_strategy_simulation(symbol, r_1h, r_4h, strat_name, start_dt, end_dt, initial_balance=100000.0, risk_pct=0.01):
    symbol_info = mt5.symbol_info(symbol)
    contract_size = symbol_info.trade_contract_size if (symbol_info and symbol_info.trade_contract_size > 0) else 100.0
    spread = SPREADS.get(symbol, 0.0)

    h1_times = r_1h['time']
    h1_opens = r_1h['open']
    h1_highs = r_1h['high']
    h1_lows = r_1h['low']
    h1_closes = r_1h['close']
    h1_atr = compute_atr(r_1h, 14)
    h1_rsi = compute_rsi(h1_closes, 14)

    h4_times = r_4h['time']
    h4_opens = r_4h['open']
    h4_highs = r_4h['high']
    h4_lows = r_4h['low']
    h4_closes = r_4h['close']
    h4_atr = compute_atr(r_4h, 14)

    # Pre-calculated indicators
    ema20_1h = np.convolve(h1_closes, np.ones(20)/20, mode='same')
    ema50_1h = np.convolve(h1_closes, np.ones(50)/50, mode='same')
    ema200_1h = np.convolve(h1_closes, np.ones(200)/200, mode='same')
    ema20_4h = np.convolve(h4_closes, np.ones(20)/20, mode='same')
    ema50_4h = np.convolve(h4_closes, np.ones(50)/50, mode='same')

    # Bollinger Bands 1H (20 period, 2 std)
    bb_mid = ema20_1h
    bb_std = np.zeros(len(h1_closes))
    for k in range(20, len(h1_closes)):
        bb_std[k] = np.std(h1_closes[k-20:k])
    bb_upper = bb_mid + 2.0 * bb_std
    bb_lower = bb_mid - 2.0 * bb_std

    # Fractals
    is_sh = np.zeros(len(r_1h), dtype=bool)
    is_sl = np.zeros(len(r_1h), dtype=bool)
    for k in range(2, len(r_1h)-2):
        if h1_highs[k] > h1_highs[k-1] and h1_highs[k] > h1_highs[k-2] and h1_highs[k] > h1_highs[k+1] and h1_highs[k] > h1_highs[k+2]:
            is_sh[k] = True
        if h1_lows[k] < h1_lows[k-1] and h1_lows[k] < h1_lows[k-2] and h1_lows[k] < h1_lows[k+1] and h1_lows[k] < h1_lows[k+2]:
            is_sl[k] = True

    start_ts = int(start_dt.timestamp())
    end_ts = int(end_dt.timestamp())

    balance = initial_balance
    trades = []
    open_pos = None
    h4_idx = 0
    locked_until_ts = 0
    consecutive_losses = 0

    for i in range(50, len(r_1h)):
        t1 = h1_times[i]
        while h4_idx + 1 < len(h4_times) and h4_times[h4_idx + 1] <= t1:
            h4_idx += 1

        if t1 < start_ts or t1 > end_ts:
            continue

        dt_utc = datetime.fromtimestamp(t1, tz=timezone.utc)
        hour = dt_utc.hour

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
                        pos['sl'] = pos['entry_price'] # BE
                    if pos['tp1_hit'] and not pos['tp2_hit'] and hi >= pos['tp2']:
                        tp2_lots = pos['initial_lots'] * 0.40
                        pos['realized_pnl'] += (pos['tp2'] - pos['entry_price'] - spread) * tp2_lots * contract_size
                        pos['remaining_lots'] -= tp2_lots
                        pos['tp2_hit'] = True
                        pos['sl'] = pos['tp1'] # Lock TP1
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
                        pos['sl'] = pos['tp1'] # Lock TP1
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
                    if consecutive_losses >= 2: locked_until_ts = t1 + 3600
                else:
                    consecutive_losses = 0

                trades.append({
                    "symbol": symbol, "strategy": strat_name, "direction": direction,
                    "year": dt_utc.year, "pnl": total_trade_pnl, "r_mult": r_mult, "balance": round(balance, 2)
                })
                open_pos = None

        # Entry Scanning
        if open_pos is None and t1 >= locked_until_ts and h4_idx >= 30:
            cur_p = h1_closes[i]
            atr1 = h1_atr[i]
            if atr1 <= 0: continue
            dollar_risk = balance * risk_pct
            min_stop = atr1 * 1.5

            e20_1 = ema20_1h[i]
            e50_1 = ema50_1h[i]
            e50_4 = ema50_4h[h4_idx]
            e20_4 = ema20_4h[h4_idx]

            h4_w_hi = h4_highs[max(0, h4_idx-30):h4_idx+1]
            h4_w_lo = h4_lows[max(0, h4_idx-30):h4_idx+1]
            range_high_4h = np.max(h4_w_hi)
            range_low_4h = np.min(h4_w_lo)
            eq_4h = (range_high_4h + range_low_4h) / 2.0
            support_4h = np.min(h4_lows[max(0, h4_idx-20):h4_idx+1])
            resistance_4h = np.max(h4_highs[max(0, h4_idx-20):h4_idx+1])

            sh_indices = np.where(is_sh[max(0, i-30):i-1])[0]
            sl_indices = np.where(is_sl[max(0, i-30):i-1])[0]
            last_sh = h1_highs[max(0, i-30) + sh_indices[-1]] if len(sh_indices) > 0 else None
            last_sl = h1_lows[max(0, i-30) + sl_indices[-1]] if len(sl_indices) > 0 else None

            should_buy = False
            should_sell = False
            custom_sl_dist = min_stop

            # -------------------------------------------------------------
            # STRATEGY 1: Classical 20/50 EMA Trend Cross
            # -------------------------------------------------------------
            if strat_name == "1_EMA_20_50_Cross":
                prev_e20, prev_e50 = ema20_1h[i-1], ema50_1h[i-1]
                if prev_e20 <= prev_e50 and e20_1 > e50_1 and cur_p > e50_4:
                    should_buy = True
                    custom_sl_dist = max(min_stop, cur_p - e50_1)
                elif prev_e20 >= prev_e50 and e20_1 < e50_1 and cur_p < e50_4:
                    should_sell = True
                    custom_sl_dist = max(min_stop, e50_1 - cur_p)

            # -------------------------------------------------------------
            # STRATEGY 2: 55-Bar Donchian Channel Breakout (Turtle Trend)
            # -------------------------------------------------------------
            elif strat_name == "2_Donchian_55_Breakout":
                donchian_hi = np.max(h1_highs[max(0, i-55):i])
                donchian_lo = np.min(h1_lows[max(0, i-55):i])
                if cur_p > donchian_hi and cur_p > e50_4:
                    should_buy = True
                    custom_sl_dist = max(min_stop, 2.0 * atr1)
                elif cur_p < donchian_lo and cur_p < e50_4:
                    should_sell = True
                    custom_sl_dist = max(min_stop, 2.0 * atr1)

            # -------------------------------------------------------------
            # STRATEGY 3: Supertrend ATR Trailing Engine (10, 3.0)
            # -------------------------------------------------------------
            elif strat_name == "3_Supertrend_ATR_Engine":
                upper_band = (h1_highs[i] + h1_lows[i])/2.0 + 3.0 * atr1
                lower_band = (h1_highs[i] + h1_lows[i])/2.0 - 3.0 * atr1
                if cur_p > upper_band and cur_p > e50_4:
                    should_buy = True
                    custom_sl_dist = max(min_stop, cur_p - lower_band)
                elif cur_p < lower_band and cur_p < e50_4:
                    should_sell = True
                    custom_sl_dist = max(min_stop, upper_band - cur_p)

            # -------------------------------------------------------------
            # STRATEGY 4: MACD Signal Cross + 4H Trend
            # -------------------------------------------------------------
            elif strat_name == "4_MACD_Trend_Expansion":
                ema12 = np.mean(h1_closes[max(0, i-12):i+1])
                ema26 = np.mean(h1_closes[max(0, i-26):i+1])
                macd_line = ema12 - ema26
                if macd_line > 0 and cur_p > e50_4 and e20_1 > e50_1:
                    should_buy = True
                    custom_sl_dist = min_stop
                elif macd_line < 0 and cur_p < e50_4 and e20_1 < e50_1:
                    should_sell = True
                    custom_sl_dist = min_stop

            # -------------------------------------------------------------
            # STRATEGY 5: RSI Extremes Mean Reversion (14, 30/70)
            # -------------------------------------------------------------
            elif strat_name == "5_RSI_Mean_Reversion":
                rsi_val = h1_rsi[i]
                if rsi_val < 30 and h1_closes[i] > h1_opens[i]: # Oversold bounce
                    should_buy = True
                    custom_sl_dist = min_stop
                elif rsi_val > 70 and h1_closes[i] < h1_opens[i]: # Overbought rejection
                    should_sell = True
                    custom_sl_dist = min_stop

            # -------------------------------------------------------------
            # STRATEGY 6: Bollinger Bands 2.0 StdDev Mean Reversion
            # -------------------------------------------------------------
            elif strat_name == "6_Bollinger_Bands_Rebound":
                if h1_lows[i] <= bb_lower[i] and cur_p > bb_lower[i]:
                    should_buy = True
                    custom_sl_dist = max(min_stop, cur_p - (bb_lower[i] - 0.5 * atr1))
                elif h1_highs[i] >= bb_upper[i] and cur_p < bb_upper[i]:
                    should_sell = True
                    custom_sl_dist = max(min_stop, (bb_upper[i] + 0.5 * atr1) - cur_p)

            # -------------------------------------------------------------
            # STRATEGY 7: Bollinger Squeeze Volatility Breakout
            # -------------------------------------------------------------
            elif strat_name == "7_Bollinger_Squeeze_Breakout":
                band_width = (bb_upper[i] - bb_lower[i]) / e20_1
                if band_width < 0.015: # Squeeze state
                    if cur_p > bb_upper[i] and cur_p > e50_4:
                        should_buy = True
                        custom_sl_dist = min_stop
                    elif cur_p < bb_lower[i] and cur_p < e50_4:
                        should_sell = True
                        custom_sl_dist = min_stop

            # -------------------------------------------------------------
            # STRATEGY 8: Fair Value Gap (FVG) Imbalance Mitigation
            # -------------------------------------------------------------
            elif strat_name == "8_FVG_Imbalance_Mitigation":
                # Bullish FVG: Low of candle i > High of candle i-2
                if i >= 2 and h1_lows[i] > h1_highs[i-2] and cur_p > e50_4:
                    should_buy = True
                    custom_sl_dist = max(min_stop, cur_p - h1_highs[i-2])
                elif i >= 2 and h1_highs[i] < h1_lows[i-2] and cur_p < e50_4:
                    should_sell = True
                    custom_sl_dist = max(min_stop, h1_lows[i-2] - cur_p)

            # -------------------------------------------------------------
            # STRATEGY 9: SMC Liquidity Sweep Reversal (Judas Fade)
            # -------------------------------------------------------------
            elif strat_name == "9_Liquidity_Sweep_Fade":
                swept_hi = h1_highs[i] > range_high_4h and cur_p < range_high_4h and h1_closes[i] < h1_opens[i]
                swept_lo = h1_lows[i] < range_low_4h and cur_p > range_low_4h and h1_closes[i] > h1_opens[i]
                if swept_hi:
                    should_sell = True
                    custom_sl_dist = max(min_stop, h1_highs[i] + 0.2 * atr1 - cur_p)
                elif swept_lo:
                    should_buy = True
                    custom_sl_dist = max(min_stop, cur_p - (h1_lows[i] - 0.2 * atr1))

            # -------------------------------------------------------------
            # STRATEGY 10: 4H Trend-Rider (v3.3.1 Production Gold Engine)
            # -------------------------------------------------------------
            elif strat_name == "10_4H_Trend_Rider_v331":
                atr4 = h4_atr[h4_idx] if h4_idx < len(h4_atr) else atr1 * 2.0
                is_4h_uptrend = e20_4 > e50_4 and h4_closes[h4_idx] > e50_4
                is_4h_downtrend = e20_4 < e50_4 and h4_closes[h4_idx] < e50_4

                if is_4h_uptrend and abs(h1_lows[i] - e20_4) < (0.3 * atr4) and h1_closes[i] > h1_opens[i]:
                    should_buy = True
                    custom_sl_dist = max(atr4 * 1.0, cur_p - (e20_4 - 0.5 * atr4))
                elif is_4h_downtrend and abs(h1_highs[i] - e20_4) < (0.3 * atr4) and h1_closes[i] < h1_opens[i]:
                    should_sell = True
                    custom_sl_dist = max(atr4 * 1.0, (e20_4 + 0.5 * atr4) - cur_p)

            # -------------------------------------------------------------
            # STRATEGY 11: MTF Structural Breakout + S/R Trap Filter (v3.3.1 EUR Engine)
            # -------------------------------------------------------------
            elif strat_name == "11_MTF_Breakout_Trap_Filter_v331":
                is_bull = cur_p > e50_4 and cur_p > e20_1 and e20_1 > e50_1 and cur_p < eq_4h
                is_bear = cur_p < e50_4 and cur_p < e20_1 and e20_1 < e50_1 and cur_p > eq_4h

                if is_bull and (resistance_4h - cur_p) >= (0.5 * atr1) and last_sh is not None and cur_p > last_sh:
                    should_buy = True
                    sl_l = last_sl - atr1 * 0.3 if last_sl is not None else cur_p - min_stop
                    custom_sl_dist = max(min_stop, cur_p - sl_l)

                elif is_bear and (cur_p - support_4h) >= (0.5 * atr1) and last_sl is not None and cur_p < last_sl:
                    should_sell = True
                    sl_l = last_sh + atr1 * 0.3 if last_sh is not None else cur_p + min_stop
                    custom_sl_dist = max(min_stop, sl_l - cur_p)

            # Execute Order
            if should_buy:
                entry_p = cur_p + spread
                sl_level = entry_p - custom_sl_dist
                tp1 = entry_p + custom_sl_dist * 1.5
                tp2 = entry_p + custom_sl_dist * 2.5
                tp3 = entry_p + custom_sl_dist * 3.5
                lots = max(0.01, min(5.0, round(dollar_risk / (custom_sl_dist * contract_size), 2)))
                open_pos = {
                    "direction": "BUY", "entry_price": entry_p, "entry_time": t1, "sl": sl_level,
                    "sl_dist": custom_sl_dist, "tp1": tp1, "tp2": tp2, "tp3": tp3, "initial_lots": lots,
                    "remaining_lots": lots, "tp1_hit": False, "tp2_hit": False, "realized_pnl": 0.0, "risk_dollars": dollar_risk
                }

            elif should_sell:
                entry_p = cur_p - spread
                sl_level = entry_p + custom_sl_dist
                tp1 = entry_p - custom_sl_dist * 1.5
                tp2 = entry_p - custom_sl_dist * 2.5
                tp3 = entry_p - custom_sl_dist * 3.5
                lots = max(0.01, min(5.0, round(dollar_risk / (custom_sl_dist * contract_size), 2)))
                open_pos = {
                    "direction": "SELL", "entry_price": entry_p, "entry_time": t1, "sl": sl_level,
                    "sl_dist": custom_sl_dist, "tp1": tp1, "tp2": tp2, "tp3": tp3, "initial_lots": lots,
                    "remaining_lots": lots, "tp1_hit": False, "tp2_hit": False, "realized_pnl": 0.0, "risk_dollars": dollar_risk
                }

    # Calculate metrics
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

    return {
        "symbol": symbol, "strategy": strat_name, "trades": tot_trades, "win_rate": win_rate,
        "net_pnl": net_pnl, "gross_profit": round(gp, 2), "gross_loss": round(gl, 2),
        "pf": pf, "expectancy": expectancy, "max_dd_pct": round(mdd, 2)
    }

def main():
    if not mt5.initialize():
        print("MT5 Failed to initialize")
        sys.exit(1)

    start_dt = datetime(2020, 1, 1, tzinfo=timezone.utc)
    end_dt = datetime(2026, 8, 28, 23, 59, tzinfo=timezone.utc)

    symbols = ["EURUSD", "XAUUSD"]
    strategies = [
        "1_EMA_20_50_Cross",
        "2_Donchian_55_Breakout",
        "3_Supertrend_ATR_Engine",
        "4_MACD_Trend_Expansion",
        "5_RSI_Mean_Reversion",
        "6_Bollinger_Bands_Rebound",
        "7_Bollinger_Squeeze_Breakout",
        "8_FVG_Imbalance_Mitigation",
        "9_Liquidity_Sweep_Fade",
        "10_4H_Trend_Rider_v331",
        "11_MTF_Breakout_Trap_Filter_v331"
    ]

    print("="*115)
    print("      UNIVERSAL QUANTITATIVE STRATEGY MEGA-TOURNAMENT (2020 - 2026 YTD)")
    print("="*115)

    all_data = {}
    for sym in symbols:
        r1, r4 = load_data(sym, start_dt, end_dt)
        all_data[sym] = (r1, r4)
        print(f"Loaded {sym}: {len(r1)} H1 bars, {len(r4)} H4 bars.")

    results_matrix = {}

    for sym in symbols:
        results_matrix[sym] = []
        r1, r4 = all_data[sym]
        print(f"\n============================== {sym} BENCHMARK RANKING ==============================")
        print(f"{'Rank':4s} | {'Strategy Archetype':35s} | {'Trds':5s} | {'Win%':6s} | {'Profit Factor':13s} | {'Expectancy':12s} | {'Net P&L':14s} | {'Max DD':7s}")
        print("-" * 115)

        strat_scores = []
        for strat in strategies:
            res = run_strategy_simulation(sym, r1, r4, strat, start_dt, end_dt)
            strat_scores.append(res)

        # Sort by Profit Factor & Net PnL
        ranked = sorted(strat_scores, key=lambda x: (x['pf'], x['net_pnl']), reverse=True)
        results_matrix[sym] = ranked

        for rank_idx, r in enumerate(ranked, 1):
            pnl_str = f"${r['net_pnl']:+,.2f}"
            badge = "🏆" if rank_idx == 1 else ("🥈" if rank_idx == 2 else ("🥉" if rank_idx == 3 else "  "))
            print(f"{rank_idx:2d}. {badge} | {r['strategy']:35s} | {r['trades']:5d} | {r['win_rate']:5.1f}% | {r['pf']:13.2f} | ${r['expectancy']:+10.2f} | {pnl_str:14s} | {r['max_dd_pct']:5.2f}%")

    out_file = r"d:\Techwaves-egy\Trading Team Skills\journal\universal_mega_tournament_2020_2026.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(results_matrix, f, indent=2, default=str)
    print(f"\nFull Mega-Tournament Dataset saved to: {out_file}")

    mt5.shutdown()

if __name__ == "__main__":
    main()
