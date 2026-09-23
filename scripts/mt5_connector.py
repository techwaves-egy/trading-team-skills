import MetaTrader5 as mt5
import json
import logging
import time
import math
from datetime import datetime, timedelta
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

def get_session_state():
    config_path = r"d:\Techwaves-egy\Trading Team Skills\config\session_state.json"
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

def update_loss_tracker(symbol):
    """Checks recent deal history to update the 2-Strike lockout tracker."""
    bridge.initialize()
    now = datetime.now()
    from_date = now - timedelta(days=1)
    deals = mt5.history_deals_get(from_date, now, group=f"*{symbol}*")
    
    if not deals:
        return

    # Look at the most recent closed deal for the symbol
    out_deals = [d for d in deals if d.entry == mt5.DEAL_ENTRY_OUT or d.entry == mt5.DEAL_ENTRY_OUT_BY]
    if not out_deals:
        return
        
    last_deal = sorted(out_deals, key=lambda x: x.time)[-1]
    
    if symbol not in _loss_tracker:
        _loss_tracker[symbol] = {'count': 0, 'locked_until': None}
        
    if last_deal.profit < 0:
        if getattr(update_loss_tracker, "last_processed_deal", {}).get(symbol) == last_deal.ticket:
            return
            
        _loss_tracker[symbol]['count'] += 1
        if getattr(update_loss_tracker, "last_processed_deal", None) is None:
            update_loss_tracker.last_processed_deal = {}
        update_loss_tracker.last_processed_deal[symbol] = last_deal.ticket
        
        logger.info(f"Loss detected on {symbol}. Consecutive losses: {_loss_tracker[symbol]['count']}")
        
        if _loss_tracker[symbol]['count'] >= 2:
            _loss_tracker[symbol]['locked_until'] = datetime.now() + timedelta(minutes=60)
            logger.warning(f"Asset {symbol} locked for 60 minutes due to 2 consecutive losses.")
    elif last_deal.profit > 0:
        _loss_tracker[symbol]['count'] = 0
        if getattr(update_loss_tracker, "last_processed_deal", None) is None:
            update_loss_tracker.last_processed_deal = {}
        update_loss_tracker.last_processed_deal[symbol] = last_deal.ticket

