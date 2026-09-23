import sys, json, os
from datetime import datetime, timezone, timedelta
import numpy as np
import MetaTrader5 as mt5

def load_rates(symbol, start_dt, end_dt):
    warmup_start = start_dt - timedelta(days=40)
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

def run_pullback_backtest(symbol, start_dt, end_dt):
    r_m15, r_h1, r_h4 = load_rates(symbol, start_dt, end_dt)
    symbol_info = mt5.symbol_info(symbol)
    contract_size = symbol_info.trade_contract_size if (symbol_info and symbol_info.trade_contract_size > 0) else 100.0
    
    h1_times, h1_closes, h1_highs, h1_lows = r_h1['time'], r_h1['close'], r_h1['high'], r_h1['low']
    h1_atr = compute_atr(r_h1, 14)
    h4_times, h4_closes, h4_highs, h4_lows = r_h4['time'], r_h4['close'], r_h4['high'], r_h4['low']

    balance = 100000.0
    initial_balance = 100000.0
    trades = []
    open_position = None
    pending_order = None # (direction, limit_price, sl, tp1, tp2, tp3, lots, expire_time)
    consecutive_losses = 0
    locked_until_time = 0

    start_ts = int(start_dt.timestamp())
    end_ts = int(end_dt.timestamp())
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

        # Check pending limit order fill
        if pending_order is not None and open_position is None:
            p_dir, p_price, p_sl, p_tp1, p_tp2, p_tp3, p_lots, p_exp = pending_order
            if m_time > p_exp:
                pending_order = None # expired
            else:
                filled = False
                if p_dir == "BUY" and m_bar['low'] <= p_price:
                    filled = True
                elif p_dir == "SELL" and m_bar['high'] >= p_price:
                    filled = True
                    
                if filled:
                    open_position = {
                        "direction": p_dir,
                        "entry_price": p_price,
                        "entry_time": m_time,
                        "sl": p_sl,
                        "sl_dist": abs(p_price - p_sl),
                        "tp1": p_tp1,
                        "tp2": p_tp2,
                        "tp3": p_tp3,
                        "initial_lots": p_lots,
                        "remaining_lots": p_lots,
                        "tp1_hit": False,
                        "tp2_hit": False,
                        "realized_pnl": 0.0
                    }
                    pending_order = None

        # Manage open position
        if open_position is not None:
            pos = open_position
            direction = pos['direction']
            high_price, low_price = m_bar['high'], m_bar['low']
            is_closed = False
            exit_reason, exit_price, pnl = "", 0.0, 0.0

            if direction == "BUY":
                if low_price <= pos['sl']:
                    exit_price, exit_reason = pos['sl'], "STOP_LOSS"
                    pnl = (exit_price - pos['entry_price']) * pos['remaining_lots'] * contract_size
                    is_closed = True
                else:
                    if not pos['tp1_hit'] and high_price >= pos['tp1']:
                        tp1_lots = pos['initial_lots'] * 0.40
                        pos['realized_pnl'] += (pos['tp1'] - pos['entry_price']) * tp1_lots * contract_size
                        pos['remaining_lots'] -= tp1_lots
                        pos['tp1_hit'] = True
                        pos['sl'] = pos['entry_price'] # BE
                    if pos['tp1_hit'] and not pos['tp2_hit'] and high_price >= pos['tp2']:
                        tp2_lots = pos['initial_lots'] * 0.40
                        pos['realized_pnl'] += (pos['tp2'] - pos['entry_price']) * tp2_lots * contract_size
                        pos['remaining_lots'] -= tp2_lots
                        pos['tp2_hit'] = True
                        pos['sl'] = pos['tp1'] # Lock profit
                    if pos['tp2_hit'] and high_price >= pos['tp3']:
                        tp3_lots = pos['remaining_lots']
                        pos['realized_pnl'] += (pos['tp3'] - pos['entry_price']) * tp3_lots * contract_size
                        pos['remaining_lots'] = 0.0
                        exit_price, exit_reason = pos['tp3'], "FULL_TP3_RUNNER"
                        pnl = 0.0
                        is_closed = True

            elif direction == "SELL":
                if high_price >= pos['sl']:
                    exit_price, exit_reason = pos['sl'], "STOP_LOSS"
                    pnl = (pos['entry_price'] - exit_price) * pos['remaining_lots'] * contract_size
                    is_closed = True
                else:
                    if not pos['tp1_hit'] and low_price <= pos['tp1']:
                        tp1_lots = pos['initial_lots'] * 0.40
                        pos['realized_pnl'] += (pos['entry_price'] - pos['tp1']) * tp1_lots * contract_size
                        pos['remaining_lots'] -= tp1_lots
                        pos['tp1_hit'] = True
                        pos['sl'] = pos['entry_price'] # BE
                    if pos['tp1_hit'] and not pos['tp2_hit'] and low_price <= pos['tp2']:
                        tp2_lots = pos['initial_lots'] * 0.40
                        pos['realized_pnl'] += (pos['entry_price'] - pos['tp2']) * tp2_lots * contract_size
                        pos['remaining_lots'] -= tp2_lots
                        pos['tp2_hit'] = True
                        pos['sl'] = pos['tp1'] # Lock profit
                    if pos['tp2_hit'] and low_price <= pos['tp3']:
                        tp3_lots = pos['remaining_lots']
                        pos['realized_pnl'] += (pos['entry_price'] - pos['tp3']) * tp3_lots * contract_size
                        pos['remaining_lots'] = 0.0
                        exit_price, exit_reason = pos['tp3'], "FULL_TP3_RUNNER"
                        pnl = 0.0
                        is_closed = True

            if is_closed:
                total_trade_pnl = round(pos['realized_pnl'] + pnl, 2)
                balance += total_trade_pnl
                trades.append({"symbol": symbol, "direction": direction, "pnl": total_trade_pnl})
                open_position = None

        # Entry Gate checks
        if open_position is None and pending_order is None and m_time >= locked_until_time:
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

            if is_4h_bull and is_1h_bull and cur_price < eq_4h: # UPTREND in Discount
                if (resistance_4h - cur_price) >= (0.5 * atr_val) and swing_highs:
                    if cur_price > swing_highs[-1]:
                        # Place limit order on 50% pullback towards 1H EMA20
                        entry_limit = round((cur_price + ema20_1h) / 2.0, 2)
                        candidates = [l for l in swing_lows if l < entry_limit]
                        sl_level = max(candidates) - atr_val * 0.3 if candidates else entry_limit - min_stop
                        sl_dist = entry_limit - sl_level
                        if sl_dist < min_stop:
                            sl_level = entry_limit - min_stop
                            sl_dist = min_stop
                        
                        tp1 = entry_limit + sl_dist * 1.5
                        tp2 = entry_limit + sl_dist * 2.5
                        tp3 = entry_limit + sl_dist * 3.5
                        lots = round((balance * 0.01) / (sl_dist * contract_size), 2)
                        lots = max(0.01, min(5.0, lots))
                        pending_order = ("BUY", entry_limit, sl_level, tp1, tp2, tp3, lots, m_time + 4 * 3600)

            elif is_4h_bear and is_1h_bear and cur_price > eq_4h: # DOWNTREND in Premium
                if (cur_price - support_4h) >= (0.5 * atr_val) and swing_lows:
                    if cur_price < swing_lows[-1]:
                        # Place limit order on 50% pullback towards 1H EMA20
                        entry_limit = round((cur_price + ema20_1h) / 2.0, 2)
                        candidates = [h for h in swing_highs if h > entry_limit]
                        sl_level = min(candidates) + atr_val * 0.3 if candidates else entry_limit + min_stop
                        sl_dist = sl_level - entry_limit
                        if sl_dist < min_stop:
                            sl_level = entry_limit + min_stop
                            sl_dist = min_stop
                        
                        tp1 = entry_limit - sl_dist * 1.5
                        tp2 = entry_limit - sl_dist * 2.5
                        tp3 = entry_limit - sl_dist * 3.5
                        lots = round((balance * 0.01) / (sl_dist * contract_size), 2)
                        lots = max(0.01, min(5.0, lots))
                        pending_order = ("SELL", entry_limit, sl_level, tp1, tp2, tp3, lots, m_time + 4 * 3600)

    # Compute metrics
    wins = [t for t in trades if t['pnl'] > 0]
    losses = [t for t in trades if t['pnl'] < 0]
    tot_pnl = sum([t['pnl'] for t in trades])
    wr = len(wins) / len(trades) * 100 if trades else 0
    gross_win = sum([t['pnl'] for t in wins])
    gross_loss = abs(sum([t['pnl'] for t in losses]))
    pf = round(gross_win / gross_loss, 2) if gross_loss > 0 else 99.0
    print(f"{symbol:7s} (Pullback Retest) | Trades: {len(trades):2d} | Win Rate: {wr:5.1f}% | Net PnL: ${tot_pnl:+9.2f} | PF: {pf:4.2f}")
    return {"symbol": symbol, "trades": len(trades), "win_rate": wr, "pnl": tot_pnl, "pf": pf}

if __name__ == "__main__":
    if not mt5.initialize():
        sys.exit(1)
    s = datetime(2025, 1, 1, tzinfo=timezone.utc)
    e = datetime(2025, 12, 31, 23, 59, tzinfo=timezone.utc)
    print("\n--- COMPARISON: v3.1.0 PULLBACK RETEST VARIANT (2025) ---")
    for sym in ['XAUUSD', 'EURUSD', 'GBPUSD', 'USDJPY']:
        run_pullback_backtest(sym, s, e)
    mt5.shutdown()
