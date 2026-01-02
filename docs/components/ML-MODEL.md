# ML Model: Deep Dive

## Purpose

Enhance the rules-based scoring with machine learning predictions for:
- Better ranking of risk signals
- Pattern detection across multiple signals
- Calibrated probability estimates

**Note**: This is a Phase 2 feature. MVP uses rules-only scoring.

---

## Strategy: Two-Track Scoring

```
                    ┌─────────────────┐
                    │   Raw Signals   │
                    └────────┬────────┘
                             │
              ┌──────────────┴──────────────┐
              ▼                             ▼
    ┌─────────────────┐           ┌─────────────────┐
    │  Rules Engine   │           │    ML Model     │
    │  (Explainable)  │           │  (Predictive)   │
    └────────┬────────┘           └────────┬────────┘
             │                             │
             │ 60%                    40%  │
             └──────────────┬──────────────┘
                            ▼
                  ┌─────────────────┐
                  │  Combined Score │
                  └─────────────────┘
```

**Why both?**
- Rules: Always explainable, works from day 1
- ML: Learns patterns, improves over time
- Combined: User trust + prediction accuracy

---

## Target Variable

### Option 1: Volatility Spike (Recommended for MVP)

```python
def create_volatility_target(price_data, lookahead=7, threshold=2.0):
    """
    Target: Will volatility in next 7 days exceed 2x historical?
    Binary classification: 1 = spike, 0 = normal
    """
    # Historical volatility (30-day rolling)
    returns = price_data['Close'].pct_change()
    hist_vol = returns.rolling(30).std()

    # Future volatility (7-day forward)
    future_vol = returns.rolling(7).std().shift(-lookahead)

    # Target: future vol > threshold * historical vol
    target = (future_vol > threshold * hist_vol).astype(int)

    return target
```

