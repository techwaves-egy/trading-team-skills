#!/usr/bin/env python3
"""
AI Autonomous Trading Firm — Institutional Backtest Engine (v3.1.0)
Simulates exact multi-timeframe regime detection, S/R trap filtering,
true 1H fractal swing CHoCH confirmation, 1.5x ATR stop floor,
3-tier scale-out management (40/40/20), 2-strike lockout, and anti-stacking.

Period: 2025-01-01 to 2025-12-31
"""

import sys
import os
import json
import math
from datetime import datetime, timezone, timedelta
import numpy as np

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import MetaTrader5 as mt5

def load_rates(symbol, start_dt, end_dt):
    """Fetch M15, H1, H4 rates from MT5 with warm-up lookback"""
    # Fetch with 200 bars warm-up prior to 2025
    warmup_start = start_dt - timedelta(days=40)
    
    r_m15 = mt5.copy_rates_range(symbol, mt5.TIMEFRAME_M15, warmup_start, end_dt)
    r_h1 = mt5.copy_rates_range(symbol, mt5.TIMEFRAME_H1, warmup_start, end_dt)
    r_h4 = mt5.copy_rates_range(symbol, mt5.TIMEFRAME_H4, warmup_start, end_dt)
    
    return r_m15, r_h1, r_h4

def compute_atr(rates, period=14):
    """Compute ATR array"""
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

