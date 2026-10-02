import MetaTrader5 as mt5
import json
import logging
import time
import math
from datetime import datetime, timezone, timedelta
import os

# -----------------------------------------------------------------------------
# MT5 Connector v3.0.0 - Institutional Rules
# -----------------------------------------------------------------------------

logger = logging.getLogger("MT5Connector_v3")
if not logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)

class MT5Bridge:
    """Persistent MT5 Connection Manager (v3.0.0)"""
    def __init__(self):
        self.connected = False

    def __enter__(self):
        self.initialize()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass # Keep connection alive as per requirements
        
    def initialize(self):
        if self.connected:
            return True
        max_retries = 3
        backoff = 1
        for i in range(max_retries):
            if mt5.initialize():
                self.connected = True
                logger.info("MT5 initialized successfully (v3.0.0).")
                return True
            else:
                logger.warning(f"MT5 init failed, retrying in {backoff}s... Error: {mt5.last_error()}")
                time.sleep(backoff)
                backoff *= 2
        logger.error("Failed to initialize MT5 after retries.")
        return False

# Global singletons
bridge = MT5Bridge()
_loss_tracker = {}
LOSS_STATE_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config", "loss_state.json")

def load_loss_tracker():
    if os.path.exists(LOSS_STATE_FILE):
        try:
            with open(LOSS_STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error loading loss state: {e}")
    return {}

def save_loss_tracker(state):
    try:
        os.makedirs(os.path.dirname(LOSS_STATE_FILE), exist_ok=True)
        with open(LOSS_STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)
    except Exception as e:
        logger.error(f"Error saving loss state: {e}")

def get_daily_realized_pnl():
    """
    Computes today's net realized PnL across all closed deals from 00:00:00 UTC to now.
    Includes profit, swap, fee, and commission.
    """
    bridge.initialize()
    now_utc = datetime.now(timezone.utc)
    start_of_day_utc = datetime(now_utc.year, now_utc.month, now_utc.day, 0, 0, 0, tzinfo=timezone.utc)
    start_ts = int(start_of_day_utc.timestamp())
    end_ts = int(now_utc.timestamp()) + 300

    deals = mt5.history_deals_get(start_ts, end_ts)
    if not deals:
        return 0.0

    out_entries = [mt5.DEAL_ENTRY_OUT, getattr(mt5, "DEAL_ENTRY_OUT_BY", 2)]
    net_pnl = 0.0
    for d in deals:
        if d.entry in out_entries:
            deal_net = d.profit + getattr(d, "swap", 0.0) + getattr(d, "fee", 0.0) + getattr(d, "commission", 0.0)
            net_pnl += deal_net

    return round(net_pnl, 2)

def get_session_state():
    config_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config", "session_state.json")
    try:
        if os.path.exists(config_path):
            with open(config_path, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        logger.error(f"Failed to load session_state.json: {e}")
    return {"risk_per_trade_dollars": 5.0, "max_daily_loss_dollars": 50.0, "default_lots": 0.01}

def calculate_atr(symbol, timeframe=mt5.TIMEFRAME_H1, period=14):
    """Real ATR Calculation (True Range based)"""
    bridge.initialize()
    rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, period + 1)
    if rates is None or len(rates) < period + 1:
        logger.error(f"Failed to get rates for {symbol} ATR calculation.")
        return None
    
    true_ranges = []
    for i in range(1, len(rates)):
        high = rates[i]['high']
        low = rates[i]['low']
        prev_close = rates[i-1]['close']
        # True Range = max(High-Low, abs(High-PrevClose), abs(Low-PrevClose))
        tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
        true_ranges.append(tr)
        
    atr = sum(true_ranges[-period:]) / period
    return atr

def get_macro_trend_bias(symbol, timeframe=mt5.TIMEFRAME_H4):
    """
    Paul Tudor Jones 200 EMA & 4H Macro Trend Bias Engine (v5.0.0)
    PTJ Golden Rule: 'Nothing good happens below the 200-day/200-period moving average.'
    Returns:
        dict: {
            "bias": "BULLISH" | "BEARISH" | "NEUTRAL",
            "ema200": float,
            "ema50": float,
            "price": float,
            "reason": str
        }
    """
    bridge.initialize()
    rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, 250)
    if rates is None or len(rates) < 60:
        return {"bias": "NEUTRAL", "ema200": 0.0, "ema50": 0.0, "price": 0.0, "reason": "Insufficient 4H rates"}

    closes = [r['close'] for r in rates]
    price = closes[-1]

    def calc_ema(series, period):
        k = 2.0 / (period + 1.0)
        ema = series[0]
        for val in series[1:]:
            ema = (val * k) + (ema * (1.0 - k))
        return ema

    ema50 = calc_ema(closes, min(50, len(closes)))
    ema200 = calc_ema(closes, min(200, len(closes)))

    is_below_200 = price < ema200
    is_below_50 = price < ema50
    is_above_200 = price > ema200
    is_above_50 = price > ema50

    if is_below_200 and is_below_50:
        bias = "BEARISH"
        reason = f"Price ({price:.2f}) < 4H 200 EMA ({ema200:.2f}) & 50 EMA ({ema50:.2f}) — Strong Macro Downtrend"
    elif is_above_200 and is_above_50:
        bias = "BULLISH"
        reason = f"Price ({price:.2f}) > 4H 200 EMA ({ema200:.2f}) & 50 EMA ({ema50:.2f}) — Strong Macro Uptrend"
    elif is_below_200:
        bias = "BEARISH"
        reason = f"Price ({price:.2f}) < 4H 200 EMA ({ema200:.2f}) — PTJ Macro Bear Bias"
    elif is_above_200:
        bias = "BULLISH"
        reason = f"Price ({price:.2f}) > 4H 200 EMA ({ema200:.2f}) — PTJ Macro Bull Bias"
    else:
        bias = "NEUTRAL"
        reason = f"Price ({price:.2f}) consolidating near 4H EMAs (50 EMA: {ema50:.2f}, 200 EMA: {ema200:.2f})"

    return {
        "bias": bias,
        "ema200": round(ema200, 2),
        "ema50": round(ema50, 2),
        "price": round(price, 2),
        "reason": reason
    }

