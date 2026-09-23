import sys
from datetime import datetime, timezone
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import MetaTrader5 as mt5

if not mt5.initialize():
    print("MT5 Failed")
    sys.exit(1)

for sym in ["XAUUSD", "EURUSD", "GBPUSD", "USDJPY"]:
    rates_1h = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_H1, 0, 50000)
    rates_4h = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_H4, 0, 20000)
    
    c1h = len(rates_1h) if rates_1h is not None else 0
    c4h = len(rates_4h) if rates_4h is not None else 0
    
    earliest_1h = datetime.fromtimestamp(rates_1h[0]['time'], tz=timezone.utc).strftime('%Y-%m-%d') if c1h > 0 else 'N/A'
    earliest_4h = datetime.fromtimestamp(rates_4h[0]['time'], tz=timezone.utc).strftime('%Y-%m-%d') if c4h > 0 else 'N/A'
    
    print(f"{sym:7s} | 1H: {c1h:5d} bars (back to {earliest_1h}) | 4H: {c4h:5d} bars (back to {earliest_4h})")

mt5.shutdown()