def run_backtest_symbol(symbol, start_dt, end_dt, initial_balance=100000.0, risk_per_trade_dollars=10.0, mode="fixed"):
    """
    Run bar-by-bar backtest on a single symbol across 2025 using M15 execution bars
    and multi-timeframe H1/H4 indicators.
    """
    print(f"\n=======================================================")
    print(f"  RUNNING v3.1.0 BACKTEST: {symbol} (Full Year 2025)")
    print(f"=======================================================")
    
    r_m15, r_h1, r_h4 = load_rates(symbol, start_dt, end_dt)
    if r_m15 is None or len(r_m15) == 0:
        print(f"Error: No M15 data for {symbol}")
        return None

    symbol_info = mt5.symbol_info(symbol)
    contract_size = symbol_info.trade_contract_size if (symbol_info and symbol_info.trade_contract_size > 0) else 100.0
    point = symbol_info.point if symbol_info else 0.01

    # Pre-calculate H1 metrics
    h1_times = r_h1['time']
    h1_closes = r_h1['close']
    h1_highs = r_h1['high']
    h1_lows = r_h1['low']
    h1_atr = compute_atr(r_h1, 14)
    
    # Pre-calculate H4 metrics
    h4_times = r_h4['time']
    h4_closes = r_h4['close']
    h4_highs = r_h4['high']
    h4_lows = r_h4['low']

    # State tracking
    balance = initial_balance
    peak_balance = initial_balance
    equity_curve = []
    trades = []
    open_position = None # Anti-stacking
    consecutive_losses = 0
    locked_until_time = 0

    start_ts = int(start_dt.timestamp())
    end_ts = int(end_dt.timestamp())

    # Map M15 bars to H1 and H4 index
    h1_idx = 0
    h4_idx = 0

    for m_idx in range(len(r_m15)):
        m_bar = r_m15[m_idx]
        m_time = m_bar['time']
        
        # Advance H1 index
        while h1_idx + 1 < len(h1_times) and h1_times[h1_idx + 1] <= m_time:
            h1_idx += 1
            
        # Advance H4 index
        while h4_idx + 1 < len(h4_times) and h4_times[h4_idx + 1] <= m_time:
            h4_idx += 1

        # Check if within 2025 evaluation window
        if m_time < start_ts or m_time > end_ts:
            continue

        # --- 1. MANAGE OPEN POSITION (If any) ---
        if open_position is not None:
            pos = open_position
            direction = pos['direction']
            high_price = m_bar['high']
            low_price = m_bar['low']
            close_price = m_bar['close']
            
            # Check Stop Loss & Take Profit milestones
            is_closed = False
            exit_reason = ""
            exit_price = 0.0
            pnl = 0.0

            if direction == "BUY":
                # Check SL hit
                if low_price <= pos['sl']:
                    exit_price = pos['sl']
                    exit_reason = "STOP_LOSS"
                    pnl = (exit_price - pos['entry_price']) * pos['remaining_lots'] * contract_size
                    is_closed = True
                else:
                    # Check TP1 (40% close + Move SL to Break-Even)
                    if not pos['tp1_hit'] and high_price >= pos['tp1']:
                        tp1_lots = pos['initial_lots'] * 0.40
                        realized_tp1 = (pos['tp1'] - pos['entry_price']) * tp1_lots * contract_size
                        pos['realized_pnl'] += realized_tp1
                        pos['remaining_lots'] -= tp1_lots
                        pos['tp1_hit'] = True
                        pos['sl'] = pos['entry_price'] # Move to Break-Even
                        
                    # Check TP2 (40% close + Lock in TP1)
                    if pos['tp1_hit'] and not pos['tp2_hit'] and high_price >= pos['tp2']:
                        tp2_lots = pos['initial_lots'] * 0.40
                        realized_tp2 = (pos['tp2'] - pos['entry_price']) * tp2_lots * contract_size
                        pos['realized_pnl'] += realized_tp2
                        pos['remaining_lots'] -= tp2_lots
                        pos['tp2_hit'] = True
                        pos['sl'] = pos['tp1'] # Lock profit at TP1
                        
                    # Check TP3 (Remaining 20% runner)
                    if pos['tp2_hit'] and high_price >= pos['tp3']:
                        tp3_lots = pos['remaining_lots']
                        realized_tp3 = (pos['tp3'] - pos['entry_price']) * tp3_lots * contract_size
                        pos['realized_pnl'] += realized_tp3
                        pos['remaining_lots'] = 0.0
                        exit_price = pos['tp3']
                        exit_reason = "FULL_TP3_RUNNER"
                        pnl = 0.0 # already in realized_pnl
                        is_closed = True

            elif direction == "SELL":
                # Check SL hit
                if high_price >= pos['sl']:
                    exit_price = pos['sl']
                    exit_reason = "STOP_LOSS"
                    pnl = (pos['entry_price'] - exit_price) * pos['remaining_lots'] * contract_size
                    is_closed = True
                else:
                    # Check TP1 (40% close + Move SL to Break-Even)
                    if not pos['tp1_hit'] and low_price <= pos['tp1']:
                        tp1_lots = pos['initial_lots'] * 0.40
                        realized_tp1 = (pos['entry_price'] - pos['tp1']) * tp1_lots * contract_size
                        pos['realized_pnl'] += realized_tp1
                        pos['remaining_lots'] -= tp1_lots
                        pos['tp1_hit'] = True
                        pos['sl'] = pos['entry_price'] # Move to Break-Even
                        
                    # Check TP2 (40% close + Lock in TP1)
                    if pos['tp1_hit'] and not pos['tp2_hit'] and low_price <= pos['tp2']:
                        tp2_lots = pos['initial_lots'] * 0.40
                        realized_tp2 = (pos['entry_price'] - pos['tp2']) * tp2_lots * contract_size
                        pos['realized_pnl'] += realized_tp2
                        pos['remaining_lots'] -= tp2_lots
                        pos['tp2_hit'] = True
                        pos['sl'] = pos['tp1'] # Lock profit at TP1
                        
                    # Check TP3 (Remaining 20% runner)
                    if pos['tp2_hit'] and low_price <= pos['tp3']:
                        tp3_lots = pos['remaining_lots']
                        realized_tp3 = (pos['entry_price'] - pos['tp3']) * tp3_lots * contract_size
                        pos['realized_pnl'] += realized_tp3
                        pos['remaining_lots'] = 0.0
                        exit_price = pos['tp3']
                        exit_reason = "FULL_TP3_RUNNER"
                        pnl = 0.0
                        is_closed = True

            if is_closed:
                total_trade_pnl = round(pos['realized_pnl'] + pnl, 2)
                balance += total_trade_pnl
                peak_balance = max(peak_balance, balance)
                
                # Lockout logic
                if total_trade_pnl < 0:
                    consecutive_losses += 1
                    if consecutive_losses >= 2:
                        locked_until_time = m_time + 3600 # 60 min freeze
                else:
                    consecutive_losses = 0

                trades.append({
                    "id": len(trades) + 1,
                    "symbol": symbol,
                    "direction": direction,
                    "entry_time": datetime.fromtimestamp(pos['entry_time'], tz=timezone.utc).strftime("%Y-%m-%d %H:%M"),
                    "exit_time": datetime.fromtimestamp(m_time, tz=timezone.utc).strftime("%Y-%m-%d %H:%M"),
                    "entry_price": pos['entry_price'],
                    "exit_price": exit_price,
                    "initial_lots": pos['initial_lots'],
                    "sl_distance": pos['sl_dist'],
                    "pnl": total_trade_pnl,
                    "exit_reason": exit_reason,
                    "balance_after": round(balance, 2)
                })
                open_position = None

        # --- 2. EVALUATE ENTRY GATES (If no open position) ---
        if open_position is None:
            # Gate 1: 2-Strike Lockout Check
            if m_time < locked_until_time:
                continue

            if h1_idx < 30 or h4_idx < 30:
                continue

            # Multi-Timeframe 4H Analysis
            c4 = h4_closes[max(0, h4_idx-50):h4_idx+1]
            h4_sub = h4_highs[max(0, h4_idx-30):h4_idx+1]
            l4_sub = h4_lows[max(0, h4_idx-30):h4_idx+1]
            ema50_4h = np.mean(c4[-50:]) if len(c4) >= 50 else np.mean(c4)
            range_high_4h = np.max(h4_sub)
            range_low_4h = np.min(l4_sub)
            eq_4h = (range_high_4h + range_low_4h) / 2.0
            
            # 1H Analysis
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
            
            is_premium = cur_price > eq_4h
            is_discount = cur_price < eq_4h

            regime = "RANGING"
            if is_4h_bull and is_1h_bull and (is_discount or cur_price > range_high_4h):
                regime = "UPTREND"
            elif is_4h_bear and is_1h_bear and (is_premium or cur_price < range_low_4h):
                regime = "DOWNTREND"

            if regime == "RANGING":
                continue

            # Gate 3: S/R Trap Filter
            support_4h = np.min(h4_lows[max(0, h4_idx-20):h4_idx+1])
            resistance_4h = np.max(h4_highs[max(0, h4_idx-20):h4_idx+1])
            
            if regime == "DOWNTREND" and (cur_price - support_4h) < (0.5 * atr_val):
                continue # Trap filter blocked selling into support floor
            if regime == "UPTREND" and (resistance_4h - cur_price) < (0.5 * atr_val):
                continue # Trap filter blocked buying into resistance ceiling

            # Gate 5: True 1H Fractal Swing CHoCH Check
            h1_rates_sub = r_h1[max(0, h1_idx-30):h1_idx+1]
            swing_highs = []
            swing_lows = []
            for i in range(2, len(h1_rates_sub) - 2):
                if h1_rates_sub[i]['high'] > h1_rates_sub[i-1]['high'] and h1_rates_sub[i]['high'] > h1_rates_sub[i-2]['high'] and \
                   h1_rates_sub[i]['high'] > h1_rates_sub[i+1]['high'] and h1_rates_sub[i]['high'] > h1_rates_sub[i+2]['high']:
                    swing_highs.append(h1_rates_sub[i]['high'])
                if h1_rates_sub[i]['low'] < h1_rates_sub[i-1]['low'] and h1_rates_sub[i]['low'] < h1_rates_sub[i-2]['low'] and \
                   h1_rates_sub[i]['low'] < h1_rates_sub[i+1]['low'] and h1_rates_sub[i]['low'] < h1_rates_sub[i+2]['low']:
                    swing_lows.append(h1_rates_sub[i]['low'])

            if regime == "UPTREND":
                if not swing_highs:
                    continue
                target_swing = swing_highs[-1]
                if cur_price > target_swing: # CHoCH Confirmed
                    # Compute SL & TPs
                    candidates = [l for l in swing_lows if l < cur_price]
                    sl_level = (max(candidates) - atr_val * 0.3) if candidates else (cur_price - min_stop)
                    sl_dist = cur_price - sl_level
                    if sl_dist < min_stop:
                        sl_level = cur_price - min_stop
                        sl_dist = min_stop
                    
                    tp1 = cur_price + sl_dist * 1.5
                    tp2 = cur_price + sl_dist * 2.5
                    tp3 = cur_price + sl_dist * 3.5

                    # Risk Sizing
                    if mode == "fixed":
                        lots = round(risk_per_trade_dollars / (sl_dist * contract_size), 2)
                        lots = max(0.01, min(0.10, lots))
                    else: # 1% compounding
                        dollar_risk = balance * 0.01
                        lots = round(dollar_risk / (sl_dist * contract_size), 2)
                        lots = max(0.01, min(5.0, lots))

                    open_position = {
                        "direction": "BUY",
                        "entry_price": cur_price,
                        "entry_time": m_time,
                        "sl": sl_level,
                        "sl_dist": sl_dist,
                        "tp1": tp1,
                        "tp2": tp2,
                        "tp3": tp3,
                        "initial_lots": lots,
                        "remaining_lots": lots,
                        "tp1_hit": False,
                        "tp2_hit": False,
                        "realized_pnl": 0.0
                    }

            elif regime == "DOWNTREND":
                if not swing_lows:
                    continue
                target_swing = swing_lows[-1]
                if cur_price < target_swing: # CHoCH Confirmed
                    # Compute SL & TPs
                    candidates = [h for h in swing_highs if h > cur_price]
                    sl_level = (min(candidates) + atr_val * 0.3) if candidates else (cur_price + min_stop)
                    sl_dist = sl_level - cur_price
                    if sl_dist < min_stop:
                        sl_level = cur_price + min_stop
                        sl_dist = min_stop
                    
                    tp1 = cur_price - sl_dist * 1.5
                    tp2 = cur_price - sl_dist * 2.5
                    tp3 = cur_price - sl_dist * 3.5

                    # Risk Sizing
                    if mode == "fixed":
                        lots = round(risk_per_trade_dollars / (sl_dist * contract_size), 2)
                        lots = max(0.01, min(0.10, lots))
                    else: # 1% compounding
                        dollar_risk = balance * 0.01
                        lots = round(dollar_risk / (sl_dist * contract_size), 2)
                        lots = max(0.01, min(5.0, lots))

                    open_position = {
                        "direction": "SELL",
                        "entry_price": cur_price,
                        "entry_time": m_time,
                        "sl": sl_level,
                        "sl_dist": sl_dist,
                        "tp1": tp1,
                        "tp2": tp2,
                        "tp3": tp3,
                        "initial_lots": lots,
                        "remaining_lots": lots,
                        "tp1_hit": False,
                        "tp2_hit": False,
                        "realized_pnl": 0.0
                    }

    # Close any lingering position at the end of the year
    if open_position is not None:
        pos = open_position
        cur_p = r_m15[-1]['close']
        if pos['direction'] == "BUY":
            pnl = (cur_p - pos['entry_price']) * pos['remaining_lots'] * contract_size
        else:
            pnl = (pos['entry_price'] - cur_p) * pos['remaining_lots'] * contract_size
        total_pnl = round(pos['realized_pnl'] + pnl, 2)
        balance += total_pnl
        trades.append({
            "id": len(trades) + 1,
            "symbol": symbol,
            "direction": pos['direction'],
            "entry_time": datetime.fromtimestamp(pos['entry_time'], tz=timezone.utc).strftime("%Y-%m-%d %H:%M"),
            "exit_time": datetime.fromtimestamp(r_m15[-1]['time'], tz=timezone.utc).strftime("%Y-%m-%d %H:%M"),
            "entry_price": pos['entry_price'],
            "exit_price": cur_p,
            "initial_lots": pos['initial_lots'],
            "sl_distance": pos['sl_dist'],
            "pnl": total_pnl,
            "exit_reason": "END_OF_YEAR_CLOSE",
            "balance_after": round(balance, 2)
        })

    # Summary calculations
    total_trades = len(trades)
    wins = [t for t in trades if t['pnl'] > 0]
    losses = [t for t in trades if t['pnl'] < 0]
    be = [t for t in trades if t['pnl'] == 0]
    
    total_profit = sum([t['pnl'] for t in wins])
    total_loss = abs(sum([t['pnl'] for t in losses]))
    net_pnl = round(balance - initial_balance, 2)
    win_rate = round((len(wins) / total_trades) * 100, 2) if total_trades > 0 else 0.0
    profit_factor = round(total_profit / total_loss, 2) if total_loss > 0 else (99.0 if total_profit > 0 else 0.0)
    
    # Calculate Max Drawdown
    equity_series = [initial_balance]
    running_b = initial_balance
    for t in trades:
        running_b += t['pnl']
        equity_series.append(running_b)
    
    peak = equity_series[0]
    max_dd_dollars = 0.0
    max_dd_pct = 0.0
    for eq in equity_series:
        if eq > peak:
            peak = eq
        dd = peak - eq
        dd_pct = (dd / peak) * 100 if peak > 0 else 0
        if dd > max_dd_dollars:
            max_dd_dollars = dd
            max_dd_pct = dd_pct

    # Monthly breakdown
    monthly = {}
    for t in trades:
        month = t['entry_time'][:7] # YYYY-MM
        if month not in monthly:
            monthly[month] = {"trades": 0, "wins": 0, "losses": 0, "pnl": 0.0}
        monthly[month]["trades"] += 1
        if t['pnl'] > 0:
            monthly[month]["wins"] += 1
        elif t['pnl'] < 0:
            monthly[month]["losses"] += 1
        monthly[month]["pnl"] = round(monthly[month]["pnl"] + t['pnl'], 2)

    result = {
        "symbol": symbol,
        "initial_balance": initial_balance,
        "final_balance": round(balance, 2),
        "net_pnl": net_pnl,
        "return_pct": round((net_pnl / initial_balance) * 100, 2),
        "total_trades": total_trades,
        "wins": len(wins),
        "losses": len(losses),
        "breakeven": len(be),
        "win_rate": win_rate,
        "profit_factor": profit_factor,
        "gross_profit": round(total_profit, 2),
        "gross_loss": round(total_loss, 2),
        "max_drawdown_dollars": round(max_dd_dollars, 2),
        "max_drawdown_pct": round(max_dd_pct, 2),
        "monthly": monthly,
        "trades": trades
    }

    print(f"\n--- {symbol} 2025 BACKTEST RESULTS ---")
    print(f"Total Trades:    {total_trades}")
    print(f"Win Rate:        {win_rate}% ({len(wins)}W / {len(losses)}L / {len(be)}BE)")
    print(f"Net Profit:      ${net_pnl:+,.2f} ({result['return_pct']:+.2f}%)")
    print(f"Profit Factor:   {profit_factor}")
    print(f"Max Drawdown:    ${max_dd_dollars:,.2f} ({max_dd_pct:.2f}%)")
    print(f"Gross Profit:    +${total_profit:,.2f} | Gross Loss: -${total_loss:,.2f}")
    
    return result

