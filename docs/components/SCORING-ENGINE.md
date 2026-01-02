# Scoring Engine: Deep Dive

## Purpose

Convert extracted signals into a unified SignalScore (0-100) that represents overall risk level for a stock.

---

## Scoring Philosophy

### Design Principles

1. **Explainable**: Every score can be traced back to specific signals
2. **Comparable**: Scores are normalized across tickers
3. **Actionable**: Clear thresholds for decisions
4. **Conservative**: Prefer false positives over false negatives for risk

### Score Interpretation

| Score Range | Risk Level | Color | Meaning |
|-------------|------------|-------|---------|
| 0-30 | Low | Green | No significant risk signals detected |
| 31-50 | Neutral | Yellow | Some signals, normal monitoring |
| 51-70 | Elevated | Orange | Multiple signals, increased attention needed |
| 71-100 | High | Red | Significant risk signals, action recommended |

---

## Category Architecture

### Categories and Weights

```python
CATEGORY_WEIGHTS = {
    'regulatory': 0.30,   # SEC filings, investigations
    'operational': 0.25,  # Hiring patterns, workforce
    'narrative': 0.20,    # Press releases, communications
    'insider': 0.15,      # Form 4 transactions
    'momentum': 0.10,     # Social/news volume (optional)
}
# Weights sum to 1.0
```

### Weight Rationale

| Category | Weight | Rationale |
|----------|--------|-----------|
| Regulatory | 30% | Highest signal quality, legally required disclosures |
| Operational | 25% | Leading indicator of company health |
| Narrative | 20% | Official communications reflect management awareness |
| Insider | 15% | Insiders have information advantage |
| Momentum | 10% | Noisy but can indicate attention |

---

## Signal Scoring

### Signal Score Table

```python
SIGNAL_SCORES = {
    # REGULATORY (max: 100 for category)
    "SEC_8K_ACCOUNTANT_CHANGE": 40,      # Very significant
    "SEC_8K_EXECUTIVE_DEPARTURE": 25,    # Significant
    "SEC_8K_MATERIAL_EVENT": 20,         # Moderate
    "SEC_8K_NONRELIANCE": 50,           # Critical
    "INVESTIGATION_MENTIONED": 35,       # Significant
    "RESTATEMENT_MENTIONED": 45,         # Very significant
    "MATERIAL_WEAKNESS_MENTIONED": 40,   # Very significant

    # OPERATIONAL (max: 100)
    "LEGAL_HIRING_SPIKE": 30,           # Leading indicator
    "COMPLIANCE_HIRING_SPIKE": 25,      # Leading indicator
    "ENGINEERING_HIRING_DROP": 20,      # Growth concern
    "LAYOFF_LANGUAGE_DETECTED": 35,     # Direct signal
    "RESTRUCTURING_KEYWORD": 20,        # Moderate signal

    # NARRATIVE (max: 100)
    "NEGATIVE_SENTIMENT_SPIKE": 20,     # Soft signal
    "FRIDAY_RELEASE_PATTERN": 15,       # Timing signal
    "COMMUNICATION_DROP": 15,           # Attention signal
    "LAYOFF_ANNOUNCED": 25,             # Direct signal
    "INVESTIGATION_MENTIONED": 30,      # Significant

    # INSIDER (max: 100)
    "INSIDER_SELL_LARGE": 25,           # Significant
    "INSIDER_SELL_CLUSTER": 30,         # Very significant
    "INSIDER_BUY_LARGE": -20,           # Positive (reduces score)
    "INSIDER_SELL_SMALL": 10,           # Minor

    # MOMENTUM (max: 100)
    "SOCIAL_MENTION_SPIKE": 10,         # Attention indicator
    "NEWS_VOLUME_SPIKE": 10,            # Attention indicator
    "WIKIPEDIA_VIEWS_SPIKE": 5,         # Minor attention
}
```

### Severity Multipliers

Signals can have severity multipliers based on magnitude:

```python
def calculate_signal_score(signal: dict) -> float:
    """Calculate score contribution for a single signal"""
    base_score = SIGNAL_SCORES.get(signal['type'], 0)
    severity = signal.get('severity', 1.0)

    # Clamp severity between 0.5 and 2.0
    severity = max(0.5, min(2.0, severity))

    return base_score * severity
```

### Severity Guidelines

| Signal Type | Severity 0.5 | Severity 1.0 | Severity 1.5 | Severity 2.0 |
|-------------|--------------|--------------|--------------|--------------|
| INSIDER_SELL_LARGE | <$500K | $500K-$1M | $1M-$5M | >$5M |
| LEGAL_HIRING_SPIKE | 50% increase | 100% increase | 200% increase | >300% increase |
| RESTATEMENT_MENTIONED | Mentioned | Confirmed | Ongoing | Multiple periods |

---

## Scoring Algorithm

### Step 1: Group Signals by Category

```python
def group_signals_by_category(signals: list) -> dict:
    """Group signals into categories"""
    grouped = {cat: [] for cat in CATEGORY_WEIGHTS}

    for signal in signals:
        category = signal.get('category', 'other')
        if category in grouped:
            grouped[category].append(signal)

    return grouped
```

### Step 2: Calculate Category Scores

```python
def calculate_category_score(signals: list) -> float:
    """Calculate score for a single category"""
    if not signals:
        return 0.0

    total = sum(calculate_signal_score(s) for s in signals)

    # Cap at 100
    return min(100.0, max(0.0, total))
```

### Step 3: Apply Weights

