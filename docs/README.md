# Stock Risk Intelligence Platform

## Overview

A comprehensive platform for real-time stock risk monitoring, powered by SEC filings, price data, and AI analysis. Detects red flags before the market reacts and provides actionable BUY/HOLD/SELL signals.

---

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Set environment variables
export GROQ_API_KEY=your_api_key

# Run locally
python -m src.main

# Run tests
pytest tests/
```

---

## Features

| Feature | Status | Phase |
|---------|--------|-------|
| Custom ticker scanning | ✅ Live | 1.0 |
| SEC 8-K filing analysis | ✅ Live | 1.0 |
| Form 4 insider trading | ✅ Live | 1.0 |
| LLM-powered explanations | ✅ Live | 1.0 |
| Webhook alerts | ✅ Live | 1.0 |
| S&P 500 auto-scan | 🔄 Building | 1.1 |
| Scheduling support | 🔄 Building | 1.1 |
| Historical tracking | 📋 Planned | 1.2 |
| Price/momentum analysis | 📋 Planned | 1.3 |
| BUY/SELL signals | 📋 Planned | 1.3 |
| Real-time firehose | 📋 Planned | 1.4 |
| Portfolio mode | 📋 Planned | 1.5 |

---

## Documentation

| Document | Description |
|----------|-------------|
| [TECHNICAL-DESIGN.md](./TECHNICAL-DESIGN.md) | Architecture, phases, API design |
| [EXECUTIVE-OVERVIEW.md](./EXECUTIVE-OVERVIEW.md) | Non-technical overview |
| [DEMO-AND-DEPLOYMENT.md](./DEMO-AND-DEPLOYMENT.md) | Setup and deployment guide |

### Component Docs (Reference)
| Component | Status |
|-----------|--------|
| [SEC-COLLECTOR.md](./components/SEC-COLLECTOR.md) | ✅ Implemented |
| [LLM-EXPLAINER.md](./components/LLM-EXPLAINER.md) | ✅ Implemented |
| [SCORING-ENGINE.md](./components/SCORING-ENGINE.md) | ✅ Implemented |

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                 STOCK RISK INTELLIGENCE PLATFORM             │
├─────────────────────────────────────────────────────────────┤
│  INGESTION      │  ANALYSIS       │  OUTPUT                 │
│  • SEC EDGAR    │  • LLM Analyzer │  • Risk Score (0-100)   │
│  • Stock Lists  │  • Price Data   │  • BUY/HOLD/SELL Signal │
│  • Price APIs   │  • Trend Calc   │  • Explanations         │
│                 │  • Scoring      │  • Alerts               │
└─────────────────────────────────────────────────────────────┘
```

---

## Usage

### Basic (Custom Tickers)
```json
{
  "tickers": ["AAPL", "TSLA", "NVDA"],
  "lookbackDays": 30
}
```

### S&P 500 Scan (Phase 1.1)
```json
{
  "scanMode": "sp500",
  "lookbackDays": 30
}
```

### Portfolio Mode (Phase 1.5)
```json
{
  "mode": "portfolio",
  "portfolio": [
    {"ticker": "AAPL", "shares": 100, "avgCost": 150.00}
  ]
}
```

---

## Output Example

```json
{
  "ticker": "TSLA",
  "risk_score": 72,
  "risk_level": "high",
  "signal": "sell",
  "red_flags": [
    {
      "type": "CLUSTER_SELLING",
      "title": "3 Executives Sold $8.2M",
      "severity": "high"
    }
  ],
  "explanation": "Tesla shows elevated risk due to multiple executive sales...",
  "analyzed_at": "2026-01-01T12:00:00Z"
}
```

---

## Development

### Project Structure
```
src/
├── collectors/      # Data ingestion (SEC, prices)
├── analyzers/       # LLM analysis, trends
├── scoring/         # Risk scoring, signals
├── services/        # Orchestration
├── formatters/      # Output formatting
└── core/            # Models, interfaces
```

### Running Tests
```bash
# All tests
pytest tests/ -v

# Unit only
pytest tests/unit -v

# E2E (requires GROQ_API_KEY)
pytest tests/e2e -v
```

---

## Roadmap

| Phase | Features | Target |
|-------|----------|--------|
| 1.1 | S&P 500 mode, scheduling | Week 1 |
| 1.2 | Historical tracking, trends | Week 1 |
| 1.3 | Price data, BUY/SELL signals | Week 2 |
| 1.4 | Real-time SEC firehose | Week 2 |
| 1.5 | Portfolio mode | Week 3 |
| 2.0 | ML model training | Future |

---

## Legal Disclaimer

This tool provides risk analysis for informational purposes only. It does not constitute financial advice. Always consult a qualified financial advisor before making investment decisions.

---

*Version: 1.0*
*Last Updated: January 1, 2026*