def get_asian_range(symbol):
    """
    Computes Asian Session High, Low, and Mid for today (00:00 - 06:00 UTC).
    """
    bridge.initialize()
    now_utc = datetime.now(timezone.utc)
    start_asian = datetime(now_utc.year, now_utc.month, now_utc.day, 0, 0, tzinfo=timezone.utc)
    end_asian = datetime(now_utc.year, now_utc.month, now_utc.day, 6, 0, tzinfo=timezone.utc)

    rates = mt5.copy_rates_range(symbol, mt5.TIMEFRAME_M15, start_asian, end_asian)
    if rates is None or len(rates) < 4:
        return {"valid": False, "high": 0.0, "low": 0.0, "mid": 0.0, "range": 0.0}

    asian_high = max(r['high'] for r in rates)
    asian_low = min(r['low'] for r in rates)
    asian_mid = (asian_high + asian_low) / 2.0
    asian_range = asian_high - asian_low

    return {
        "valid": True,
        "high": round(asian_high, 2),
        "low": round(asian_low, 2),
        "mid": round(asian_mid, 2),
        "range": round(asian_range, 2)
    }

def check_liquidity_sweep(symbol, direction):
    """
    Institutional ICT Liquidity Sweep / Judas Swing Engine (v5.0.0)
    Checks if London or NY session swept the Asian High/Low and rejected back inside.
    - Bearish Judas Swing (SELL): Price spiked ABOVE Asian High, swept buy stops, and closed back BELOW Asian High.
    - Bullish Judas Swing (BUY): Price spiked BELOW Asian Low, swept sell stops, and closed back ABOVE Asian Low.
    """
    asian = get_asian_range(symbol)
    if not asian.get("valid"):
        return False, 0.0, "Asian range not established or insufficient bars"

    bridge.initialize()
    rates_m15 = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M15, 0, 20)
    if rates_m15 is None or len(rates_m15) < 5:
        return False, 0.0, "Insufficient M15 bars for liquidity sweep"

    last_closed = rates_m15[-2]
    recent_bars = rates_m15[-8:-1]

    if direction.upper() == "SELL":
        highest_recent = max(r['high'] for r in recent_bars)
        if highest_recent > asian['high']:
            if last_closed['close'] < asian['high']:
                return True, highest_recent, (
                    f"Bearish Judas Swing: Asian High ({asian['high']:.2f}) swept by spike to "
                    f"{highest_recent:.2f}, closed back below ({last_closed['close']:.2f})"
                )
        return False, 0.0, f"No Asian High sweep detected (Asian High: {asian['high']:.2f}, High: {highest_recent:.2f})"

    elif direction.upper() == "BUY":
        lowest_recent = min(r['low'] for r in recent_bars)
        if lowest_recent < asian['low']:
            if last_closed['close'] > asian['low']:
                return True, lowest_recent, (
                    f"Bullish Judas Swing: Asian Low ({asian['low']:.2f}) swept by spike to "
                    f"{lowest_recent:.2f}, closed back above ({last_closed['close']:.2f})"
                )
        return False, 0.0, f"No Asian Low sweep detected (Asian Low: {asian['low']:.2f}, Low: {lowest_recent:.2f})"

    return False, 0.0, "Invalid direction"