**Pros**: Captures "something big happens", frequent enough for training
**Cons**: Not directional (doesn't predict up vs down)

### Option 2: Significant Drawdown

```python
def create_drawdown_target(price_data, lookahead=14, threshold=-0.10):
    """
    Target: Will price drop >10% in next 14 days?
    Binary classification: 1 = drop, 0 = normal
    """
    future_return = (price_data['Close'].shift(-lookahead) / price_data['Close']) - 1
    target = (future_return < threshold).astype(int)
    return target
```

**Pros**: Directly actionable (sell signal)
**Cons**: Rare events, class imbalance

### Recommendation

Start with **volatility spike** (more balanced classes, captures attention).
Add **drawdown** as secondary model after more data.

---

## Feature Engineering

### Features from Signals

```python
FEATURES = {
    # SEC/Regulatory (30-day lookback)
    'sec_8k_count_30d': 'Count of 8-K filings',
    'sec_8k_high_risk_item_flag': 'Any 4.01 or 4.02 items',
    'sec_form4_sell_volume_30d': 'Total insider sell value',
    'sec_form4_sell_count_30d': 'Number of insider sells',
    'sec_form4_buy_sell_ratio': 'Buy/sell ratio',
    'sec_form4_cluster_flag': 'Multiple sells within 7 days',

    # Careers (delta vs baseline)
    'jobs_total_delta_14d': 'Change in total jobs',
    'jobs_legal_ratio': 'Legal jobs as % of total',
    'jobs_legal_delta_14d': 'Change in legal jobs',
    'jobs_compliance_delta_14d': 'Change in compliance jobs',
    'jobs_engineering_delta_14d': 'Change in engineering jobs',

    # Newsroom
    'news_count_30d': 'Press releases in 30 days',
    'news_negative_keywords_30d': 'Negative keyword count',
    'news_investigation_flag': 'Investigation mentioned',
    'news_friday_release_count_30d': 'Friday releases',

    # Derived/Interaction
    'multi_signal_count': 'Total signals detected',
    'rules_score': 'Rules-based SignalScore',
    'insider_sell_while_legal_spike': 'Sells + legal hiring (interaction)',
}
```

### Feature Extraction Function

```python
def extract_features(signals: list, baseline: dict) -> dict:
    """Convert signals to feature vector"""
    features = {}

    # Count signals by type
    sec_signals = [s for s in signals if s['category'] == 'regulatory']
    features['sec_8k_count_30d'] = len([s for s in sec_signals if '8K' in s['type']])
    features['sec_8k_high_risk_item_flag'] = int(any(
        s['type'] in ['SEC_8K_ACCOUNTANT_CHANGE', 'SEC_8K_NONRELIANCE']
        for s in sec_signals
    ))

    # Insider activity
    insider_signals = [s for s in signals if s['category'] == 'insider']
    sell_signals = [s for s in insider_signals if 'SELL' in s['type']]
    buy_signals = [s for s in insider_signals if 'BUY' in s['type']]

    features['sec_form4_sell_count_30d'] = len(sell_signals)
    features['sec_form4_cluster_flag'] = int(any(
        s['type'] == 'INSIDER_SELL_CLUSTER' for s in sell_signals
    ))

    # Careers features
    ops_signals = [s for s in signals if s['category'] == 'operational']
    features['jobs_legal_delta_14d'] = get_delta_from_signals(ops_signals, 'LEGAL_HIRING')

    # ... extract remaining features

    return features
```

---

## Model Selection

### Primary: LightGBM

```python
import lightgbm as lgb
from sklearn.calibration import CalibratedClassifierCV

class SignalPredictor:
    def __init__(self):
        self.model = None
        self.scaler = StandardScaler()
        self.feature_names = list(FEATURES.keys())

    def train(self, X: np.ndarray, y: np.ndarray):
        """Train the prediction model"""
        # Scale features
        X_scaled = self.scaler.fit_transform(X)

        # Base model
        base_model = lgb.LGBMClassifier(
            n_estimators=100,
            max_depth=5,
            learning_rate=0.05,
            class_weight='balanced',
            random_state=42,
            verbose=-1
        )

        # Calibrate probabilities
        self.model = CalibratedClassifierCV(
            base_model,
            method='isotonic',
            cv=5
        )
        self.model.fit(X_scaled, y)

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        """Get calibrated probability scores"""
        X_scaled = self.scaler.transform(X)
        return self.model.predict_proba(X_scaled)[:, 1]

    def predict_score(self, X: np.ndarray) -> np.ndarray:
        """Get score scaled to 0-100"""
        proba = self.predict_proba(X)
        return proba * 100
```

**Why LightGBM?**
- Handles small datasets well
- Fast training
- Good with tabular data
- Feature importance built-in

### Fallback: Logistic Regression

```python
from sklearn.linear_model import LogisticRegression

class SimplePredictor:
    """Fallback for very small datasets"""
    def __init__(self):
        self.model = LogisticRegression(class_weight='balanced')
        self.scaler = StandardScaler()

    def train(self, X, y):
        X_scaled = self.scaler.fit_transform(X)
        self.model.fit(X_scaled, y)
```

---

## Training Pipeline

### Data Collection

```python
async def collect_training_data(tickers: list, days: int = 180):
    """Collect historical data for training"""
    training_data = []

    for ticker in tickers:
        # Get historical signals (need to store these over time)
        signals_history = await load_signal_history(ticker, days)

        # Get price data for labels
        prices = yf.Ticker(ticker).history(period=f"{days}d")

        # Create labels
        vol_target = create_volatility_target(prices)
        drawdown_target = create_drawdown_target(prices)

        # Align signals with labels by date
        for date, day_signals in signals_history.items():
            if date in vol_target.index:
                features = extract_features(day_signals)
                training_data.append({
                    'ticker': ticker,
                    'date': date,
                    'features': features,
                    'vol_label': vol_target[date],
                    'drawdown_label': drawdown_target[date]
                })

    return training_data
```

### Training

```python
def train_model(training_data: list):
    """Train the ML model"""
    # Convert to arrays
    X = np.array([d['features'] for d in training_data])
    y = np.array([d['vol_label'] for d in training_data])

    # Time series split (don't leak future data)
    tscv = TimeSeriesSplit(n_splits=5)

    # Train with cross-validation
    predictor = SignalPredictor()
    cv_scores = []

    for train_idx, val_idx in tscv.split(X):
        X_train, X_val = X[train_idx], X[val_idx]
        y_train, y_val = y[train_idx], y[val_idx]

        predictor.train(X_train, y_train)
        proba = predictor.predict_proba(X_val)

        # Evaluate
        from sklearn.metrics import roc_auc_score
        auc = roc_auc_score(y_val, proba)
        cv_scores.append(auc)

    print(f"CV AUC: {np.mean(cv_scores):.3f} (+/- {np.std(cv_scores):.3f})")

    # Train final model on all data
    predictor.train(X, y)
    return predictor
```

---

## Model Deployment

### Storage (Using JSON for Safety)

```python
import json
import numpy as np

async def save_model(predictor: SignalPredictor, kv_store):
    """Save trained model to Apify KV store using JSON"""
    # For LightGBM, we can save the model as text
    model_data = {
        'model_text': predictor.model.booster_.save_model_to_string(),
        'scaler_mean': predictor.scaler.mean_.tolist(),
        'scaler_scale': predictor.scaler.scale_.tolist(),
        'feature_names': predictor.feature_names,
        'trained_at': datetime.utcnow().isoformat(),
        'version': '1.0'
    }
    await kv_store.set_value('ml_model', json.dumps(model_data))

async def load_model(kv_store) -> SignalPredictor | None:
    """Load trained model from KV store"""
    model_json = await kv_store.get_value('ml_model')
    if not model_json:
        return None

    data = json.loads(model_json)
    predictor = SignalPredictor()

    # Reconstruct model from text
    predictor.model = lgb.Booster(model_str=data['model_text'])
    predictor.scaler.mean_ = np.array(data['scaler_mean'])
    predictor.scaler.scale_ = np.array(data['scaler_scale'])
    predictor.feature_names = data['feature_names']

    return predictor
```

**Note**: Using JSON serialization for safety. For complex sklearn models that don't support text export, consider using `joblib` with proper security measures or ONNX format for production.

### Inference

```python
async def get_ml_score(signals: list, kv_store) -> float | None:
    """Get ML score for signals"""
    predictor = await load_model(kv_store)
    if not predictor:
        return None  # No model trained yet

    features = extract_features(signals)
    feature_vector = np.array([[features.get(f, 0) for f in predictor.feature_names]])

    score = predictor.predict_score(feature_vector)[0]
    return round(score, 1)
```

---

## Combined Scoring

```python
def calculate_combined_score(rules_score: float, ml_score: float | None) -> dict:
    """Combine rules and ML scores"""
    if ml_score is None:
        # No ML model available
        return {
            'combined_score': rules_score,
            'rules_score': rules_score,
            'ml_score': None,
            'ml_contribution': 0
        }

    RULES_WEIGHT = 0.6
    ML_WEIGHT = 0.4

    combined = rules_score * RULES_WEIGHT + ml_score * ML_WEIGHT

    return {
        'combined_score': round(combined, 1),
        'rules_score': rules_score,
        'ml_score': ml_score,
        'rules_contribution': round(rules_score * RULES_WEIGHT, 1),
        'ml_contribution': round(ml_score * ML_WEIGHT, 1)
    }
```

---

## Evaluation Metrics

### Primary Metrics

```python
def evaluate_model(y_true, y_proba):
    """Calculate evaluation metrics"""
    from sklearn.metrics import (
        roc_auc_score, precision_recall_curve,
        average_precision_score, brier_score_loss
    )

    return {
        'auc_roc': roc_auc_score(y_true, y_proba),
        'avg_precision': average_precision_score(y_true, y_proba),
        'brier_score': brier_score_loss(y_true, y_proba),  # Calibration
    }
```

### Backtesting

```python
def backtest_predictions(predictions: list, actuals: list) -> dict:
    """Backtest predictions against actual outcomes"""
    high_risk = [p for p, a in zip(predictions, actuals) if p['score'] > 70]
    high_risk_events = [p for p in high_risk if p['actual_event']]

    precision_at_70 = len(high_risk_events) / len(high_risk) if high_risk else 0

    return {
        'precision_at_70': precision_at_70,
        'high_risk_count': len(high_risk),
        'true_positives': len(high_risk_events),
    }
```

---

## Cold Start Strategy

### Phase 1: Rules Only (Months 1-3)

```python
# No ML model
# Rules-based scoring only
# Collect and store all signals for future training
```

### Phase 2: Train First Model (Month 3+)

```python
# Require: 90+ days of signal data
# Require: At least 10 tickers with consistent data
# Train on volatility prediction
```

### Phase 3: Continuous Improvement (Month 6+)

```python
# Monthly retraining
# Add drawdown prediction
# A/B test rules vs combined
```

---

## TBD / Open Questions

### Critical

1. **Minimum Data Requirements**: How much data before ML is useful?
   - **Hypothesis**: 90 days, 20+ tickers
   - **How to Decide**: Train on simulated data, check AUC

2. **Feature Selection**: Which features actually matter?
   - **Decision**: Start with all, prune based on importance
   - **Tool**: SHAP values for feature importance

### Medium Priority

3. **Retraining Frequency**: How often to retrain?
   - **Decision**: Monthly for MVP
   - **Later**: Trigger on performance degradation

4. **Model Versioning**: How to handle model updates?
   - **Decision**: Store version + timestamp in KV
   - **Later**: A/B testing infrastructure

### Lower Priority

5. **Online Learning**: Should model update incrementally?
   - **Decision**: Batch retraining for MVP (simpler)
   - **Later**: Consider online learning for faster adaptation

---

## Dependencies

```txt
scikit-learn>=1.3.0
lightgbm>=4.0.0
pandas>=2.0.0
numpy>=1.24.0
yfinance>=0.2.0  # For price data / labels
```

---

*Component Version: 1.0*
