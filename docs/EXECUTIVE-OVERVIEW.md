# SEC Filing Risk Scanner: Executive Overview (Revised)

## What We're Building

**SEC Filing Risk Scanner** is an AI-powered tool that analyzes SEC filings (8-K, Form 4) to detect risk signals before they become headlines.

**Store Name**: `SEC Filing Risk Scanner – 8-K Filings & Insider Trading Alerts`

**Target Competition**: Apify $1M Challenge (Deadline: January 31, 2026)

---

## Strategy: MAU-First Approach

The Apify Challenge rewards **Monthly Active Users (MAUs)**, not technical complexity.

**Our strategy**:
1. **Ship fast** - Get Actor 1 live in 1-2 weeks
2. **Stay reliable** - SEC data is stable, LLMs are fast
3. **Add intelligence** - LLM analysis, not traditional ML
4. **Multiple Actors** - 2-3 focused products = 2-3x MAU streams

---

## Product Architecture (Revised)

### Actor 1: stock-sec-risk-scanner (PRIMARY - Ship First)

**What it does**:
- Scrapes SEC EDGAR (8-K filings, Form 4 insider transactions)
- Uses LLM (Groq/Llama 3.3) to analyze filings for red flags
- Scores risk severity with AI reasoning
- Explains findings in plain English

**Why ship this first**:
- SEC data is 100% reliable (structured, public)
- LLM analysis adds intelligence without training data
- Clear value proposition for users
- Fast to build and test

### Actor 2: stock-newsroom-scanner (SECONDARY)

**What it does**:
- Scrapes company press releases and IR pages
- Detects negative keywords (investigation, restatement, layoff)
- Analyzes communication patterns

**Ship after Actor 1 is live and stable**

### Actor 3: stock-hiring-signals (EXPERIMENTAL - Maybe)

**What it does**:
- Tracks company job postings
- Detects hiring pattern changes

**Only build if time permits, marked as "experimental"**

---

## What Got Cut (vs. Original Plan)

| Component | Status | Reason |
|-----------|--------|--------|
| Traditional ML Model | ❌ Removed | No training data, adds complexity |
| Careers Collector (v1) | ❌ Deferred | Too brittle, high failure rate |
| Backtesting Module | ❌ Removed | Nice-to-have, not MAU driver |
| Agent Deep-Dive | ❌ Removed | Over-engineering |
| Multi-source Fusion | ❌ Deferred | Keep Actors independent |

---

## LLM-Enhanced Intelligence (Key Differentiator)

Instead of traditional ML (requires training data), we use LLMs for:

| Task | How LLM Helps |
|------|---------------|
| Red flag detection | Zero-shot classification of filing content |
| Severity scoring | In-context reasoning about risk level |
| Pattern recognition | Few-shot prompting for insider patterns |
| Explanation | Native capability - plain English summaries |

**Why this works**:
- No training data needed
- LLMs are good at document analysis
- Groq free tier is fast and generous
- Users see "AI-powered" legitimately

---

## Target Users

| User Type | Use Case | When They Run |
|-----------|----------|---------------|
| **Retail Investors** | Monitor holdings | Weekly |
| **Traders** | Pre-earnings check | Before earnings |
| **Content Creators** | Generate signal reports | Weekly |
| **Newsletter Writers** | Curated insights | Weekly |

---

## Why We Win

| Factor | Our Advantage |
|--------|---------------|
| **Blue Ocean** | No good SEC analysis tools on Apify Store |
| **Repeat Usage** | Weekly monitoring = recurring MAUs |
| **AI-Powered** | LLM analysis is legitimate differentiator |
| **Reliable** | SEC + Groq = stable foundation |
| **Multiple Actors** | 2-3 products = 2-3x MAU potential |

---

## Success Metrics

### Minimum Viable Success
- Actor 1 published on Store
- 50+ MAUs (qualifies for $100 payout)

### Target Success
- 200+ MAUs across all Actors
- Top 10 in finance category

### Stretch Goals
- 500+ MAUs
- Jury consideration for top 3

---

## Risks (Revised)

| Risk | Severity | Mitigation |
|------|----------|------------|
| Groq rate limits | Low | Cache responses, batch requests |
| SEC changes format | Low | Structured data is stable |
| Low MAUs | Medium | Marketing push, iterate on feedback |
| LLM hallucination | Low | Show evidence links, ground responses |

---

## Timeline (Revised)

| Phase | Duration | Deliverable |
|-------|----------|-------------|
| Week 1 | 5-7 days | Actor 1 MVP (SEC + LLM) |
| Week 2 | 3-4 days | Publish to Store, initial marketing |
| Week 3 | 5-7 days | Actor 2 (Newsroom), iterate Actor 1 |
| Week 4+ | Ongoing | Marketing, feedback, optimization |

---

## Open Questions (Reduced)

1. **Ticker Universe**: Start with S&P 100? User-defined only?
2. **LLM Prompts**: Need testing to optimize red flag detection
3. **Store Listing**: Finalize title and description

---

*Document Version: 2.0*
*Last Updated: December 29, 2024*
*Change: Simplified to LLM-enhanced, MAU-first approach*