import sys
sys.path.insert(0, r"d:\Techwaves-egy\Trading Team Skills\scripts")
from research_backtest import run_simulation
import MetaTrader5 as mt5
from datetime import datetime, timezone

if mt5.initialize():
    s25 = datetime(2025, 1, 1, tzinfo=timezone.utc)
    e25 = datetime(2025, 12, 31, 23, 59, tzinfo=timezone.utc)
    s24 = datetime(2024, 1, 1, tzinfo=timezone.utc)
    e24 = datetime(2024, 12, 31, 23, 59, tzinfo=timezone.utc)
    
    print("=== BREAKOUT MODEL ON 2025 VS 2024 ===")
    for sym in ["EURUSD", "GBPUSD", "XAUUSD"]:
        r25 = run_simulation(sym, s25, e25, entry_model="breakout")
        r24 = run_simulation(sym, s24, e24, entry_model="breakout")
        print(f"{sym} 2025: {r25['trades']} Trds | Win: {r25['win_rate']}% | PnL: ${r25['net_pnl']:+,.2f} | PF: {r25['pf']:.2f} | Exp: ${r25['expectancy']:+.2f} | Avg R: {r25['avg_r']:+.2f}R | Sharpe: {r25['sharpe']}")
        print(f"{sym} 2024: {r24['trades']} Trds | Win: {r24['win_rate']}% | PnL: ${r24['net_pnl']:+,.2f} | PF: {r24['pf']:.2f} | Exp: ${r24['expectancy']:+.2f} | Avg R: {r24['avg_r']:+.2f}R | Sharpe: {r24['sharpe']}")
        print("-" * 75)
    mt5.shutdown()