def check_confirmation(symbol, direction, timeframe=mt5.TIMEFRAME_M15):
    """
    Multi-Timeframe Structural Confirmation & Trap Filter Gate (v3.1.0)
    1. Trap Filter: Rejects Selling into 4H Major Support Floor or Buying into 4H Major Resistance.
    2. True Structural Swing Break: Requires breaking a verified 1H Swing High/Low.
    """
    bridge.initialize()
    rates_1h = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_H1, 0, 40)
    rates_4h = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_H4, 0, 30)
    rates_m15 = mt5.copy_rates_from_pos(symbol, timeframe, 0, 30)
    
    if rates_1h is None or len(rates_1h) < 20 or rates_m15 is None or len(rates_m15) < 10:
        return False, "Failed to fetch rates for structural confirmation"
    
    tick = mt5.symbol_info_tick(symbol)
    if not tick:
        return False, "Failed to get tick data"
    price = tick.bid if direction.upper() == "SELL" else tick.ask
    atr = calculate_atr(symbol, mt5.TIMEFRAME_H1, 14) or 1.0
    
    # 1. Major 4H Support / Resistance Trap Filter
    if rates_4h is not None and len(rates_4h) >= 20:
        support_4h = min([r['low'] for r in rates_4h[-20:]])
        resistance_4h = max([r['high'] for r in rates_4h[-20:]])
        
        # Do not sell directly at the bottom support floor (within 0.5x ATR)
        if direction.upper() == "SELL" and (price - support_4h) < (0.5 * atr) and price >= support_4h:
            return False, f"TRAP FILTER: Selling directly into 4H Major Support ({support_4h:.2f}). Floor distance {price - support_4h:.2f} < 0.5x ATR ({0.5*atr:.2f})"
            
        # Do not buy directly at the top resistance ceiling (within 0.5x ATR)
        if direction.upper() == "BUY" and (resistance_4h - price) < (0.5 * atr) and price <= resistance_4h:
            return False, f"TRAP FILTER: Buying directly into 4H Major Resistance ({resistance_4h:.2f}). Ceiling distance {resistance_4h - price:.2f} < 0.5x ATR ({0.5*atr:.2f})"

    # 2. True 1-Hour Fractal Swing Points
    swing_highs = []
    swing_lows = []
    for i in range(2, len(rates_1h) - 2):
        if rates_1h[i]['high'] > rates_1h[i-1]['high'] and rates_1h[i]['high'] > rates_1h[i-2]['high'] and \
           rates_1h[i]['high'] > rates_1h[i+1]['high'] and rates_1h[i]['high'] > rates_1h[i+2]['high']:
            swing_highs.append(rates_1h[i]['high'])
        if rates_1h[i]['low'] < rates_1h[i-1]['low'] and rates_1h[i]['low'] < rates_1h[i-2]['low'] and \
           rates_1h[i]['low'] < rates_1h[i+1]['low'] and rates_1h[i]['low'] < rates_1h[i+2]['low']:
            swing_lows.append(rates_1h[i]['low'])
            
    latest_m15_close = rates_m15[-2]['close'] # fully closed candle
    
    if direction.upper() == "BUY":
        if not swing_highs:
            return False, "No valid 1H swing highs identified"
        target_swing = swing_highs[-1]
        if latest_m15_close > target_swing:
            return True, f"CHoCH Buy Confirmed (15M Close {latest_m15_close:.2f} > 1H Swing High {target_swing:.2f})"
        return False, f"Price {latest_m15_close:.2f} has not broken 1H Swing High {target_swing:.2f}"
        
    elif direction.upper() == "SELL":
        if not swing_lows:
            return False, "No valid 1H swing lows identified"
        target_swing = swing_lows[-1]
        if latest_m15_close < target_swing:
            return True, f"CHoCH Sell Confirmed (15M Close {latest_m15_close:.2f} < 1H Swing Low {target_swing:.2f})"
        return False, f"Price {latest_m15_close:.2f} has not broken 1H Swing Low {target_swing:.2f}"
    
    return False, "Invalid direction"

