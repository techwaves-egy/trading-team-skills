#!/usr/bin/env python3
import sys
import os
from datetime import datetime, timezone
import MetaTrader5 as mt5

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

def diagnose():
    if not mt5.initialize():
        print("MT5 Failed to initialize")
        return

    print("=" * 80)
    print(f"   LIVE MARKET & DECISION ENGINE AUDIT — {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")
    print("=" * 80)

    for sym in ["EURUSD", "XAUUSD"]:
        tick = mt5.symbol_info_tick(sym)
        r4 = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_H4, 0, 50)
        r1 = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_H1, 0, 50)
        r15 = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_M15, 0, 50)

        price = tick.bid if tick else 0.0
        c4 = [r['close'] for r in r4]
        h4 = [r['high'] for r in r4]
        l4 = [r['low'] for r in r4]
        ema50_4h = sum(c4[-50:]) / 50.0
        range_hi_4h = max(h4[-30:])
        range_lo_4h = min(l4[-30:])
        eq_4h = (range_hi_4h + range_lo_4h) / 2.0
        sup_4h = min(l4[-20:])
        res_4h = max(h4[-20:])

        c1 = [r['close'] for r in r1]
        ema20_1h = sum(c1[-20:]) / 20.0
        ema50_1h = sum(c1[-50:]) / 50.0

        # ATR 1H
        tr = [max(r1[i]['high']-r1[i]['low'], abs(r1[i]['high']-r1[i-1]['close']), abs(r1[i]['low']-r1[i-1]['close'])) for i in range(1, len(r1))]
        atr_1h = sum(tr[-14:]) / 14.0

        # Swings
        sh = [r1[k]['high'] for k in range(2, len(r1)-2) if r1[k]['high'] == max([r1[j]['high'] for j in range(k-2, k+3)])]
        sl = [r1[k]['low'] for k in range(2, len(r1)-2) if r1[k]['low'] == min([r1[j]['low'] for j in range(k-2, k+3)])]
        last_sh = sh[-1] if sh else None
        last_sl = sl[-1] if sl else None

        is_4h_bull = price > ema50_4h
        is_4h_bear = price < ema50_4h
        is_1h_bull = price > ema20_1h and ema20_1h > ema50_1h
        is_1h_bear = price < ema20_1h and ema20_1h < ema50_1h
        is_premium = price > eq_4h
        is_discount = price < eq_4h

        near_res = (res_4h - price) < (0.5 * atr_1h)
        near_sup = (price - sup_4h) < (0.5 * atr_1h)

        print(f"\n--- {sym} (Current Price: {price}) ---")
        print(f"1. 4H Macro Regime:")
        print(f"   • 4H 50 EMA: {ema50_4h:.4f} -> {'BULLISH' if is_4h_bull else 'BEARISH'}")
        print(f"   • 4H Range: [{range_lo_4h:.4f} to {range_hi_4h:.4f}] | 50% Equilibrium: {eq_4h:.4f}")
        print(f"   • Valuation Zone: {'PREMIUM (Sells allowed)' if is_premium else 'DISCOUNT (Buys allowed)'}")

        print(f"2. 1H Intermediary Trend:")
        print(f"   • 1H 20 EMA: {ema20_1h:.4f} | 1H 50 EMA: {ema50_1h:.4f}")
        if is_1h_bull:
            trend_str = "BULLISH (Price > 20 EMA > 50 EMA)"
        elif is_1h_bear:
            trend_str = "BEARISH (Price < 20 EMA < 50 EMA)"
        else:
            trend_str = "RANGING / CHOPPY (No clear moving average fan)"
        print(f"   • Alignment: {trend_str}")

        print(f"3. Support/Resistance Trap Gate (Gate 3):")
        print(f"   • 4H Major Support: {sup_4h:.4f} (Distance: {price - sup_4h:.4f} | Req Buffer: {0.5*atr_1h:.4f})")
        print(f"   • 4H Major Resistance: {res_4h:.4f} (Distance: {res_4h - price:.4f} | Req Buffer: {0.5*atr_1h:.4f})")
        print(f"   • Status: {'TRAP TRIGGERED - Near Resistance' if near_res else ('TRAP TRIGGERED - Near Support' if near_sup else 'CLEAR (No Trap)')}")

        print(f"4. Structural Fractal Trigger (Gate 5):")
        print(f"   • Last 1H Swing High: {last_sh} | Last 1H Swing Low: {last_sl}")
        if last_sh and last_sl:
            if price > last_sh:
                struct_str = f"BREAKOUT ABOVE {last_sh}"
            elif price < last_sl:
                struct_str = f"BREAKDOWN BELOW {last_sl}"
            else:
                struct_str = f"CONFINED INSIDE RANGE ({last_sl} to {last_sh})"
            print(f"   • Structural Position: {struct_str}")

        print(f"5. Decision Engine Verdict:")
        if is_4h_bull and is_1h_bull and is_discount and not near_res and last_sh and price > last_sh:
            verdict = "QUALIFIES FOR BUY ORDER"
        elif is_4h_bear and is_1h_bear and is_premium and not near_sup and last_sl and price < last_sl:
            verdict = "QUALIFIES FOR SELL ORDER"
        else:
            reasons = []
            if not (is_4h_bull and is_1h_bull) and not (is_4h_bear and is_1h_bear):
                reasons.append("Multi-timeframe trend conflict / Ranging state")
            if (is_4h_bull and is_premium):
                reasons.append("Price is in Premium (Exhausted for Buys)")
            if (is_4h_bear and is_discount):
                reasons.append("Price is in Discount (Exhausted for Sells)")
            if near_res or near_sup:
                reasons.append("Proximity to major 4H Support/Resistance trap")
            if last_sh and last_sl and (price <= last_sh and price >= last_sl):
                reasons.append(f"Price is compressing inside 1H fractal range ({last_sl} - {last_sh}) without a valid breakout")
            verdict = "NO TRADE — " + " | ".join(reasons)
        print(f"   • >>> {verdict} <<<")

    print("\n" + "=" * 80)
    mt5.shutdown()

if __name__ == "__main__":
    diagnose()
