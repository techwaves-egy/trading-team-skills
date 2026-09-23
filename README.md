# AI Autonomous Trading Firm — Skill Workspace (v3.0.0)

Institutional multi-agent AI trading organization engineered for live market analysis, automated regime detection, confirmation entry protocols, dynamic ATR volatility floors, 2-strike asset lockouts, dynamic strategy competition, quantitative risk management, order execution, dual In-Chat/Telegram approvals, real-time Take Profit & Stop Loss action guidance, native **MetaTrader 5 direct desktop execution**, and **TradingView webhooks**.

---

## 🏛️ Organizational Structure

The firm operates 16 coordinated specialist roles across 5 operational divisions:

```
├── 1. Executive & Governance:     Chief Trading Officer (CTO), Portfolio Manager, Trade Committee (9-Member Quorum)
├── 2. Market Intelligence:        Macro, Fundamental, Technical, Market Structure, News, Sentiment Analysts
├── 3. Quantitative & Statistical: Quant & Statistical Analyst, Volatility Analyst (ATR Floor Guard), Correlation Analyst
├── 4. Strategy & Regimes:         Market Regime Engine (Bi-Directional Agility), Strategy Selection Specialist
└── 5. Risk & Execution:           Risk Manager (Absolute Veto & 2-Strike Lockout), Execution & Position Management Agent
```

---

## 📂 Repository Layout

```
d:/Techwaves-egy/Trading Team Skills/
├── SKILL.md                               # Master Skill definition (v3.0.0) and primary orchestrator
├── README.md                              # Workspace overview, quick-start guide, and architecture
├── CHANGELOG.md                           # Version history (v1.0.0 → v3.0.0)
├── config/
│   ├── alert_config.json                  # Persistent multi-chat Telegram & Discord credentials
│   ├── broker_config.json                 # MetaTrader & Broker API configuration
│   └── session_state.json                 # Live session risk ceilings ($5, $100, etc.)
├── scripts/
│   ├── config_manager.py                  # CLI & programmatic manager to save/persist multi-chat credentials
│   ├── telegram_listener.py               # 24/7 two-way interactive background Telegram & MT5 listener daemon
│   ├── market_scanner.py                  # Automated periodic market sweep engine
│   ├── mt5_connector.py                   # Direct native MetaTrader 5 terminal connector (Execution & SL modifications)
│   ├── tradingview_bridge.py              # Inbound TradingView alert webhook server (Port 5000)
│   └── send_alert.py                      # Multi-channel dispatcher with TP1/TP2/SL manual action templates
├── docs/
│   ├── 01_ORGANIZATION_ROLES.md           # 16-role duties, committee voting precedence, and veto gates
│   ├── 02_REGIME_STRATEGY_ENGINE.md       # 10 regimes, 8 strategies, Confirmation Entry Protocol, bi-directional flips
│   ├── 03_RISK_ENGINE_POSITION_SIZING.md  # Dynamic ATR Volatility Floor (≥ 1.5x ATR), Hard Dollar Risk Ceilings, 2-Strike Lockout
│   ├── 04_EXECUTION_LIFECYCLE.md          # 9-state order lifecycle, Dual In-Chat & Telegram Approval flows
│   ├── 05_JOURNAL_PERFORMANCE.md          # Forensic executed & rejection JSON schemas, Sharpe/Sortino math
│   ├── 06_POSITION_MANAGEMENT_RULES.md    # 3-tier scale-out matrix (40/40/20), real-time TP/SL action alerts
│   ├── 07_MARKET_SCAN_UNIVERSE.md         # Master asset watchlists, 5 liquidity filters, trading sessions
│   ├── 08_BROKER_INTEGRATIONS.md          # MT4/5, Interactive Brokers, Binance API & simulated fallback
│   ├── 09_INTER_AGENT_COMMUNICATION.md    # Inter-agent message schemas, sequence flow, and pipeline handoffs
│   ├── 10_NOTIFICATION_CHANNELS.md        # Telegram multi-chat broadcasting, TP/SL alerts, interactive buttons
│   ├── 11_BACKGROUND_MONITORING_DAEMON.md # 24/7 Telegram listeners, periodic sweep engines, mobile commands
│   └── 12_METATRADER_TRADINGVIEW_INTEGRATION.md # Native MT5 connector, TradingView webhooks & Pine script
└── templates/
    ├── SESSION_INTAKE.md                  # Pre-flight 6-parameter questionnaire template
    ├── TRADE_DECISION_TICKET.md           # Candidate evaluation, multi-TP targets, and committee voting
    ├── TP_SL_ACTION_ALERTS.md             # Real-time milestone action guidance templates
    ├── SESSION_STATUS.md                  # Live telemetry dashboard and scale-out position tracker
    └── SESSION_SUMMARY.md                 # End-of-session comprehensive audit report
```

---

## ⚡ Quick-Start Integration Guide

### 1. Connecting MetaTrader 5 (MT5)
```bash
# 1. Install official MT5 package
pip install MetaTrader5

# 2. Open MT5 Desktop -> Tools -> Options -> Expert Advisors -> Allow Algorithmic Trading
# 3. Direct order execution is handled by:
python scripts/mt5_connector.py
```

### 2. Connecting TradingView Webhook
```bash
# 1. Start the local TradingView webhook bridge
python scripts/tradingview_bridge.py 5000

# 2. In TradingView Alert -> Webhook URL:
https://your-public-url/webhook
```
