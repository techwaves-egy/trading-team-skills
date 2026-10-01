#!/usr/bin/env python3
"""
AI Autonomous Trading Firm — Senior Macro & Economic News Analyzer (Role #8)
Specialized quantitative news analyzer that:
  1. Ingests real-time macroeconomic calendars (ForexFactory JSON/XML/CSV feeds) with local caching.
  2. Enforces mandatory high-impact news blackout windows (±30 mins) on trading assets.
  3. Synthesizes macro sentiment, Fed/ECB expectations, and yield impacts for Gold (XAUUSD) & FX.
  4. Generates direct, actionable executive advisory briefings for the Chief Risk Officer (CRO @wtalaat).
  5. Plugs into auto_scanner.py (Gate 0.02) and telegram_listener.py (/news, /macro).
"""

import sys
import os
import time
import json
import logging
import argparse
import urllib.request
import urllib.error
import xml.etree.ElementTree as ET
import csv
import io
from datetime import datetime, timezone, timedelta

# Ensure UTF-8 console output on Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.path.join(BASE_DIR, "scripts"))

from send_alert import broadcast_telegram, send_admin_telegram

CONFIG_DIR = os.path.join(BASE_DIR, "config")
CALENDAR_CACHE_FILE = os.path.join(CONFIG_DIR, "economic_calendar.json")
ALERT_CONFIG_FILE = os.path.join(CONFIG_DIR, "alert_config.json")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - NewsAnalyzer - %(levelname)s - %(message)s"
)
logger = logging.getLogger("NewsAnalyzer")