```python
def calculate_signal_score(signals: list) -> dict:
    """Calculate overall SignalScore"""
    grouped = group_signals_by_category(signals)

    category_scores = {}
    for category, cat_signals in grouped.items():
        category_scores[category] = {
            'score': calculate_category_score(cat_signals),
            'signals_count': len(cat_signals),
            'top_signals': sorted(
                cat_signals,
                key=lambda s: calculate_signal_score(s),
                reverse=True
            )[:3]
        }

    # Weighted final score
    final_score = sum(
        category_scores[cat]['score'] * CATEGORY_WEIGHTS[cat]
        for cat in CATEGORY_WEIGHTS
    )

    return {
        'signal_score': round(final_score, 1),
        'risk_level': get_risk_level(final_score),
        'breakdown': category_scores,
        'total_signals': sum(cs['signals_count'] for cs in category_scores.values()),
    }
```

### Step 4: Determine Risk Level

```python
def get_risk_level(score: float) -> str:
    """Convert score to risk level"""
    if score < 30:
        return 'low'
    elif score < 50:
        return 'neutral'
    elif score < 70:
        return 'elevated'
    else:
        return 'high'
```

---

## Edge Cases

### No Signals

```python
if not signals:
    return {
        'signal_score': 0,
        'risk_level': 'low',
        'breakdown': {cat: {'score': 0, 'signals_count': 0} for cat in CATEGORY_WEIGHTS},
        'note': 'No signals detected - may indicate data collection issues'
    }
```

### Conflicting Signals

```python
# Example: Large insider buy AND large insider sell
# Both contribute to the score - they don't cancel out
# Rationale: Both are noteworthy activity
```

### Single Very Strong Signal

```python
# A single critical signal (e.g., SEC_8K_NONRELIANCE = 50) can push
# a category to 50, resulting in final score of ~15 from that alone
# This is intentional - critical signals should register
```

---

## Score Delta Tracking

Track how scores change over time:

```python
class ScoreDeltaTracker:
    def __init__(self, kv_store):
        self.kv_store = kv_store

    async def get_delta(self, ticker: str, current_score: float) -> dict:
        """Calculate score change vs previous readings"""
        key = f"score_history_{ticker}"
        history = await self.kv_store.get_value(key) or []

        deltas = {
            '1d': None,
            '7d': None,
            '30d': None,
        }

        for days, period in [(1, '1d'), (7, '7d'), (30, '30d')]:
            target_date = datetime.now() - timedelta(days=days)
            closest = self._find_closest(history, target_date)
            if closest:
                deltas[period] = current_score - closest['score']

        return deltas

    async def record_score(self, ticker: str, score: float):
        """Record current score for future delta calculation"""
        key = f"score_history_{ticker}"
        history = await self.kv_store.get_value(key) or []

        history.append({
            'date': datetime.now().isoformat(),
            'score': score
        })

        # Keep 90 days of history
        history = history[-90:]
        await self.kv_store.set_value(key, history)
```

---

## Output Schema

```python
{
    "ticker": "TSLA",
    "signal_score": 67.5,
    "risk_level": "elevated",
    "score_delta": {
        "1d": +5.2,
        "7d": +12.3,
        "30d": -3.1
    },
    "breakdown": {
        "regulatory": {
            "score": 65.0,
            "weight": 0.30,
            "contribution": 19.5,
            "signals_count": 2,
            "top_signals": [
                {
                    "type": "SEC_8K_EXECUTIVE_DEPARTURE",
                    "title": "CFO Departure Announced",
                    "score_contribution": 25
                }
            ]
        },
        "operational": {
            "score": 55.0,
            "weight": 0.25,
            "contribution": 13.75,
            "signals_count": 2
        },
        "narrative": {
            "score": 45.0,
            "weight": 0.20,
            "contribution": 9.0,
            "signals_count": 3
        },
        "insider": {
            "score": 80.0,
            "weight": 0.15,
            "contribution": 12.0,
            "signals_count": 1
        },
        "momentum": {
            "score": 20.0,
            "weight": 0.10,
            "contribution": 2.0,
            "signals_count": 1
        }
    },
    "top_signals": [
        {
            "rank": 1,
            "type": "INSIDER_SELL_CLUSTER",
            "category": "insider",
            "title": "Multiple Insiders Sold Shares",
            "score_contribution": 30,
            "evidence_url": "https://sec.gov/..."
        }
    ]
}
```

---

## TBD / Open Questions

### Critical

1. **Weight Calibration**: Are the category weights optimal?
   - **How to Decide**: Backtest against historical data
   - **Default**: Use proposed weights, adjust based on performance

2. **Signal Score Values**: Are individual signal scores balanced?
   - **How to Decide**: Compare signal frequencies and importance
   - **Default**: Use proposed values, iterate with feedback

### Medium Priority

3. **Score Decay**: Should old signals reduce impact over time?
   - **Decision**: No decay for MVP (simpler)
   - **Future**: Add decay factor for signals >7 days old

4. **Category Caps**: Should category scores have subcaps?
   - **Decision**: Cap at 100 per category (already implemented)
   - **Rationale**: Prevents single category dominating

### Lower Priority

5. **Confidence Score**: Should we report confidence in the score?
   - **Decision**: Skip for MVP
   - **Future**: Confidence based on data completeness

6. **Peer Comparison**: Should we show relative ranking?
   - **Decision**: Add in Phase 2
   - **Example**: "Higher risk than 85% of S&P 500"

---

## ML Integration (Phase 2)

### Combined Score

```python
def calculate_combined_score(rules_score: float, ml_score: float) -> float:
    """Combine rules-based and ML scores"""
    RULES_WEIGHT = 0.6
    ML_WEIGHT = 0.4

    return rules_score * RULES_WEIGHT + ml_score * ML_WEIGHT
```

### ML Score Source

ML score comes from trained model predicting:
- P(volatility spike next 7 days)
- P(significant drawdown next 14 days)

Scaled to 0-100 for combination.

---

*Component Version: 1.0*