def check_bollinger_confirmation(symbol, direction):
    """
    Multi-Candle Reversal Confirmation & Waterfall Filter for Bollinger Mean Reversion (v4.0.0)
    Guarantees:
    1. Upper/Lower band was tested by a recent closed candle (1H or 15M).
    2. Anti-Waterfall Cascade Filter: Rejects fading if last 3 1H bars were unidirectional waterfall bars.
    3. Multi-Candle Reversal on M15: Requires rejection wick >= 35%, engulfing, or 2 consecutive directional closes.
    4. Price Action Alignment: Live price confirms momentum and does not break beyond the extreme of the reversal candle.
    """
    bridge.initialize()
    rates_1h = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_H1, 0, 30)
    rates_m15 = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M15, 0, 15)
    if rates_1h is None or len(rates_1h) < 22 or rates_m15 is None or len(rates_m15) < 5:
        return False, "Insufficient candle data for Bollinger confirmation"
        
    tick = mt5.symbol_info_tick(symbol)
    if not tick:
        return False, "Tick data unavailable"
    price = tick.bid if direction.upper() == "SELL" else tick.ask

    # Calculate 1H Bollinger Bands on completed bars
    closes_1h = [r['close'] for r in rates_1h[:-1]]  # exclude live forming bar
    bb_mid = sum(closes_1h[-20:]) / 20.0
    variance = sum((c - bb_mid) ** 2 for c in closes_1h[-20:]) / 20.0
    bb_std = variance ** 0.5
    bb_upper = bb_mid + 2.0 * bb_std
    bb_lower = bb_mid - 2.0 * bb_std
    atr_est = max(0.01, (bb_upper - bb_lower) / 4.0)

    last_closed_m15 = rates_m15[-2]  # index -1 is forming candle; -2 is last closed candle
    prev_closed_m15 = rates_m15[-3]
    last_closed_1h = rates_1h[-2]

    # --- 1. Waterfall Cascade Filter ("No Falling Knives Policy") ---
    if len(rates_1h) >= 5:
        c_3h = rates_1h[-4:-1]
        if direction.upper() == "BUY":
            waterfall_down = all(r['close'] < r['open'] for r in c_3h)
            drop_pts = rates_1h[-4]['open'] - rates_1h[-2]['close']
            if waterfall_down and drop_pts > 2.0 * atr_est:
                return False, f"FALLING KNIFE FILTER: 3 consecutive 1H drop bars ({drop_pts:.2f} pts). Reversion BUY blocked until base forms."
        elif direction.upper() == "SELL":
            waterfall_up = all(r['close'] > r['open'] for r in c_3h)
            rally_pts = rates_1h[-2]['close'] - rates_1h[-4]['open']
            if waterfall_up and rally_pts > 2.0 * atr_est:
                return False, f"PARABOLIC RALLY FILTER: 3 consecutive 1H expansion bars ({rally_pts:.2f} pts). Reversion SELL blocked."

    # --- 1.1 Paul Tudor Jones 4H 200 EMA Macro Bias Gate ---
    macro_info = get_macro_trend_bias(symbol, mt5.TIMEFRAME_H4)
    m_bias = macro_info.get("bias", "NEUTRAL")
    if direction.upper() == "BUY" and m_bias == "BEARISH":
        return False, f"PTJ 200 EMA FILTER: Counter-trend BUY blocked. 4H Macro Bias is BEARISH ({macro_info.get('reason')})."
    elif direction.upper() == "SELL" and m_bias == "BULLISH":
        return False, f"PTJ 200 EMA FILTER: Counter-trend SELL blocked. 4H Macro Bias is BULLISH ({macro_info.get('reason')})."

    # --- 2. Directional Confirmation & Multi-Candle Reversal ---
    if direction.upper() == "SELL":
        band_tested = (
            last_closed_1h['high'] >= bb_upper or
            last_closed_m15['high'] >= bb_upper or
            prev_closed_m15['high'] >= bb_upper or
            price >= bb_upper * 0.999
        )
        if not band_tested:
            return False, f"Upper Bollinger Band ({bb_upper:.2f}) not tested by recent closed candles"

        # Completed 15M candle MUST be bearish (red)
        if last_closed_m15['close'] >= last_closed_m15['open']:
            return False, f"Awaiting closed-candle confirmation: Last 15M candle closed bullish (O:{last_closed_m15['open']:.2f}, C:{last_closed_m15['close']:.2f}). Sellers not confirmed."

        # Multi-candle structure requirement:
        candle_range = last_closed_m15['high'] - last_closed_m15['low']
        upper_wick = last_closed_m15['high'] - max(last_closed_m15['open'], last_closed_m15['close'])
        is_rejection_wick = (upper_wick >= 0.35 * candle_range) if candle_range > 0 else False
        is_engulfing = last_closed_m15['close'] < prev_closed_m15['open']
        two_red = (last_closed_m15['close'] < last_closed_m15['open']) and (prev_closed_m15['close'] < prev_closed_m15['open'])

        if not (is_rejection_wick or is_engulfing or two_red):
            return False, f"Awaiting structural reversal confirmation: M15 candle lacks upper rejection wick (<35%), engulfing, or 2nd red bar."

        # Live price must not be spiking above rejection candle high
        if price > last_closed_m15['high']:
            return False, f"Price breakout detected: live price ({price:.2f}) broke above rejection high ({last_closed_m15['high']:.2f}). Mean reversion aborted."

        return True, f"Multi-Candle Reversal Confirmed (15M Bearish Close {last_closed_m15['close']:.2f}, Live {price:.2f})"

    elif direction.upper() == "BUY":
        band_tested = (
            last_closed_1h['low'] <= bb_lower or
            last_closed_m15['low'] <= bb_lower or
            prev_closed_m15['low'] <= bb_lower or
            price <= bb_lower * 1.001
        )
        if not band_tested:
            return False, f"Lower Bollinger Band ({bb_lower:.2f}) not tested by recent closed candles"

        # Completed 15M candle MUST be bullish (green)
        if last_closed_m15['close'] <= last_closed_m15['open']:
            return False, f"Awaiting closed-candle confirmation: Last 15M candle closed bearish (O:{last_closed_m15['open']:.2f}, C:{last_closed_m15['close']:.2f}). Buyers not confirmed."

        # Multi-candle structure requirement:
        candle_range = last_closed_m15['high'] - last_closed_m15['low']
        lower_wick = min(last_closed_m15['open'], last_closed_m15['close']) - last_closed_m15['low']
        is_rejection_wick = (lower_wick >= 0.35 * candle_range) if candle_range > 0 else False
        is_engulfing = last_closed_m15['close'] > prev_closed_m15['open']
        two_green = (last_closed_m15['close'] > last_closed_m15['open']) and (prev_closed_m15['close'] > prev_closed_m15['open'])

        if not (is_rejection_wick or is_engulfing or two_green):
            return False, f"Awaiting structural reversal confirmation: M15 candle lacks lower rejection wick (<35%), engulfing, or 2nd green bar."

        # Live price must not be falling below rejection candle low
        if price < last_closed_m15['low']:
            return False, f"Price drop detected: live price ({price:.2f}) broke below rejection low ({last_closed_m15['low']:.2f}). Mean reversion aborted."

        return True, f"Multi-Candle Reversal Confirmed (15M Bullish Close {last_closed_m15['close']:.2f}, Live {price:.2f})"

    return False, "Invalid direction"