class NewsAnalyzer:
    """Senior Macro & Economic News Analyzer and CRO Advisory Engine."""

    FEED_JSON = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
    FEED_XML = "https://nfs.faireconomy.media/ff_calendar_thisweek.xml"
    FEED_CSV = "https://nfs.faireconomy.media/ff_calendar_thisweek.csv"

    def __init__(self, cache_ttl_hours=4.0):
        self.cache_ttl_hours = cache_ttl_hours
        self._last_retry_after_until = 0.0

    def _load_cache(self):
        """Load cached calendar from disk."""
        if os.path.exists(CALENDAR_CACHE_FILE):
            try:
                with open(CALENDAR_CACHE_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Error reading calendar cache: {e}")
        return None

    def _save_cache(self, events, source="ForexFactory"):
        """Save normalized events to disk cache."""
        try:
            os.makedirs(CONFIG_DIR, exist_ok=True)
            payload = {
                "last_updated_utc": datetime.now(timezone.utc).isoformat(),
                "source": source,
                "event_count": len(events),
                "events": events
            }
            with open(CALENDAR_CACHE_FILE, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2)
            logger.info(f"Cached {len(events)} economic events to {CALENDAR_CACHE_FILE}")
        except Exception as e:
            logger.error(f"Failed to save calendar cache: {e}")

    def fetch_calendar(self, force_refresh=False):
        """
        Fetch this week's economic events with multi-tier fallback:
        1. Local cache if fresh (< TTL) and not force_refresh.
        2. Remote JSON feed.
        3. Remote XML feed.
        4. Remote CSV feed.
        5. Existing local cache if remote calls fail or are rate-limited.
        """
        cached = self._load_cache()

        # Check cache freshness
        if cached and not force_refresh:
            try:
                last_updated = datetime.fromisoformat(cached.get("last_updated_utc"))
                age_hours = (datetime.now(timezone.utc) - last_updated).total_seconds() / 3600.0
                if age_hours < self.cache_ttl_hours and cached.get("events"):
                    logger.debug(f"Using cached calendar ({age_hours:.1f}h old, {len(cached['events'])} events)")
                    return cached["events"]
            except Exception:
                pass

        # Check Cloudflare rate limit backoff
        now_ts = time.time()
        if now_ts < self._last_retry_after_until:
            wait_rem = int(self._last_retry_after_until - now_ts)
            logger.warning(f"Remote calendar rate-limited. Backing off for {wait_rem}s. Using local cache.")
            if cached and cached.get("events"):
                return cached["events"]

        # Attempt remote fetch
        events = self._try_fetch_remote()
        if events:
            self._save_cache(events)
            return events

        # Fallback to existing cache if remote failed
        if cached and cached.get("events"):
            logger.warning("Remote calendar fetch failed; falling back to existing cache.")
            return cached["events"]

        logger.error("No calendar data available from remote feeds or local cache.")
        return []

    def _try_fetch_remote(self):
        """Attempt fetching from JSON, then XML, then CSV."""
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) TechwavesQuant/4.0"}

        # 1. Try JSON
        try:
            req = urllib.request.Request(self.FEED_JSON, headers=headers)
            with urllib.request.urlopen(req, timeout=8) as res:
                if res.status == 200:
                    raw = json.loads(res.read().decode("utf-8"))
                    events = self._normalize_json_events(raw)
                    if events:
                        logger.info(f"Successfully fetched {len(events)} events via JSON")
                        return events
        except urllib.error.HTTPError as e:
            if e.code == 429:
                retry_after = int(e.headers.get("Retry-After", 180))
                self._last_retry_after_until = time.time() + retry_after
                logger.warning(f"ForexFactory JSON returned 429 Too Many Requests (Retry-After: {retry_after}s)")
            else:
                logger.warning(f"JSON calendar fetch HTTP error: {e}")
        except Exception as e:
            logger.warning(f"JSON calendar fetch error: {e}")

        # 2. Try XML
        try:
            req = urllib.request.Request(self.FEED_XML, headers=headers)
            with urllib.request.urlopen(req, timeout=8) as res:
                if res.status == 200:
                    tree = ET.fromstring(res.read())
                    events = self._normalize_xml_events(tree)
                    if events:
                        logger.info(f"Successfully fetched {len(events)} events via XML")
                        return events
        except urllib.error.HTTPError as e:
            if e.code == 429:
                retry_after = int(e.headers.get("Retry-After", 180))
                self._last_retry_after_until = time.time() + retry_after
            logger.warning(f"XML calendar fetch HTTP error: {e}")
        except Exception as e:
            logger.warning(f"XML calendar fetch error: {e}")

        # 3. Try CSV
        try:
            req = urllib.request.Request(self.FEED_CSV, headers=headers)
            with urllib.request.urlopen(req, timeout=8) as res:
                if res.status == 200:
                    text_content = res.read().decode("utf-8", errors="replace")
                    events = self._normalize_csv_events(text_content)
                    if events:
                        logger.info(f"Successfully fetched {len(events)} events via CSV")
                        return events
        except Exception as e:
            logger.warning(f"CSV calendar fetch error: {e}")

        return None

    def _normalize_json_events(self, raw_events):
        """Normalize JSON events into standard structure."""
        events = []
        for e in raw_events:
            date_raw = e.get("date", "")
            dt_utc_iso = None
            if date_raw:
                try:
                    dt = datetime.fromisoformat(date_raw)
                    dt_utc_iso = dt.astimezone(timezone.utc).isoformat()
                except Exception:
                    pass

            events.append({
                "title": e.get("title", "").strip(),
                "country": e.get("country", "").strip().upper(),
                "impact": e.get("impact", "Low").strip(),
                "datetime_utc": dt_utc_iso,
                "forecast": e.get("forecast", "").strip(),
                "previous": e.get("previous", "").strip(),
                "url": e.get("url", "")
            })
        return events

    def _normalize_xml_events(self, tree):
        """Normalize XML events into standard structure."""
        events = []
        for item in tree.findall("event"):
            title = (item.findtext("title") or "").strip()
            country = (item.findtext("country") or "").strip().upper()
            date_str = (item.findtext("date") or "").strip()
            time_str = (item.findtext("time") or "").strip()
            impact = (item.findtext("impact") or "Low").strip()
            forecast = (item.findtext("forecast") or "").strip()
            previous = (item.findtext("previous") or "").strip()
            url = (item.findtext("url") or "").strip()

            dt_utc_iso = self._parse_date_time_to_utc(date_str, time_str)

            events.append({
                "title": title,
                "country": country,
                "impact": impact,
                "datetime_utc": dt_utc_iso,
                "forecast": forecast,
                "previous": previous,
                "url": url
            })
        return events

    def _normalize_csv_events(self, csv_text):
        """Normalize CSV events into standard structure."""
        events = []
        reader = csv.DictReader(io.StringIO(csv_text))
        for r in reader:
            title = r.get("Title", "").strip()
            country = r.get("Country", "").strip().upper()
            date_str = r.get("Date", "").strip()
            time_str = r.get("Time", "").strip()
            impact = r.get("Impact", "Low").strip()
            forecast = r.get("Forecast", "").strip()
            previous = r.get("Previous", "").strip()
            url = r.get("URL", "").strip()

            dt_utc_iso = self._parse_date_time_to_utc(date_str, time_str)

            events.append({
                "title": title,
                "country": country,
                "impact": impact,
                "datetime_utc": dt_utc_iso,
                "forecast": forecast,
                "previous": previous,
                "url": url
            })
        return events

    def _parse_date_time_to_utc(self, date_str, time_str):
        """Converts MM-DD-YYYY and 11:50pm (ForexFactory XML/CSV is in UTC) to ISO UTC."""
        if not date_str or not time_str:
            return None
        if "m" not in time_str.lower():
            return None  # Skip all-day or tentative
        try:
            full_str = f"{date_str} {time_str}"
            dt = datetime.strptime(full_str, "%m-%d-%Y %I:%M%p").replace(tzinfo=timezone.utc)
            return dt.isoformat()
        except Exception:
            return None

    @staticmethod
    def get_relevant_currencies(symbol):
        """Map asset symbol to affected economic currencies."""
        sym = symbol.upper()
        if "XAU" in sym or "GOLD" in sym:
            return ["USD"]
        elif "EURUSD" in sym:
            return ["USD", "EUR"]
        elif "GBPUSD" in sym:
            return ["USD", "GBP"]
        elif "USDJPY" in sym:
            return ["USD", "JPY"]
        elif "USDCAD" in sym:
            return ["USD", "CAD"]
        elif "AUDUSD" in sym:
            return ["USD", "AUD"]
        elif "BTC" in sym or "ETH" in sym or "CRYPTO" in sym:
            return ["USD"]
        return ["USD"]

    def get_events(self, symbol="XAUUSD", hours_ahead=24.0, min_impact="Medium"):
        """
        Get upcoming events for the symbol's relevant currencies within hours_ahead.
        min_impact: "Low", "Medium", or "High"
        """
        all_events = self.fetch_calendar()
        currencies = self.get_relevant_currencies(symbol)
        now_utc = datetime.now(timezone.utc)

        impact_ranks = {"Low": 1, "Medium": 2, "High": 3, "Holiday": 0}
        min_rank = impact_ranks.get(min_impact, 2)

        results = []
        for e in all_events:
            if e.get("country") not in currencies:
                continue

            rank = impact_ranks.get(e.get("impact", "Low"), 1)
            if rank < min_rank:
                continue

            dt_iso = e.get("datetime_utc")
            if not dt_iso:
                continue

            try:
                dt = datetime.fromisoformat(dt_iso)
                diff_sec = (dt - now_utc).total_seconds()
                diff_hours = diff_sec / 3600.0

                # Filter within window (-1 hour past to hours_ahead future)
                if -1.0 <= diff_hours <= hours_ahead:
                    e_copy = dict(e)
                    e_copy["diff_minutes"] = round(diff_sec / 60.0, 1)
                    e_copy["diff_hours"] = round(diff_hours, 2)
                    e_copy["datetime_obj"] = dt
                    results.append(e_copy)
            except Exception:
                continue

        results.sort(key=lambda x: x["diff_minutes"])
        return results

    def check_blackout(self, symbol="XAUUSD", blackout_mins_before=30, blackout_mins_after=15):
        """
        Evaluate if a High-Impact news event triggers an active trading blackout.
        Returns:
            (is_blackout: bool, active_event: dict or None, reason: str, minutes_to_event: float or None)
        """
        events = self.get_events(symbol=symbol, hours_ahead=2.0, min_impact="High")

        for e in events:
            diff_m = e["diff_minutes"]
            # Active window: between -blackout_mins_after (post-news) and +blackout_mins_before (pre-news)
            if -blackout_mins_after <= diff_m <= blackout_mins_before:
                if diff_m >= 0:
                    status_desc = f"RELEASING IN {int(diff_m)} MINS"
                else:
                    status_desc = f"RELEASED {int(abs(diff_m))} MINS AGO (POST-EVENT STABILIZATION)"

                reason = (
                    f"HIGH-IMPACT NEWS BLACKOUT: '{e['title']}' ({e['country']}) {status_desc}. "
                    f"Spread expansion & whipsaw protection enforced."
                )
                return True, e, reason, diff_m

        return False, None, "CLEAR: No Tier-1 events in blackout window.", None

    def get_cro_advisory(self, symbol="XAUUSD"):
        """
        Synthesize institutional macro intelligence and generate actionable strategic counsel
        for Chief Risk Officer @wtalaat.
        """
        now_utc = datetime.now(timezone.utc)
        currencies = self.get_relevant_currencies(symbol)

        # 1. Check Blackout
        is_blackout, blackout_event, blackout_reason, blackout_mins = self.check_blackout(symbol)

        # 2. Upcoming High and Medium events in 24 hours
        events_24h = self.get_events(symbol=symbol, hours_ahead=24.0, min_impact="Medium")
        high_events_24h = [e for e in events_24h if e.get("impact") == "High"]
        med_events_24h = [e for e in events_24h if e.get("impact") == "Medium"]

        # 3. Next high-impact catalyst
        next_high = high_events_24h[0] if high_events_24h else None

        # 4. Determine Threat Level
        if is_blackout:
            threat_level = "RED"
            threat_badge = "🔴 CRITICAL (NEWS BLACKOUT ACTIVE)"
            stance = "COMPLETE TRADE FREEZE"
        elif next_high and next_high["diff_minutes"] <= 120:
            threat_level = "YELLOW"
            threat_badge = f"🟡 ELEVATED WATCH ({next_high['title']} in {int(next_high['diff_minutes'])}m)"
            stance = "DEFENSIVE POSTURE (NO NEW BATCHES)"
        elif any(e["diff_minutes"] <= 30 for e in med_events_24h):
            threat_level = "YELLOW"
            threat_badge = "🟡 CAUTION (MEDIUM IMPACT RELEASE IMMINENT)"
            stance = "VOLATILITY WATCH"
        else:
            threat_level = "GREEN"
            threat_badge = "🟢 CLEAR SAILING (NORMAL QUANT SCAN)"
            stance = "CLEAR TO ENGAGE"

        # 5. Macro Mechanism & Institutional Context
        macro_context = self._generate_macro_context(symbol, next_high, high_events_24h)

        # 6. Strategic Advice for CRO
        cro_advice = self._generate_cro_advice(threat_level, is_blackout, blackout_event, next_high, symbol)

        return {
            "symbol": symbol,
            "currencies": currencies,
            "threat_level": threat_level,
            "threat_badge": threat_badge,
            "strategic_stance": stance,
            "is_blackout": is_blackout,
            "blackout_reason": blackout_reason,
            "next_high_event": next_high,
            "events_today_count": len(events_24h),
            "events_24h": events_24h,
            "macro_context": macro_context,
            "cro_advice": cro_advice,
            "current_utc": now_utc.strftime("%Y-%m-%d %H:%M:%S UTC"),
        }

    def _generate_macro_context(self, symbol, next_high, high_events):
        """Explain the financial mechanism impacting the traded instrument."""
        is_gold = "XAU" in symbol.upper() or "GOLD" in symbol.upper()

        if not next_high:
            if is_gold:
                return (
                    "Macro calendar is quiet over the next 24 hours. Gold is driven by prevailing "
                    "technical structure, 20-period Bollinger Band mean reversion, and intermarket US Dollar "
                    "index (DXY) drift. Institutional liquidity is clean with minimal headline risk."
                )
            return "Macro calendar is clear of Tier-1 shocks. Technical setups have high fidelity."

        title = next_high["title"].lower()
        if "cpi" in title or "inflation" in title or "pce" in title:
            return (
                f"Upcoming catalyst '{next_high['title']}' is a Tier-1 inflation driver. "
                "Higher inflation prints push US 10-Year Real Yields upward, bolstering the US Dollar and "
                "triggering sharp downward algorithmic liquidation on Gold. Conversely, softer inflation "
                "ignites immediate safe-haven bullion surges."
            )
        elif "non-farm" in title or "unemployment" in title or "employment" in title or "jobless" in title:
            return (
                f"Upcoming catalyst '{next_high['title']}' dictates Federal Reserve rate expectations. "
                "Strong labor data delays monetary easing expectations (bearish Gold / bullish USD). "
                "Subdued labor prints accelerate rate-cut pricing, triggering explosive upside rallies in Gold."
            )
        elif "fomc" in title or "fed" in title or "powell" in title or "interest rate" in title:
            return (
                f"Central Bank event '{next_high['title']}' carries maximum systemic volatility. "
                "Expect rapid multi-hundred-pip whipsaws, severe liquidity pool purges, and spread widening "
                "across all Dollar-denominated pairs."
            )
        elif "pmi" in title:
            return (
                f"Catalyst '{next_high['title']}' measures manufacturing/services expansion. "
                "Contractionary readings (<50.0) heighten economic growth concerns, weakening USD and "
                "offering modest structural tailwinds for Gold."
            )
        else:
            return (
                f"Upcoming event '{next_high['title']}' carries elevated volatility potential. "
                "Expect localized liquidity gaps and spread expansion at release time."
            )

    def _generate_cro_advice(self, threat_level, is_blackout, blackout_event, next_high, symbol):
        """Generate specific directives for CRO @wtalaat."""
        if threat_level == "RED":
            event_name = blackout_event['title'] if blackout_event else "High Impact News"
            return [
                f"🛑 VETO NEW ORDERS: Strictly halt automated order submissions for {symbol}.",
                f"⚠️ BLACKOUT ACTIVE: '{event_name}' in progress or imminent within ±30 mins.",
                "🔒 PROTECT OPEN CAPITAL: Check open positions in MT5. Ensure Server-Side 80/70 SL is armed or close manually.",
                "⏱️ RE-EVALUATE: Wait 15 minutes post-release for spread normalization before resuming scans."
            ]
        elif threat_level == "YELLOW":
            mins_left = int(next_high['diff_minutes']) if next_high else 45
            return [
                f"⚠️ ELEVATED THREAT: '{next_high['title']}' scheduled in {mins_left} minutes.",
                "📉 RESTRICT SIZING: Block multi-order batches (3x/5x). Permit only single 0.01 micro-lots if setup qualifies.",
                "🛡️ HARD PROFIT LOCK: If existing trades reach 70% TP, immediately clamp stops at break-even.",
                "⏱️ SHUTDOWN COUNTDOWN: Prepare to enter complete scanning freeze 30 minutes before release."
            ]
        else:
            return [
                "✅ GREEN LIGHT: No Tier-1 macroeconomic hazards detected within the next 2+ hours.",
                "🎯 STRATEGY DEPLOYMENT: Full algorithmic clearance for Bollinger Mean Reversion (v4.0.0).",
                "📊 CAPITAL SIZING: Standard equity-scaled batch sizing authorized (1x to 5x based on account balance).",
                "🛡️ PROFIT PROTECTION: Maintain standard 80/70 Server-Side Broker SL and closed-candle reversal gates."
            ]

    def format_telegram_advisory(self, symbol="XAUUSD"):
        """Format the full CRO advisory as an institutional Telegram HTML alert."""
        adv = self.get_cro_advisory(symbol)

        lines = [
            f"📰 <b>MACRO INTELLIGENCE & CRO ADVISORY</b>",
            f"<b>Role:</b> Senior Macro & Economic News Analyzer (#8)",
            f"<b>Administrator & CRO:</b> <code>@wtalaat</code>",
            f"━━━━━━━━━━━━━━━━━━━━",
            f"<b>Asset:</b> <code>{adv['symbol']}</code> (Risk Currency: <code>{', '.join(adv['currencies'])}</code>)",
            f"<b>Time (UTC):</b> <code>{adv['current_utc']}</code>",
            f"<b>Threat Level:</b> <b>{adv['threat_badge']}</b>",
            f"<b>Mandated Stance:</b> <b>{adv['strategic_stance']}</b>",
            f"━━━━━━━━━━━━━━━━━━━━"
        ]

        # Upcoming Releases section
        lines.append("📅 <b>UPCOMING ECONOMIC RELEASES (24H):</b>")
        if adv["events_24h"]:
            for e in adv["events_24h"][:6]:
                imp_icon = "🔴" if e.get("impact") == "High" else "🟡"
                diff_str = f"in {int(e['diff_minutes'])}m" if e["diff_minutes"] > 0 else f"{int(abs(e['diff_minutes']))}m ago"
                dt_time = e.get("datetime_obj").strftime("%H:%M UTC") if e.get("datetime_obj") else "TBD"
                f_p = f" (F: {e['forecast']} | P: {e['previous']})" if e.get("forecast") or e.get("previous") else ""
                lines.append(f"• {imp_icon} <code>{dt_time}</code> [{e['country']}] <b>{e['title']}</b> ({diff_str}){f_p}")
        else:
            lines.append("<i>• No High/Medium releases scheduled in next 24 hours. Clean runway.</i>")

        lines.append("━━━━━━━━━━━━━━━━━━━━")
        lines.append("💡 <b>INSTITUTIONAL MACRO MECHANISM:</b>")
        lines.append(f"<i>{adv['macro_context']}</i>")
        lines.append("━━━━━━━━━━━━━━━━━━━━")
        lines.append("🎯 <b>DIRECTIVES FOR CRO @wtalaat:</b>")
        for directive in adv["cro_advice"]:
            lines.append(f"• {directive}")
        lines.append("━━━━━━━━━━━━━━━━━━━━")
        lines.append("<i>AI Autonomous Trading Firm • Macro & News Intelligence Engine v4.1.0</i>")

        return "\n".join(lines)

    def broadcast_cro_advisory(self, symbol="XAUUSD"):
        """Send advisory directly to CRO @wtalaat."""
        message = self.format_telegram_advisory(symbol)
        send_admin_telegram(message)
        logger.info(f"Delivered Macro Advisory to CRO @wtalaat for {symbol}")
        return True


