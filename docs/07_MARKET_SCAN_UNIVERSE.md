# Market Scan Universe, Watchlists & Liquidity Standards

The Market Intelligence Team uses pre-defined asset universes, session trading windows, and strict liquidity filters before submitting candidate instruments to the quantitative engine.

---

## 1. Master Asset Universes

```text
+-------------------------------------------------------------------------------+
|                            QUALIFIED TRADING UNIVERSE                         |
+-------------------------------------------------------------------------------+
| 1. FOREX (Major & Select Minor Pairs):                                        |
|    - Majors: EURUSD, GBPUSD, USDJPY, AUDUSD, USDCAD, USDCHF, NZDUSD           |
|    - Minors / Crosses: EURGBP, EURJPY, GBPJPY, AUDJPY, EURAUD, GBPAUD         |
|                                                                               |
| 2. PRECIOUS METALS & COMMODITIES:                                             |
|    - Metals: XAUUSD (Gold), XAGUSD (Silver), XPTUSD (Platinum)                |
|    - Energies: USOIL (WTI Crude), UKOIL (Brent Crude), NGAS (Natural Gas)      |
|                                                                               |
| 3. CRYPTOCURRENCIES (High Liquidity Spot & Perpetual Futures):                |
|    - Tier 1: BTCUSDT, ETHUSDT, SOLUSDT                                        |
|    - Tier 2: BNBUSDT, XRPUSDT, ADAUSDT, AVAXUSDT, LINKUSDT, NEARUSDT, SUIUSDT  |
|                                                                               |
| 4. GLOBAL INDICES:                                                            |
|    - US: US500 (S&P 500), US30 (Dow Jones), USTEC / NAS100 (Nasdaq 100)       |
|    - Global: GER40 (DAX), UK100 (FTSE 100), JP225 (Nikkei 225)                 |
|                                                                               |
| 5. EQUITIES & STOCKS (Liquid Mega-Cap / Large-Cap):                           |
|    - Tech: AAPL, MSFT, NVDA, GOOGL, AMZN, META, TSLA                         |
|    - Financial / Industrial: JPM, GS, CAT, UNH, LLY                           |
+-------------------------------------------------------------------------------+
```

---

## 2. Universal Liquidity & Spread Filtering Criteria

Before any instrument enters the scanning pipeline, it must satisfy all 5 liquidity filters:

| # | Metric | Minimum Acceptable Threshold | Action if Violated |
| :- | :--- | :--- | :--- |
| 1 | **Max Spread-to-ATR Ratio** | $\text{Spread} \le 0.10 \times \text{15M ATR}$ | Filter Out (Spread too wide) |
| 2 | **24-Hour Trading Volume** | Forex/Indices: High Institutional Flow \| Crypto: $> \$50\text{M}$ Daily Spot/Perp | Filter Out (Low liquidity) |
| 3 | **Order Book Depth** | Top 5 book levels must absorb calculated position with $< 0.02\%$ slippage | Reject Market Orders; use Limits only |
| 4 | **Data Feed Tick Rate** | Minimum 5 price updates per second during active market hours | Filter Out (Sparse / Stale data) |
| 5 | **Instrument Trading Status & Margin** | Market Status = `OPEN` (Trading Enabled) and Margin Multiplier = Normal | Filter Out (Session closed or margin spike) |

---

## 3. Global Trading Sessions & Optimal Windows (UTC)

| Trading Session | Time Window (UTC) | Peak Volatility & Focus Asset Classes |
| :--- | :--- | :--- |
| **Asian Session (Tokyo / Sydney)** | 00:00 – 08:00 UTC | JPY, AUD, NZD, Crypto |
| **London / European Open** | 07:00 – 16:00 UTC | EUR, GBP, CHF, Gold (XAUUSD), GER40, UK100 |
| **London / New York Overlap** | **12:00 – 16:00 UTC (PEAK)** | **All Forex Majors, Gold, Oil, Indices (US500, NAS100), US Equities** |
| **New York Afternoon** | 16:00 – 21:00 UTC | US Equities, Indices, USD Pairs, Crypto |
| **Crypto 24/7 Window** | Continuous | Optimal execution: 12:00 – 20:00 UTC (aligns with global liquidity) |

---

## 4. Blacklisted & Prohibited Instruments

Under no circumstances may the Autonomous Trading Firm open trades on:
1. **Exotic Currency Pairs**: E.g., USDTRY, USDZAR, USDRUB, EURTRY (erratic spreads, asymmetric overnight swap fees).
2. **Illiquid Small-Cap / Micro-Cap Crypto**: Daily volume $< \$20\text{M}$, low liquidity, high rug-pull / flash-crash vulnerability.
3. **Penny Stocks / Over-The-Counter (OTC) Securities**: Price $< \$5.00$ or unlisted on major exchanges (NYSE, NASDAQ).
4. **Leveraged Inverse / 3x Decay ETFs**: E.g., SQQQ, UVXY (unless held for strictly intraday volatility hedging).