def update_loss_tracker(symbol):
    """
    Batch-Aware & Persistent 2-Strike Lockout Tracker (v4.0.0).
    Inspects all closed deals in the last 24h, detects batch multi-losses,
    and locks symbol for 60 minutes if 2 or more consecutive losses occur.
    """
    bridge.initialize()
    loss_state = load_loss_tracker()
    sym_state = loss_state.get(symbol, {"count": 0, "locked_until": None, "last_processed_deal": 0})
    
    now_utc = datetime.now(timezone.utc)
    from_date = now_utc - timedelta(days=1)
    deals = mt5.history_deals_get(int(from_date.timestamp()), int(now_utc.timestamp()) + 300, group=f"*{symbol}*")
    if not deals:
        return
        
    out_entries = [mt5.DEAL_ENTRY_OUT, getattr(mt5, "DEAL_ENTRY_OUT_BY", 2)]
    out_deals = [d for d in deals if d.entry in out_entries]
    if not out_deals:
        return
        
    out_deals_sorted = sorted(out_deals, key=lambda x: x.time)
    last_seen = sym_state.get("last_processed_deal", 0)
    new_deals = [d for d in out_deals_sorted if d.ticket > last_seen]
    if not new_deals:
        return
        
    # Group new deals by timestamp to recognize batches (deals within 5 seconds of each other)
    batches = []
    current_batch = []
    for d in new_deals:
        if not current_batch:
            current_batch.append(d)
        elif abs(d.time - current_batch[-1].time) <= 5:
            current_batch.append(d)
        else:
            batches.append(current_batch)
            current_batch = [d]
    if current_batch:
        batches.append(current_batch)
        
    for b in batches:
        net_batch_profit = sum(d.profit + getattr(d, 'swap', 0) + getattr(d, 'fee', 0) + getattr(d, 'commission', 0) for d in b)
        losing_deals_in_batch = [d for d in b if (d.profit + getattr(d, 'swap', 0) + getattr(d, 'fee', 0) + getattr(d, 'commission', 0)) < 0]
        
        if net_batch_profit < 0:
            loss_count_inc = max(1, len(losing_deals_in_batch))
            sym_state["count"] += loss_count_inc
            logger.info(f"[LOSS TRACKER] Loss batch detected on {symbol} ({loss_count_inc} losing tickets). Consecutive losses now: {sym_state['count']}")
            
            if sym_state["count"] >= 2:
                lock_expiry = datetime.now(timezone.utc) + timedelta(minutes=60)
                sym_state["locked_until"] = lock_expiry.isoformat()
                logger.warning(f"[2-STRIKE LOCKOUT TRIGGERED] {symbol} locked for 60 minutes until {sym_state['locked_until']} due to {sym_state['count']} losses.")
        elif net_batch_profit > 0:
            sym_state["count"] = 0
            
    sym_state["last_processed_deal"] = max(d.ticket for d in new_deals)
    loss_state[symbol] = sym_state
    save_loss_tracker(loss_state)

def check_asset_lockout(symbol):
    """2-Strike Asset Lockout Enforcement (Persistent v4.0.0)"""
    update_loss_tracker(symbol)
    loss_state = load_loss_tracker()
    if symbol in loss_state:
        sym_state = loss_state[symbol]
        if sym_state.get("count", 0) >= 2 and sym_state.get("locked_until"):
            try:
                lock_until = datetime.fromisoformat(sym_state["locked_until"])
                if datetime.now(timezone.utc) < lock_until:
                    return True, f"Asset locked until {lock_until.strftime('%H:%M:%S UTC')} due to 2-Strike rule"
                else:
                    sym_state["count"] = 0
                    sym_state["locked_until"] = None
                    loss_state[symbol] = sym_state
                    save_loss_tracker(loss_state)
            except Exception:
                pass
    return False, ""