def main():
    if not mt5.initialize():
        print("Failed to initialize MT5")
        sys.exit(1)

    start_2025 = datetime(2025, 1, 1, tzinfo=timezone.utc)
    end_2025 = datetime(2025, 12, 31, 23, 59, tzinfo=timezone.utc)

    # 1. Backtest Portfolio (Gold + Forex Majors) with institutional 1% risk
    symbols = ['XAUUSD', 'EURUSD', 'GBPUSD', 'USDJPY']
    all_results = {}

    for sym in symbols:
        res = run_backtest_symbol(sym, start_2025, end_2025, initial_balance=100000.0, mode="institutional")
        if res:
            all_results[sym] = res

    # Summary Portfolio Scorecard
    print("\n" + "="*70)
    print("      PORTFOLIO ANNUAL SUMMARY (2025 FULL YEAR BACKTEST)")
    print("="*70)
    
    tot_trades = sum([r['total_trades'] for r in all_results.values()])
    tot_wins = sum([r['wins'] for r in all_results.values()])
    tot_losses = sum([r['losses'] for r in all_results.values()])
    tot_pnl = sum([r['net_pnl'] for r in all_results.values()])
    tot_profit = sum([r['gross_profit'] for r in all_results.values()])
    tot_loss = sum([r['gross_loss'] for r in all_results.values()])
    port_pf = round(tot_profit / tot_loss, 2) if tot_loss > 0 else 99.0
    port_wr = round((tot_wins / tot_trades) * 100, 2) if tot_trades > 0 else 0.0

    print(f"Portfolio Net PnL:     ${tot_pnl:+,.2f}")
    print(f"Portfolio Total Trades: {tot_trades}")
    print(f"Portfolio Win Rate:     {port_wr}% ({tot_wins}W / {tot_losses}L)")
    print(f"Portfolio Profit Factor: {port_pf}")
    print(f"Gross Profit:          +${tot_profit:+,.2f} | Gross Loss: -${tot_loss:,.2f}")
    print("="*70)

    # Save complete backtest output
    report_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "journal", "backtest_2025_report.json")
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(all_results, f, indent=2, default=str)
    print(f"\nFull Backtest Report saved to: {report_path}")

    mt5.shutdown()

if __name__ == "__main__":
    main()
