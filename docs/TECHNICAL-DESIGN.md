# Stock Risk Intelligence Platform - Technical Design

## Executive Summary

A comprehensive **Stock Risk Intelligence Platform** that provides real-time monitoring, automated buy/sell signals, and portfolio risk management for all major US stocks, powered by SEC filings, price data, and AI analysis.

---

## Table of Contents

1. [Vision & Goals](#vision--goals)
2. [Architecture Overview](#architecture-overview)
3. [Phase Breakdown](#phase-breakdown)
4. [Data Models](#data-models)
5. [Component Specifications](#component-specifications)
6. [ML/AI Strategy](#mlai-strategy)
7. [API Design](#api-design)
8. [Infrastructure & Operations](#infrastructure--operations)
9. [Testing Strategy](#testing-strategy)
10. [Migration Plan](#migration-plan)

---

## Vision & Goals

### Vision
A single platform where any investor can get real-time risk intelligence on US stocks, powered by SEC filings, price data, and AI analysis.

### Goals

| Goal | Metric | Target |
|------|--------|--------|
| Coverage | Stocks monitored | 500+ (S&P 500 baseline) |
| Freshness | Time to detect new filing | < 1 hour |
| Accuracy | Signal accuracy (backtested) | > 65% |
| Engagement | Monthly Active Users | 1000+ (Apify challenge) |
| Reliability | Uptime | 99%+ |

### Non-Goals (Explicitly Out of Scope)
- Real-time trading execution
- Financial advice (we provide signals, not advice)
- Cryptocurrency or forex
- International stocks (US SEC filings only)

---

## Architecture Overview

### System Context Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              EXTERNAL SYSTEMS                                │
├─────────────────────────────────────────────────────────────────────────────┤
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐│
│  │ SEC EDGAR   │  │Yahoo Finance│  │ Wikipedia   │  │ Users/Integrations ││
│  │ • 8-K feeds │  │ • Prices    │  │ • S&P 500   │  │ • Slack            ││
│  │ • Form 4    │  │ • Volume    │  │ • NASDAQ100 │  │ • Zapier           ││
│  │ • Full text │  │ • History   │  │ • Indices   │  │ • Webhooks         ││
│  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘  └─────────┬───────────┘│
└─────────┼────────────────┼────────────────┼────────────────────┼────────────┘
          │                │                │                    │
          ▼                ▼                ▼                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                        STOCK RISK INTELLIGENCE PLATFORM                      │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌────────────────────────────────────────────────────────────────────────┐ │
│  │                         INGESTION LAYER                                 │ │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐                 │ │
│  │  │StockUniverse │  │ SECCollector │  │PriceCollector│                 │ │
│  │  │  Collector   │  │  (existing)  │  │   (new)      │                 │ │
│  │  └──────────────┘  └──────────────┘  └──────────────┘                 │ │
│  └────────────────────────────────────────────────────────────────────────┘ │
│                                    │                                         │
│                                    ▼                                         │
│  ┌────────────────────────────────────────────────────────────────────────┐ │
│  │                         ANALYSIS LAYER                                  │ │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐                 │ │
│  │  │ LLMAnalyzer  │  │ PriceAnalyzer│  │TrendAnalyzer │                 │ │
│  │  │  (existing)  │  │    (new)     │  │    (new)     │                 │ │
│  │  └──────────────┘  └──────────────┘  └──────────────┘                 │ │
│  └────────────────────────────────────────────────────────────────────────┘ │
│                                    │                                         │
│                                    ▼                                         │
│  ┌────────────────────────────────────────────────────────────────────────┐ │
│  │                         SCORING LAYER                                   │ │
│  │  ┌──────────────────────────────────────────────────────────────────┐  │ │
│  │  │                    CompositeScorer                                │  │ │
│  │  │  • SEC Risk Score (existing)                                     │  │ │
│  │  │  • Price Momentum Score (new)                                    │  │ │
│  │  │  • Trend Score (new)                                             │  │ │
│  │  │  • Combined Signal: BUY/HOLD/SELL                                │  │ │
│  │  └──────────────────────────────────────────────────────────────────┘  │ │
│  └────────────────────────────────────────────────────────────────────────┘ │
│                                    │                                         │
│                                    ▼                                         │
│  ┌────────────────────────────────────────────────────────────────────────┐ │
│  │                         PERSISTENCE LAYER                               │ │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐                 │ │
│  │  │  Historical  │  │   Alerts     │  │   Cache      │                 │ │
│  │  │   Scores     │  │    State     │  │  (CIK, etc)  │                 │ │
│  │  └──────────────┘  └──────────────┘  └──────────────┘                 │ │
│  └────────────────────────────────────────────────────────────────────────┘ │
│                                    │                                         │
│                                    ▼                                         │
│  ┌────────────────────────────────────────────────────────────────────────┐ │
│  │                         OUTPUT LAYER                                    │ │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐                 │ │
│  │  │   Dataset    │  │   Alerts     │  │  Reports     │                 │ │
│  │  │  (per run)   │  │  (webhook)   │  │ (markdown)   │                 │ │
│  │  └──────────────┘  └──────────────┘  └──────────────┘                 │ │
│  └────────────────────────────────────────────────────────────────────────┘ │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Directory Structure

```
src/
├── __init__.py
├── __main__.py
├── main.py                      # Actor entry point
├── config/
│   ├── __init__.py
│   └── settings.py              # Configuration management
├── collectors/                   # Data ingestion
│   ├── __init__.py
│   ├── base.py                  # BaseCollector interface
│   ├── sec_collector.py         # SEC EDGAR (existing)
│   ├── stock_universe.py        # S&P 500, NASDAQ, etc. (Phase 1)
│   ├── price_collector.py       # Yahoo Finance (Phase 4)
│   └── firehose_collector.py    # Real-time SEC feed (Phase 5)
├── analyzers/                    # Analysis logic
│   ├── __init__.py
│   ├── llm_analyzer.py          # LLM-based analysis (existing)
│   ├── price_analyzer.py        # Price/momentum analysis (Phase 4)
│   ├── trend_analyzer.py        # Historical trend analysis (Phase 3)
│   └── prompts.py               # LLM prompts
├── scoring/                      # Scoring algorithms
│   ├── __init__.py
│   ├── rule_scorer.py           # Rule-based scoring (existing)
│   ├── composite_scorer.py      # Combined signals (Phase 4)
│   └── signal_generator.py      # BUY/SELL signals (Phase 4)
├── storage/                      # Persistence (Phase 3)
│   ├── __init__.py
│   ├── historical_store.py      # Historical scores
│   └── alert_store.py           # Alert state management
├── services/                     # Orchestration
│   ├── __init__.py
│   ├── risk_scanner.py          # Main scanner service (existing)
│   ├── webhook_service.py       # Webhook alerts (existing)
│   └── scheduler_service.py     # Scheduling logic (Phase 2)
├── formatters/                   # Output formatting
│   ├── __init__.py
│   ├── json_formatter.py        # JSON output (existing)
│   ├── markdown_formatter.py    # Reports (existing)
│   └── webhook_formatter.py     # Alert payloads (existing)
└── core/                         # Shared code
    ├── __init__.py
    ├── interfaces.py             # Abstract base classes
    ├── models.py                 # Data models
    └── exceptions.py             # Custom exceptions
```

---

## Phase Breakdown

### Phase 1: Stock Universe Auto-Scan
**Status**: Pending | **Effort**: 1 day | **MAU Impact**: High

**Goal**: Scan all S&P 500 stocks in a single run instead of user-provided tickers.

**New Files**:
- `src/collectors/stock_universe.py`

**Changes**:
- New input mode: `scanMode: "sp500" | "nasdaq100" | "custom"`
- Batch processing with rate limiting

**Acceptance Criteria**:
- [ ] Can scan all 500 S&P 500 stocks in <10 minutes
- [ ] Rate limiting prevents SEC throttling
- [ ] Progress reporting during long scans

---

### Phase 2: Scheduling Infrastructure
**Status**: Pending | **Effort**: 1 day | **MAU Impact**: High

**Goal**: Enable recurring scans with state management.

**New Files**:
- `src/services/scheduler_service.py`
- `src/storage/run_state.py`

**Key Features**:
- Incremental scanning (only new filings since last run)
- State persistence across runs
- Delta processing

**Acceptance Criteria**:
- [ ] Scheduled runs only process new filings
- [ ] State persists across runs
- [ ] Can resume from failure

---

### Phase 3: Historical Backfill + Factors + ML Model
**Status**: Pending | **Effort**: 3-4 days | **MAU Impact**: Very High

**Goal**: Backfill 2 years of historical data, collect factors with time lags, train ML model.

**New Files**:
- `src/collectors/factor_collector.py` - FRED, Yahoo Finance factors
- `src/storage/historical_store.py` - Store historical data
- `src/analyzers/trend_analyzer.py` - Trend calculations
- `src/ml/__init__.py`
- `src/ml/features.py` - Feature engineering with lags
- `src/ml/backtest.py` - Historical backtesting
- `src/ml/model.py` - XGBoost/LightGBM model
- `src/ml/predictor.py` - Real-time predictions

**Factor Sources**:
| Source | Factors |
|--------|---------|
| FRED | Fed Rate, Inflation, Unemployment, GDP, Treasury Spread |
| Yahoo Finance | VIX, S&P 500, P/E, Market Cap, RSI, Prices |
| SEC EDGAR | Historical 8-K, Form 4 filings |

**Time Lag Modeling** (stocks react to factors with delay):
```python
lags = [0, 3, 7, 14, 30]  # days before
features = {
    "fed_rate_t0": 5.25, "fed_rate_t7": 5.00, "fed_rate_t30": 4.75,
    "vix_t0": 15.2, "vix_t3": 18.5, "vix_t7": 20.1,
    "sec_risk_t0": 45, "sec_risk_t7": 30,
}
```

**Output Additions**:
```json
{
  "trend": "WORSENING",
  "score_change_7d": 25,
  "ml_prediction": {
    "predicted_return_30d": -5.2,
    "confidence": 0.72,
    "signal": "sell"
  }
}
```

**Acceptance Criteria**:
- [ ] Factor collector fetches FRED + Yahoo data
- [ ] 2 years of historical data backfilled for S&P 500
- [ ] Lagged features created (t-0, t-3, t-7, t-14, t-30)
- [ ] ML model trained on backtested data (XGBoost)
- [ ] Predictions integrated into output
- [ ] Trend analysis working

---

### Phase 4: Price Data Integration
**Status**: Pending | **Effort**: 2 days | **MAU Impact**: High

**Goal**: Add price/momentum analysis for better buy/sell signals.

**New Files**:
- `src/collectors/price_collector.py`
- `src/analyzers/price_analyzer.py`
- `src/scoring/composite_scorer.py`
- `src/scoring/signal_generator.py`

**Signal Logic**:
```python
def calculate_signal(sec_risk: int, momentum: int) -> Signal:
    if sec_risk >= 70 and momentum <= 30:
        return Signal.STRONG_SELL
    elif sec_risk >= 70:
        return Signal.SELL
    elif sec_risk <= 30 and momentum >= 70:
        return Signal.STRONG_BUY
    elif sec_risk <= 30:
        return Signal.BUY
    else:
        return Signal.HOLD
```

**Acceptance Criteria**:
- [ ] Price data for all scanned stocks
- [ ] Momentum score calculated
- [ ] Composite BUY/HOLD/SELL signal in output

---

### Phase 5: Real-Time SEC Firehose
**Status**: Pending | **Effort**: 2 days | **MAU Impact**: Very High

**Goal**: Monitor ALL new SEC filings as they're published.

**New Files**:
- `src/collectors/firehose_collector.py`

**Feeds**:
- `https://www.sec.gov/cgi-bin/browse-edgar?action=getcurrent&type=8-K&output=atom`
- `https://www.sec.gov/cgi-bin/browse-edgar?action=getcurrent&type=4&output=atom`

**Actor Mode**:
```json
{
  "mode": "firehose",
  "watchlist": ["AAPL", "TSLA"],
  "alertThreshold": 50
}
```

**Acceptance Criteria**:
- [ ] Detects new filings within 15 minutes
- [ ] Filters to watchlist if provided
- [ ] Alerts on high-risk filings

---

### Phase 6: Portfolio Mode
**Status**: Pending | **Effort**: 1 day | **MAU Impact**: High

**Goal**: Users input their holdings, get personalized risk monitoring.

**Input**:
```json
{
  "mode": "portfolio",
  "portfolio": [
    {"ticker": "AAPL", "shares": 100, "avgCost": 150.00},
    {"ticker": "TSLA", "shares": 50, "avgCost": 200.00}
  ]
}
```

**Output**:
```json
{
  "portfolio_risk_score": 35,
  "total_value": 25000,
  "at_risk_value": 5000,
  "holdings": [...],
  "recommendations": [
    "Consider reducing TSLA position (HIGH risk)",
    "AAPL position looks healthy (LOW risk)"
  ]
}
```

**Acceptance Criteria**:
- [ ] Portfolio input accepted
- [ ] Per-holding analysis
- [ ] Portfolio-level risk score
- [ ] Actionable recommendations

---

## Data Models

### Core Models

```python
class Signal(str, Enum):
    STRONG_BUY = "strong_buy"
    BUY = "buy"
    HOLD = "hold"
    SELL = "sell"
    STRONG_SELL = "strong_sell"

class Trend(str, Enum):
    IMPROVING = "improving"
    STABLE = "stable"
    WORSENING = "worsening"
    NEW = "new"

@dataclass(frozen=True)
class StockAnalysis:
    """Complete analysis for a single stock."""
    ticker: str
    company_name: str

    # SEC Risk
    risk_score: int
    risk_level: RiskLevel
    red_flags: tuple[RedFlag, ...]
    insider_summary: InsiderSummary

    # Price Analysis (Phase 4)
    price_data: PriceData | None
    momentum_score: int | None

    # Trend Analysis (Phase 3)
    trend: Trend
    score_change_7d: int | None
    score_change_30d: int | None

    # Composite Signal (Phase 4)
    signal: Signal
    signal_confidence: float

    # Explanation
    explanation: str
    analyzed_at: datetime
```

---

## ML/AI Strategy

### Current: LLM-Only (Groq/Llama 3.3)
- Red flag detection
- Insider pattern analysis
- Severity scoring
- Plain English explanations

### Phase 3: Factor-Based ML Model

**No waiting required** - We backtest on historical data immediately.

#### Factor Sources (All Free, All Have APIs)

| Category | Factors | Source | API |
|----------|---------|--------|-----|
| **Macroeconomic** | Fed Rate, Inflation, Unemployment, GDP, Treasury Spread | FRED | fred.stlouisfed.org |
| **Market** | VIX, S&P 500, Sector ETFs, Bond Yields | Yahoo Finance | yfinance |
| **Company** | P/E, Market Cap, EPS, Revenue, RSI | Yahoo Finance | yfinance |
| **Technical** | RSI, MACD, Moving Averages, Volume | Alpha Vantage | alphavantage.co |
| **SEC Signals** | Risk Score, Red Flags, Insider Activity | Our System | Built-in |

#### Time Lag Modeling

Stock prices don't react immediately to factors. We model lagged relationships:

```python
features = {
    # SEC Risk - our signal with lags
    "sec_risk_t0": 45,
    "sec_risk_t7": 30,
    "sec_risk_t30": 25,
    "sec_risk_change_7d": 15,

    # Macro factors - typically lag 1-30 days
    "fed_rate_t0": 5.25,
    "fed_rate_t30": 5.00,
    "inflation_t0": 3.2,
    "unemployment_t0": 3.8,

    # Market factors - lag 1-7 days
    "vix_t0": 15.2,
    "vix_t3": 18.5,
    "vix_t7": 20.1,
    "sp500_change_7d": -2.3,

    # Company factors
    "pe_ratio": 25.4,
    "market_cap_b": 150.0,
    "rsi_14": 65.3,

    # Insider signals - lag matters most
    "insider_sells_7d": 3,
    "insider_sells_30d": 5,
}
```

#### Backtest Approach

```python
# For each stock, for past 2 years:
for date in historical_dates:
    # 1. Collect all factors as of that date
    factors = collect_factors(ticker, date, lags=[0, 3, 7, 30])

    # 2. Get actual stock return 30 days later
    actual_return = get_price_change(ticker, date, date + 30)

    # 3. Store for training
    training_data.append({
        "features": factors,
        "target": actual_return,
        "profitable": actual_return > 0
    })

# Train model
model = XGBoost()
model.fit(training_data)
```

#### ML Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           FACTOR COLLECTION LAYER                            │
├─────────────────────────────────────────────────────────────────────────────┤
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐│
│  │ FRED API    │  │Yahoo Finance│  │ SEC EDGAR   │  │  Technical         ││
│  │ • Fed Rate  │  │ • VIX       │  │ • 8-K       │  │  • RSI             ││
│  │ • Inflation │  │ • S&P 500   │  │ • Form 4    │  │  • MACD            ││
│  │ • GDP       │  │ • P/E       │  │ • Risk Score│  │  • Volume          ││
│  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────────────┘│
│                              │                                               │
│                              ▼                                               │
│  ┌──────────────────────────────────────────────────────────────────────┐  │
│  │                    FEATURE ENGINEERING                                │  │
│  │  • Create lagged features (t-0, t-3, t-7, t-30)                      │  │
│  │  • Calculate deltas (Δ7d, Δ30d)                                      │  │
│  │  • Normalize/scale features                                          │  │
│  │  • Handle missing data                                               │  │
│  └──────────────────────────────────────────────────────────────────────┘  │
│                              │                                               │
│                              ▼                                               │
│  ┌──────────────────────────────────────────────────────────────────────┐  │
│  │                         ML MODEL (XGBoost/LightGBM)                   │  │
│  │  • Input: 50+ lagged factors                                         │  │
│  │  • Output: Predicted 30-day return + confidence                      │  │
│  │  • Trained on 2+ years of backtested data                            │  │
│  └──────────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────┘
```

#### New Files for ML

```
src/collectors/
├── factor_collector.py      # FRED + Yahoo + Technical factors

src/ml/                       # NEW MODULE
├── __init__.py
├── features.py              # Feature engineering, lag creation
├── backtest.py              # Historical backtesting engine
├── model.py                 # XGBoost/LightGBM model
└── predictor.py             # Real-time prediction service
```

### AI Agent (Separate Actor)

**Purpose**: Conversational interface on top of this platform

```
User: "Should I sell my TSLA shares?"
Agent: [Calls this Actor] → [Analyzes response] → [Generates recommendation]
```

**Decision**: Build as separate Actor for clean separation.

---

## API Design

### Input Schema

```json
{
  "mode": {
    "type": "string",
    "enum": ["scan", "firehose", "portfolio"],
    "default": "scan"
  },
  "scanMode": {
    "type": "string",
    "enum": ["custom", "sp500", "nasdaq100", "all_recent"],
    "default": "custom"
  },
  "tickers": {
    "type": "array",
    "description": "Custom tickers (scanMode=custom)"
  },
  "portfolio": {
    "type": "array",
    "description": "Holdings (mode=portfolio)"
  },
  "lookbackDays": {
    "type": "integer",
    "default": 30
  },
  "includePrice": {
    "type": "boolean",
    "default": true
  },
  "includeTrends": {
    "type": "boolean",
    "default": true
  },
  "alertThreshold": {
    "type": "integer",
    "default": 70
  },
  "webhookUrl": {
    "type": "string"
  }
}
```

### Output Schema

```json
{
  "ticker": "AAPL",
  "company_name": "Apple Inc.",
  "risk_score": 25,
  "risk_level": "low",
  "signal": "buy",
  "signal_confidence": 0.75,
  "trend": "stable",
  "score_change_7d": -3,
  "price": {
    "current": 185.50,
    "momentum_score": 72
  },
  "red_flags": [],
  "insider_summary": {
    "net_activity": "neutral"
  },
  "explanation": "Apple shows low risk...",
  "analyzed_at": "2026-01-01T12:00:00Z"
}
```

---

## Infrastructure & Operations

### Rate Limits

| Service | Limit |
|---------|-------|
| SEC EDGAR | 10 req/sec |
| Yahoo Finance | 5 req/sec |
| Groq LLM | 30 req/min |

### Error Handling

- Never fail entire run for one stock
- Log errors, continue processing
- Return partial results with error details
- Retry transient failures (network, rate limits)

---

## Testing Strategy

```
Unit Tests (60%)       - Pure functions, data transforms
Integration Tests (30%) - Component interactions, mock APIs
E2E Tests (10%)        - Full pipeline with real data
```

---

## Migration Plan

### Backward Compatibility

Existing API remains fully supported:
```json
{"tickers": ["AAPL"], "lookbackDays": 30}
```

Equivalent to:
```json
{"mode": "scan", "scanMode": "custom", "tickers": ["AAPL"]}
```

### Version Roadmap

| Version | Features |
|---------|----------|
| 1.0 | Custom tickers (current) |
| 1.1 | + S&P 500 mode, scheduling |
| 1.2 | + Historical tracking, trends |
| 1.3 | + Price data, composite signals |
| 1.4 | + Real-time firehose |
| 1.5 | + Portfolio mode |
| 2.0 | + ML model (future) |

---

## Legal Disclaimer

```
DISCLAIMER: This tool provides risk analysis based on publicly available
SEC filings and market data. It is for informational purposes only and
does not constitute financial advice. Always consult a qualified financial
advisor before making investment decisions.
```

---

*Document Version: 3.0*
*Last Updated: January 1, 2026*