def detect_regime(symbol):
    """
    Multi-Timeframe Regime & Premium/Discount Equilibrium Engine (v3.1.0)
    Confluence required: 4H Macro Trend + 1H Intermediary Trend + Premium/Discount positioning
    """
    bridge.initialize()
    rates_4h = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_H4, 0, 50)
    rates_1h = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_H1, 0, 50)
    
    if rates_4h is None or len(rates_4h) < 30 or rates_1h is None or len(rates_1h) < 30:
        return "UNKNOWN"
    
    # 4H EMA & Range metrics
    c4 = [r['close'] for r in rates_4h]
    h4 = [r['high'] for r in rates_4h]
    l4 = [r['low'] for r in rates_4h]
    ema50_4h = sum(c4[-50:]) / 50 if len(c4) >= 50 else sum(c4) / len(c4)
    
    range_high_4h = max(h4[-30:])
    range_low_4h = min(l4[-30:])
    equilibrium_4h = (range_high_4h + range_low_4h) / 2.0
    
    # 1H EMA metrics
    c1 = [r['close'] for r in rates_1h]
    price = c1[-1]
    ema20_1h = sum(c1[-20:]) / 20
    ema50_1h = sum(c1[-50:]) / 50 if len(c1) >= 50 else sum(c1) / len(c1)
    
    is_4h_bull = price > ema50_4h
    is_4h_bear = price < ema50_4h
    is_1h_bull = price > ema20_1h and ema20_1h > ema50_1h
    is_1h_bear = price < ema20_1h and ema20_1h < ema50_1h
    
    is_premium = price > equilibrium_4h   # Upper half of 4H range -> Sells preferred
    is_discount = price < equilibrium_4h  # Lower half of 4H range -> Buys preferred
    
    # Require multi-timeframe alignment and non-exhausted positioning
    if is_4h_bull and is_1h_bull and (is_discount or price > range_high_4h):
        return "UPTREND"
    elif is_4h_bear and is_1h_bear and (is_premium or price < range_low_4h):
        return "DOWNTREND"
    else:
        return "RANGING"