def check_asset_lockout(symbol):
    """2-Strike Asset Lockout Enforcement"""
    update_loss_tracker(symbol)
    if symbol in _loss_tracker:
        tracker = _loss_tracker[symbol]
        if tracker['count'] >= 2 and tracker['locked_until'] is not None:
            if datetime.now() < tracker['locked_until']:
                return True, f"Asset locked until {tracker['locked_until']}"
            else:
                _loss_tracker[symbol] = {'count': 0, 'locked_until': None}
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
    Risk-Validated Order Execution Engine - v3.1.0
    """
    try:
        bridge.initialize()
        
        symbol = ticket.get("symbol")
        if not symbol:
            return {"status": "ERROR", "reason": "Symbol missing in ticket."}
            
        order_type_str = ticket.get("order_type", "BUY").upper()
        
        # 0. Asset Policy Disablement Gate
        if symbol.upper() == "USDJPY":
            reason = "ASSET POLICY: USDJPY is disabled due to negative empirical expectancy (7-Year Benchmark PF 0.75)."
        # 0.0 Anti-Tamper & Skill Integrity Gate
        from skill_integrity_guard import verify_skill_integrity
        is_intact, discrepancies = verify_skill_integrity(silent=False)
        if not is_intact:
            reason = f"SECURITY VIOLATION: Skill integrity check failed. Trade blocked."
            logger.critical(reason)
            return {"status": "REJECTED", "reason": reason}

        # 0.1 Anti-Stacking Gate: Check if an open position already exists for this symbol
        open_pos = mt5.positions_get(symbol=symbol)
        if open_pos and len(open_pos) > 0:
            reason = f"ANTI-STACKING: Position already open on {symbol} (Ticket #{open_pos[0].ticket}). Multiple entries blocked."
            logger.warning(f"Order REJECTED: {reason}")
            return {"status": "REJECTED", "reason": reason}
        
        # 6. Multi-Timeframe Regime Detection
        regime = detect_regime(symbol)
        logger.info(f"[{symbol}] Multi-Timeframe Regime: {regime}")
        
        # 5. 2-Strike Asset Lockout Check
        locked, lock_reason = check_asset_lockout(symbol)
        if locked:
            logger.warning(f"Order REJECTED: {lock_reason}")
            return {"status": "REJECTED", "reason": lock_reason}
            
        # 4. Strategy-Aware Confirmation Entry & Trap Filter Gate
        strat_type = ticket.get("strategy", "Structural_Trend_Breakout")
        if strat_type != "Bollinger_Mean_Reversion":
            confirmed, conf_reason = check_confirmation(symbol, order_type_str)
            if not confirmed:
                logger.warning(f"Order REJECTED: {conf_reason}")
                return {"status": "REJECTED", "reason": conf_reason}
        else:
            logger.info(f"[{symbol}] Bollinger Mean Reversion strategy validated by scanner. Proceeding to execution.")
            
        # 2. Real ATR Calculation
        atr = calculate_atr(symbol, mt5.TIMEFRAME_H1, 14)
        if atr is None:
            return {"status": "ERROR", "reason": "Failed to calculate ATR"}
            
        symbol_info = mt5.symbol_info(symbol)
        if symbol_info is None:
            return {"status": "ERROR", "reason": f"Symbol {symbol} not found"}
            
        point = symbol_info.point
        tick_info = mt5.symbol_info_tick(symbol)
        if tick_info is None:
            return {"status": "ERROR", "reason": f"Failed to get tick info for {symbol}"}
            
        # Stop Distance logic
        if "sl" in ticket and ticket["sl"] > 0:
            if order_type_str == "BUY":
                price = tick_info.ask
                sl_dist = price - ticket["sl"]
            else:
                price = tick_info.bid
                sl_dist = ticket["sl"] - price
        else:
            price = tick_info.ask if order_type_str == "BUY" else tick_info.bid
            sl_dist = 2.0 * atr

        # 3. ATR Volatility Floor Enforcement
        min_safe = 1.5 * atr
        if sl_dist < min_safe:
            # Adjust if slightly under floor
            sl_dist = min_safe

        # 7. Point-Based SL/TP Calculation & 8. Multi-TP Support
        is_gold = "XAU" in symbol or "GOLD" in symbol
        sl_points = sl_dist / point
        if is_gold:
            tp1_dist = 25.00 # Target $25 profit ($20-$30 window)
            tp2_dist = 30.00
            tp3_dist = 35.00
        else:
            tp1_dist = 1.0 * sl_dist # Fast 1.0R initial target
            tp2_dist = 2.0 * sl_dist
            tp3_dist = 3.0 * sl_dist
        
        if order_type_str == "BUY":
            sl_price = price - sl_dist
            tp1_price = ticket.get("tp", price + tp1_dist)
            tp2_price = price + tp2_dist
            tp3_price = price + tp3_dist
            mt5_order_type = mt5.ORDER_TYPE_BUY
        else:
            sl_price = price + sl_dist
            tp1_price = ticket.get("tp", price - tp1_dist)
            tp2_price = price - tp2_dist
            tp3_price = price - tp3_dist
            mt5_order_type = mt5.ORDER_TYPE_SELL
            
        # 9. Dollar Risk Ceiling & Lot Sizing
        state = get_session_state()
        risk_dollars = float(state.get("risk_per_trade_dollars", state.get("risk_amount", 5.0)))
        contract_size = symbol_info.trade_contract_size if symbol_info.trade_contract_size > 0 else 100.0

        # Prioritize explicit lots passed in ticket (e.g. from auto_scanner)
        ticket_lots = ticket.get("lots") or ticket.get("volume")
        if ticket_lots and float(ticket_lots) > 0:
            lots = float(ticket_lots)
        else:
            if sl_dist > 0 and contract_size > 0:
                lots = risk_dollars / (sl_dist * contract_size)
            else:
                lots = symbol_info.volume_min

        # Clamp lots to min/max/step
        lots = max(symbol_info.volume_min, min(symbol_info.volume_max, lots))
        step = symbol_info.volume_step
        if step > 0:
            lots = round(lots / step) * step
            
        # Hard sanity limit: For micro/mini accounts, cap at 0.10 lots max to prevent account drain
        lots = min(lots, 0.10)

        # Dynamic Broker Filling Mode Resolution
        filling_mode_flag = symbol_info.filling_mode
        if filling_mode_flag & 2: # IOC supported
            type_filling = mt5.ORDER_FILLING_IOC
        elif filling_mode_flag & 1: # FOK supported
            type_filling = mt5.ORDER_FILLING_FOK
        else:
            type_filling = mt5.ORDER_FILLING_RETURN

        # Digits precision rounding
        digits = symbol_info.digits

        # Execution request
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": float(round(lots, 2)),
            "type": mt5_order_type,
            "price": float(round(price, digits)),
            "sl": float(round(sl_price, digits)),
            "tp": float(round(tp1_price, digits)), # Initial TP at TP1
            "deviation": 20,
            "magic": 300000,
            "comment": f"v3.4.0 {strat_type[:10]}",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": type_filling,
        }
        
        result = mt5.order_send(request)
        if result is None:
            err = mt5.last_error()
            return {"status": "ERROR", "reason": f"Order send failed. Code: {err}"}
            
        if result.retcode != mt5.TRADE_RETCODE_DONE:
            logger.error(f"Order failed: {result.comment} (code {result.retcode})")
            return {"status": "ERROR", "reason": result.comment, "retcode": result.retcode}
            
        return {
            "status": "SUCCESS",
            "ticket": result.order,
            "volume": request["volume"],
            "price": result.price,
            "sl": request["sl"],
            "tp1": request["tp"],
            "tp2": float(tp2_price),
            "tp3": float(tp3_price),
            "message": "Order executed successfully (v3.0.0)"
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
        request = {
            "action": mt5.TRADE_ACTION_SLTP,
            "position": pos.ticket,
            "symbol": pos.symbol,
            "sl": float(new_sl),
            "tp": float(pos.tp),
            "magic": 300000
        }
        result = mt5.order_send(request)
        if result is None:
            return {"status": "ERROR", "reason": f"Modification failed. Code: {mt5.last_error()}"}
            
        if result.retcode != mt5.TRADE_RETCODE_DONE:
            return {"status": "ERROR", "reason": result.comment, "retcode": result.retcode}
            
        return {"status": "SUCCESS", "message": "SL modified (v3.0.0)"}
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
