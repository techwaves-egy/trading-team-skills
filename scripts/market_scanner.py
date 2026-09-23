"""
Market Scanner v3.0.0
"""
import MetaTrader5 as mt5
import pandas as pd
import time
import logging

try:
    from send_alert import dispatch_alert
except ImportError:
    def dispatch_alert(msg):
        logging.info(f"Alert dispatched: {msg}")

logging.basicConfig(level=logging.INFO)

def calculate_ema(prices, period):
    return prices.ewm(span=period, adjust=False).mean()

def calculate_atr(high, low, close, period):
    tr = pd.concat([high - low, abs(high - close.shift(1)), abs(low - close.shift(1))], axis=1).max(axis=1)
    return tr.rolling(period).mean()

def scan_asset(symbol):
    if not mt5.initialize():
        logging.error("MT5 initialization failed")
        return None

    rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_H1, 0, 50)
    if rates is None or len(rates) < 50:
        logging.warning(f"Failed to get rates for {symbol}")
        return None

    df = pd.DataFrame(rates)
    df['time'] = pd.to_datetime(df['time'], unit='s')
    df['ema20'] = calculate_ema(df['close'], 20)
    df['ema50'] = calculate_ema(df['close'], 50)
    df['atr'] = calculate_atr(df['high'], df['low'], df['close'], 14)

    curr_close = df['close'].iloc[-1]
    curr_ema20 = df['ema20'].iloc[-1]
    curr_ema50 = df['ema50'].iloc[-1]
    curr_atr = df['atr'].iloc[-1]

    # Regime
    if curr_close > curr_ema20 > curr_ema50:
        regime = 'STRONG_UPTREND'
    elif curr_close > curr_ema20:
        regime = 'WEAK_UPTREND'
    elif curr_close < curr_ema20 < curr_ema50:
        regime = 'STRONG_DOWNTREND'
    elif curr_close < curr_ema20:
        regime = 'WEAK_DOWNTREND'
    elif abs(curr_ema20 - curr_ema50) < curr_atr:
        regime = 'COMPRESSION'
    else:
        regime = 'RANGE'

    # FVG
    fvgs = []
    last_10 = df.iloc[-10:]
    for i in range(1, len(last_10) - 1):
        prev = last_10.iloc[i-1]
        next_candle = last_10.iloc[i+1]
        
        if prev['high'] < next_candle['low']:
            fvgs.append({'type': 'bullish', 'top': next_candle['low'], 'bottom': prev['high']})
        elif prev['low'] > next_candle['high']:
            fvgs.append({'type': 'bearish', 'top': prev['low'], 'bottom': next_candle['high']})

    # Order Blocks
    order_blocks = []
    for i in range(1, len(last_10) - 1):
        if last_10.iloc[i-1]['close'] < last_10.iloc[i-1]['open'] and last_10.iloc[i]['close'] > last_10.iloc[i]['open']:
            order_blocks.append({'type': 'bullish', 'level': last_10.iloc[i-1]['low']})
        elif last_10.iloc[i-1]['close'] > last_10.iloc[i-1]['open'] and last_10.iloc[i]['close'] < last_10.iloc[i]['open']:
            order_blocks.append({'type': 'bearish', 'level': last_10.iloc[i-1]['high']})

    # Scoring
    score = 0
    direction = 'neutral'
    
    if regime in ['STRONG_UPTREND', 'WEAK_UPTREND']:
        direction = 'bullish'
        score += 25
    elif regime in ['STRONG_DOWNTREND', 'WEAK_DOWNTREND']:
        direction = 'bearish'
        score += 25

    if fvgs or order_blocks:
        score += 30
        
    score += 20 # Assuming ATR is fine for now

    return {
        'symbol': symbol,
        'regime': regime,
        'atr': curr_atr,
        'ema20': curr_ema20,
        'ema50': curr_ema50,
        'fvgs': fvgs,
        'order_blocks': order_blocks,
        'score': score,
        'direction': direction
    }

def scan_universe(symbols):
    candidates = []
    for symbol in symbols:
        result = scan_asset(symbol)
        if result and result['score'] >= 75:
            candidates.append(result)
    return sorted(candidates, key=lambda x: x['score'], reverse=True)

def run_market_scan(asset='ALL'):
    if asset == 'ALL':
        symbols = ['XAUUSD', 'EURUSD', 'GBPUSD', 'USDJPY', 'BTCUSD']
    else:
        symbols = [asset]
    
    candidates = scan_universe(symbols)
    logging.info(f"Scan complete. Candidates: {candidates}")
    return candidates

def start_monitoring_loop(interval_minutes=15):
    while True:
        candidates = run_market_scan()
        for cand in candidates:
            if cand['score'] >= 75:
                msg = f"Alert for {cand['symbol']}: Score {cand['score']}, Regime {cand['regime']}, Direction {cand['direction']}"
                dispatch_alert(msg)
        time.sleep(interval_minutes * 60)

if __name__ == "__main__":
    run_market_scan()