def execute_mt5_order(ticket):
    """
    Risk-Validated Order Execution Engine - v5.1.0
    When called from auto_scanner with pre-computed SL/TP/lots, acts as a trusted
    executor without re-calculating entry parameters or re-checking confirmation.
    Fallback SL/TP calculation retained for standalone/manual callers.
    """
    try:
        bridge.initialize()

        symbol = ticket.get("symbol")
        if not symbol:
            return {"status": "ERROR", "reason": "Symbol missing in ticket."}

        order_type_str = ticket.get("order_type", "BUY").upper()
        strat_type = ticket.get("strategy", "Structural_Trend_Breakout")

        # Detect if called from scanner (pre-validated) vs. standalone
        scanner_prevalidated = ("sl" in ticket and ticket["sl"] > 0
                                and "tp" in ticket and ticket["tp"] > 0
                                and "lots" in ticket and float(ticket.get("lots", 0)) > 0)

        # 0. Asset Policy Disablement Gate
        if symbol.upper() == "USDJPY":
            reason = "ASSET POLICY: USDJPY is disabled due to negative empirical expectancy (7-Year Benchmark PF 0.75)."
            logger.warning(f"Order REJECTED: {reason}")
            return {"status": "REJECTED", "reason": reason}

        # 0.0 Anti-Tamper & Skill Integrity Gate
        from skill_integrity_guard import verify_skill_integrity
        is_intact, discrepancies = verify_skill_integrity(silent=False)
        if not is_intact:
            reason = f"SECURITY VIOLATION: Skill integrity check failed. Trade blocked."
            logger.critical(reason)
            return {"status": "REJECTED", "reason": reason}

        # 0.1 Dynamic Anti-Stacking & Concurrency Gate
        state = get_session_state()
        batch_size = int(ticket.get("batch_size", state.get("concurrent_batch_size", 1)))
        symbol_pos = mt5.positions_get(symbol=symbol)
        if symbol_pos and len(symbol_pos) >= batch_size:
            reason = f"ANTI-STACKING: Concurrency limit reached ({len(symbol_pos)}/{batch_size} open on {symbol}). Multiple entries blocked."
            logger.warning(f"Order REJECTED: {reason}")
            return {"status": "REJECTED", "reason": reason}

        all_open_pos = mt5.positions_get()
        total_open = len(all_open_pos) if all_open_pos else 0
        if total_open >= batch_size:
            reason = f"PORTFOLIO CONCURRENCY: Limit reached ({total_open}/{batch_size} open positions). Waiting for open trade to close."
            logger.warning(f"Order REJECTED: {reason}")
            return {"status": "REJECTED", "reason": reason}

        # 2-Strike Asset Lockout Check
        locked, lock_reason = check_asset_lockout(symbol)
        if locked:
            logger.warning(f"Order REJECTED: {lock_reason}")
            return {"status": "REJECTED", "reason": lock_reason}

        # Symbol info & tick data (always needed)
        symbol_info = mt5.symbol_info(symbol)
        if symbol_info is None:
            return {"status": "ERROR", "reason": f"Symbol {symbol} not found"}

        tick_info = mt5.symbol_info_tick(symbol)
        if tick_info is None:
            return {"status": "ERROR", "reason": f"Failed to get tick info for {symbol}"}

        digits = symbol_info.digits
        point = symbol_info.point
        price = tick_info.ask if order_type_str == "BUY" else tick_info.bid

        # === v5.1.0 SPREAD GATE (H-4): Reject on abnormal spread ===
        spread_points = tick_info.ask - tick_info.bid
        atr = calculate_atr(symbol, mt5.TIMEFRAME_H1, 14)
        if atr is None:
            return {"status": "ERROR", "reason": "Failed to calculate ATR"}

        is_gold = "XAU" in symbol.upper() or "GOLD" in symbol.upper()
        max_spread = min(0.5 * atr, 3.0 if is_gold else 0.0010)
        if spread_points > max_spread:
            reason = (f"SPREAD GATE: Current spread ({spread_points:.2f}) exceeds max allowed "
                      f"({max_spread:.2f} = min(0.5×ATR, {'$3.00' if is_gold else '10 pips'})). "
                      f"Entry blocked to avoid slippage.")
            logger.warning(f"Order REJECTED: {reason}")
            return {"status": "REJECTED", "reason": reason}

        mt5_order_type = mt5.ORDER_TYPE_BUY if order_type_str == "BUY" else mt5.ORDER_TYPE_SELL

        if scanner_prevalidated:
            # === SCANNER PRE-VALIDATED PATH (C-1 fix): Trust scanner SL/TP/lots ===
            # No re-confirmation (C-3 fix), no SL recalculation
            sl_price = float(ticket["sl"])
            tp1_price = float(ticket["tp"])
            lots = float(ticket["lots"])

            # Minimal lot clamping to broker limits only
            lots = max(symbol_info.volume_min, min(symbol_info.volume_max, lots))
            step = symbol_info.volume_step
            if step > 0:
                lots = round(lots / step) * step

            # Compute informational TP2/TP3 distances for response
            if order_type_str == "BUY":
                sl_dist = price - sl_price
            else:
                sl_dist = sl_price - price
            tp2_price = (price + sl_dist * 2.0) if order_type_str == "BUY" else (price - sl_dist * 2.0)
            tp3_price = (price + sl_dist * 3.5) if order_type_str == "BUY" else (price - sl_dist * 3.5)

            logger.info(f"[SCANNER EXECUTOR] Trusted SL={sl_price}, TP={tp1_price}, Lots={lots} (no re-calc)")

        else:
            # === STANDALONE / MANUAL PATH: Full calculation with confirmation ===
            # Confirmation check (only for non-scanner calls)
            if strat_type == "Bollinger_Mean_Reversion":
                confirmed, conf_reason = check_bollinger_confirmation(symbol, order_type_str)
                if not confirmed:
                    logger.warning(f"Order REJECTED (Bollinger Confirmation): {conf_reason}")
                    return {"status": "REJECTED", "reason": conf_reason}
            else:
                confirmed, conf_reason = check_confirmation(symbol, order_type_str)
                if not confirmed:
                    logger.warning(f"Order REJECTED (Structural Confirmation): {conf_reason}")
                    return {"status": "REJECTED", "reason": conf_reason}

            # SL/TP calculation
            if "sl" in ticket and ticket["sl"] > 0:
                if order_type_str == "BUY":
                    sl_dist = price - ticket["sl"]
                else:
                    sl_dist = ticket["sl"] - price
            else:
                sl_dist = 2.0 * atr

            min_safe = 1.0 * atr
            if sl_dist < min_safe:
                sl_dist = min_safe

            tp1_dist = max(sl_dist * 1.2, atr * 1.2)
            tp2_dist = max(sl_dist * 2.0, atr * 2.0)
            tp3_dist = max(sl_dist * 3.5, atr * 3.5)

            if order_type_str == "BUY":
                sl_price = price - sl_dist
                tp1_price = ticket.get("tp", price + tp1_dist)
                tp2_price = price + tp2_dist
                tp3_price = price + tp3_dist
            else:
                sl_price = price + sl_dist
                tp1_price = ticket.get("tp", price - tp1_dist)
                tp2_price = price - tp2_dist
                tp3_price = price - tp3_dist

            # Lot sizing
            contract_size = symbol_info.trade_contract_size if symbol_info.trade_contract_size > 0 else 100.0
            risk_dollars = float(state.get("risk_per_trade_dollars", state.get("risk_amount", 5.0)))

            ticket_lots = ticket.get("lots") or ticket.get("volume")
            if ticket_lots and float(ticket_lots) > 0:
                lots = float(ticket_lots)
            else:
                if sl_dist > 0 and contract_size > 0:
                    lots = risk_dollars / (sl_dist * contract_size)
                else:
                    lots = symbol_info.volume_min

            lots = max(symbol_info.volume_min, min(symbol_info.volume_max, lots))
            step = symbol_info.volume_step
            if step > 0:
                lots = round(lots / step) * step

        # Dynamic Broker Filling Mode Resolution
        filling_mode_flag = symbol_info.filling_mode
        if filling_mode_flag & 2:
            type_filling = mt5.ORDER_FILLING_IOC
        elif filling_mode_flag & 1:
            type_filling = mt5.ORDER_FILLING_FOK
        else:
            type_filling = mt5.ORDER_FILLING_RETURN

        # Check MT5 terminal automated trading permission
        term = mt5.terminal_info()
        if term and not term.trade_allowed:
            err_msg = "AutoTrading disabled by client in MT5 terminal (Enable 'Algo Trading' button in MT5 toolbar or press Ctrl+E)"
            logger.error(err_msg)
            return {"status": "ERROR", "reason": err_msg, "retcode": 10027}

        # === v5.1.0 (H-2 fix): Preserve scanner's comment (Banker/Runner tag) ===
        order_comment = ticket.get("comment", f"v5.1.0 {strat_type[:10]}")

        # Execution request
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": float(round(lots, 2)),
            "type": mt5_order_type,
            "price": float(round(price, digits)),
            "sl": float(round(sl_price, digits)),
            "tp": float(round(tp1_price, digits)),
            "deviation": 20,
            "magic": 300000,
            "comment": order_comment,
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": type_filling,
        }

        result = mt5.order_send(request)
        if result is None:
            err = mt5.last_error()
            return {"status": "ERROR", "reason": f"Order send failed. Code: {err}"}

        if result.retcode != mt5.TRADE_RETCODE_DONE:
            comment = result.comment or "Order rejected"
            if result.retcode == 10027 or "autotrading disabled" in comment.lower():
                comment = "AutoTrading disabled by client (Enable 'Algo Trading' button in MT5 toolbar or press Ctrl+E)"
            logger.error(f"Order failed: {comment} (code {result.retcode})")
            return {"status": "ERROR", "reason": comment, "retcode": result.retcode}

        return {
            "status": "SUCCESS",
            "ticket": result.order,
            "volume": request["volume"],
            "price": result.price,
            "sl": request["sl"],
            "tp1": request["tp"],
            "tp2": float(round(tp2_price, digits)),
            "tp3": float(round(tp3_price, digits)),
            "message": "Order executed successfully (v5.1.0)"
        }
    except Exception as e:
        logger.exception("Unexpected error in execute_mt5_order")
        return {"status": "ERROR", "reason": str(e)}