# Convenience module-level functions for integration
_global_analyzer = None

def get_analyzer():
    global _global_analyzer
    if _global_analyzer is None:
        _global_analyzer = NewsAnalyzer()
    return _global_analyzer

def check_news_blackout(symbol="XAUUSD"):
    """Quick check for auto_scanner.py Gate 0.02."""
    analyzer = get_analyzer()
    return analyzer.check_blackout(symbol)

def get_cro_advisory(symbol="XAUUSD"):
    """Quick advisory retrieval for telegram_listener.py."""
    analyzer = get_analyzer()
    return analyzer.get_cro_advisory(symbol)

def broadcast_news_advisory(symbol="XAUUSD"):
    """Direct broadcast to CRO."""
    analyzer = get_analyzer()
    return analyzer.broadcast_cro_advisory(symbol)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AI Autonomous Trading Firm — Macro & News Analyzer")
    parser.add_argument("--symbol", default="XAUUSD", help="Asset symbol to analyze (default: XAUUSD)")
    parser.add_argument("--alert", action="store_true", help="Broadcast full advisory to CRO @wtalaat on Telegram")
    parser.add_argument("--refresh", action="store_true", help="Force refresh calendar cache from remote feeds")
    parser.add_argument("--json", action="store_true", help="Output raw advisory JSON")
    args = parser.parse_args()

    analyzer = NewsAnalyzer()
    if args.refresh:
        analyzer.fetch_calendar(force_refresh=True)

    if args.json:
        adv = analyzer.get_cro_advisory(args.symbol)
        # Convert non-serializable objects
        adv_clean = {k: v for k, v in adv.items() if k != "events_24h"}
        adv_clean["events_24h"] = [{k: str(v) for k, v in e.items()} for e in adv["events_24h"]]
        print(json.dumps(adv_clean, indent=2))
    elif args.alert:
        analyzer.broadcast_cro_advisory(args.symbol)
        print("[OK] Macro Advisory successfully delivered to CRO @wtalaat on Telegram.")
    else:
        text_report = analyzer.format_telegram_advisory(args.symbol)
        # Strip HTML tags for clean console display
        import re
        clean_cli = re.sub(r"<[^>]+>", "", text_report)
        print(clean_cli)
