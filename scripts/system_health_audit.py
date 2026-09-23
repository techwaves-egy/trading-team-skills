#!/usr/bin/env python3
import sys
import os
import time
from datetime import datetime, timezone, timedelta
import MetaTrader5 as mt5

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

def audit():
    if not mt5.initialize():
        print("MT5 Initialization failed")
        return

    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    print("=" * 80)
    print(f"       TECHWAVES EGY — COMPLETE SYSTEM & MARKET TELEMETRY AUDIT")
    print(f"                    Timestamp: {now_str}")
    print("=" * 80 + "\n")

    # 1. Account Telemetry
    acc = mt5.account_info()
    term = mt5.terminal_info()
    print("[1] ACCOUNT & TERMINAL HEALTH:")
    print(f"  • MT5 Connected:    {term.connected}")
    print(f"  • Account Login:    {acc.login} ({acc.server})")
    print(f"  • Balance:          ${acc.balance:,.2f}")
    print(f"  • Equity:           ${acc.equity:,.2f}")
    print(f"  • Free Margin:      ${acc.margin_free:,.2f}")
    if acc.margin_level:
        print(f"  • Margin Level:     {acc.margin_level:.2f}%")
    else:
        print("  • Margin Level:     N/A (Flat)")
    print(f"  • Trade Allowed:    {term.trade_allowed}")

    # 2. Open Positions
    positions = mt5.positions_get()
    print(f"\n[2] ACTIVE POSITIONS ({len(positions) if positions else 0} OPEN):")
    if positions:
        for p in positions:
            d_str = "BUY" if p.type == 0 else "SELL"
            tick = mt5.symbol_info_tick(p.symbol)
            cur_p = tick.bid if p.type == 0 else tick.ask
            dist_tp = abs(p.tp - cur_p) if p.tp > 0 else 0
            dist_sl = abs(cur_p - p.sl) if p.sl > 0 else 0
            print(f"  • Ticket #{p.ticket} | {p.symbol} {d_str} | Vol: {p.volume:.2f} Lots")
            print(f"    Open: {p.price_open} | Current: {cur_p} | Floating P&L: ${p.profit:+,.2f}")
            print(f"    SL: {p.sl} (Distance: {dist_sl:.2f}) | TP: {p.tp} (Distance: {dist_tp:.2f})")
    else:
        print("  • No open positions (Account is 100% flat).")

    # 3. Today Closed Deals
    now_ts = int(time.time()) + 86400
    from_ts = now_ts - (86400 * 2)
    deals = mt5.history_deals_get(from_ts, now_ts)
    today_deals = [d for d in deals if d.entry in [mt5.DEAL_ENTRY_OUT, getattr(mt5, "DEAL_ENTRY_OUT_BY", 2)]] if deals else []
    print(f"\n[3] TODAY CLOSED DEALS ({len(today_deals)} CLOSED):")
    tot_pnl = 0.0
    wins, losses = 0, 0
    for d in today_deals:
        dt = datetime.fromtimestamp(d.time, tz=timezone.utc).strftime("%H:%M:%S UTC")
        pnl = round(d.profit + getattr(d, "swap", 0.0) + getattr(d, "fee", 0.0), 2)
        tot_pnl += pnl
        if pnl > 0: wins += 1
        elif pnl < 0: losses += 1
        print(f"  • Deal #{d.ticket} | {d.symbol} | Vol: {d.volume:.2f} | Exit: {d.price} | P&L: ${pnl:+,.2f} | Time: {dt}")
    print(f"  >>> Total Realized P&L Today: ${tot_pnl:+,.2f} (Wins: {wins}, Losses: {losses}) <<<")

    # 4. Market Technical Telemetry
    print(f"\n[4] LIVE MARKET TECHNICAL TELEMETRY:")
    for sym in ["EURUSD", "XAUUSD"]:
        tick = mt5.symbol_info_tick(sym)
        p = tick.bid if tick else 0.0
        r1 = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_H1, 0, 50)
        r4 = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_H4, 0, 50)
        c1 = [r['close'] for r in r1]
        c4 = [r['close'] for r in r4]
        bb_mid = sum(c1[-20:]) / 20.0
        var = sum([(x - bb_mid)**2 for x in c1[-20:]]) / 20.0
        bb_std = var ** 0.5
        bb_upper = bb_mid + 2.0 * bb_std
        bb_lower = bb_mid - 2.0 * bb_std
        e50_4 = sum(c4[-50:]) / 50.0
        tr = [max(r1[i]['high']-r1[i]['low'], abs(r1[i]['high']-r1[i-1]['close']), abs(r1[i]['low']-r1[i-1]['close'])) for i in range(1, len(r1))]
        atr1 = sum(tr[-14:]) / 14.0
        print(f"\n  • [{sym}] Current Price: {p} | 4H 50 EMA: {e50_4:.4f} | 1H ATR: {atr1:.4f}")
        print(f"    1H Bollinger Envelope: Lower={bb_lower:.4f} | Mid={bb_mid:.4f} | Upper={bb_upper:.4f}")
        if p <= bb_lower:
            status = "OVERSOLD (Lower Band Pierce - BUY Rebound Setup)"
        elif p >= bb_upper:
            status = "OVERBOUGHT (Upper Band Pierce - SELL Rebound Setup)"
        else:
            pct = ((p - bb_lower)/(bb_upper - bb_lower)*100) if (bb_upper > bb_lower) else 50.0
            status = f"CONSOLIDATING ({pct:.1f}% inside band envelope)"
        print(f"    Market Status: {status}")

    print("\n" + "=" * 80)
    mt5.shutdown()

if __name__ == "__main__":
    audit()