def modify_mt5_sl(ticket_id, new_sl):
    try:
        bridge.initialize()
        positions = mt5.positions_get(ticket=ticket_id)
        if not positions:
            return {"status": "ERROR", "reason": f"Position {ticket_id} not found"}
            
        pos = positions[0]
        digits = 2
        sym_info = mt5.symbol_info(pos.symbol)
        if sym_info:
            digits = sym_info.digits

        request = {
            "action": mt5.TRADE_ACTION_SLTP,
            "position": pos.ticket,
            "symbol": pos.symbol,
            "sl": float(round(new_sl, digits)),
            "tp": float(round(pos.tp, digits)) if pos.tp else 0.0,
            "magic": getattr(pos, "magic", 300000)
        }
        result = mt5.order_send(request)
        if result is None:
            return {"status": "ERROR", "reason": f"Modification failed. Code: {mt5.last_error()}"}
            
        if result.retcode != mt5.TRADE_RETCODE_DONE:
            return {"status": "ERROR", "reason": result.comment, "retcode": result.retcode}
            
        return {"status": "SUCCESS", "message": f"SL modified to {request['sl']} (v3.0.0)", "sl": request["sl"]}
    except Exception as e:
        return {"status": "ERROR", "reason": str(e)}


def close_position(ticket_id):
    try:
        bridge.initialize()
        positions = mt5.positions_get(ticket=ticket_id)
        if not positions:
            return {"status": "ERROR", "reason": f"Position {ticket_id} not found"}
            
        pos = positions[0]
        tick = mt5.symbol_info_tick(pos.symbol)
        sym_info = mt5.symbol_info(pos.symbol)
        filling_mode = sym_info.filling_mode if sym_info else 0
        if filling_mode & 2:
            type_filling = mt5.ORDER_FILLING_IOC
        elif filling_mode & 1:
            type_filling = mt5.ORDER_FILLING_FOK
        else:
            type_filling = mt5.ORDER_FILLING_RETURN
        
        if pos.type == mt5.ORDER_TYPE_BUY:
            type_mt5 = mt5.ORDER_TYPE_SELL
            price = tick.bid
        else:
            type_mt5 = mt5.ORDER_TYPE_BUY
            price = tick.ask
            
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "position": pos.ticket,
            "symbol": pos.symbol,
            "volume": pos.volume,
            "type": type_mt5,
            "price": price,
            "deviation": 20,
            "magic": 300000,
            "comment": "Close v3.0.0",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": type_filling,
        }
        result = mt5.order_send(request)
        if result is None:
            return {"status": "ERROR", "reason": f"Close failed. Code: {mt5.last_error()}"}
            
        if result.retcode != mt5.TRADE_RETCODE_DONE:
            return {"status": "ERROR", "reason": result.comment, "retcode": result.retcode}
            
        return {"status": "SUCCESS", "message": "Position closed (v3.0.0)"}
    except Exception as e:
        return {"status": "ERROR", "reason": str(e)}


def close_all_positions():
    try:
        bridge.initialize()
        positions = mt5.positions_get()
        if positions is None:
            return {"status": "ERROR", "reason": "Failed to get positions"}
            
        results = []
        for pos in positions:
            res = close_position(pos.ticket)
            results.append({"ticket": pos.ticket, "result": res})
            
        return {"status": "SUCCESS", "results": results, "message": "All positions closed (v3.0.0)"}
    except Exception as e:
        return {"status": "ERROR", "reason": str(e)}

if __name__ == "__main__":
    print("MT5 Connector v3.0.0 initialized.")
