# LLM Explainer: Deep Dive

## Purpose

Generate plain-English explanations for stock signals that retail investors can understand and act upon.

---

## Provider: Groq

### Why Groq?

| Factor | Groq | OpenAI | Claude |
|--------|------|--------|--------|
| **Cost** | Free tier | Paid | Paid |
| **Speed** | Very fast | Fast | Fast |
| **Quality** | Good (Llama 3.3 70B) | Excellent | Excellent |
| **Rate Limits** | 30 req/min | N/A | N/A |

**Decision**: Use Groq free tier for MVP. Sufficient quality for explanations.

### Groq Free Tier Limits

- 30 requests per minute
- 14,400 requests per day
- Llama 3.3 70B model available

For our use case (top 10-20 signals per run, ~10 runs/day):
- ~200 requests/day << 14,400 limit

---

## Prompt Engineering

### System Prompt

```python
SYSTEM_PROMPT = """You are a financial analyst explaining stock signals to retail investors.

Guidelines:
1. Be concise - maximum 100 words
2. Be specific - reference the actual signals and data
3. Be actionable - explain what the signals might indicate
4. Avoid jargon - use plain English
5. Never give financial advice - just explain what the data shows
6. Focus on "why this matters" not just "what happened"
7. Mention potential causes and implications

Tone: Professional but accessible. Think "smart friend who works in finance."

IMPORTANT: You are explaining signals, not recommending actions. Always include a disclaimer like "This is informational only" when appropriate."""
```

### User Prompt Template

```python
USER_PROMPT_TEMPLATE = """Explain these signals for {ticker} ({company_name}):

Current SignalScore: {score}/100 ({risk_level} risk)
Score Change: {delta} in past 7 days

Top Signals Detected:
{signals_list}

Category Breakdown:
- Regulatory: {regulatory_score}/100
- Operational: {operational_score}/100
- Narrative: {narrative_score}/100
- Insider: {insider_score}/100

Provide a brief explanation of what these signals indicate and why an investor might want to pay attention. Be specific about the signals detected."""
```

### Signal Formatting

```python
def format_signals_for_prompt(signals: list) -> str:
    """Format top signals for LLM prompt"""
    formatted = []
    for i, signal in enumerate(signals[:5], 1):
        formatted.append(
            f"{i}. [{signal['category'].upper()}] {signal['title']}\n"
            f"   - {signal['description']}"
        )
    return '\n'.join(formatted)
```

---

## Implementation

### Main Explainer Class

```python
from groq import Groq
import hashlib
import json
from datetime import datetime, timedelta

class LLMExplainer:
    def __init__(self, api_key: str, cache_store=None):
        self.client = Groq(api_key=api_key)
        self.cache_store = cache_store
        self.model = "llama-3.3-70b-versatile"

    async def explain(self, result: dict) -> str:
        """Generate explanation for a ticker's signals"""

        # Check cache first
        cache_key = self._generate_cache_key(result)
        if self.cache_store:
            cached = await self.cache_store.get_value(f"llm_{cache_key}")
            if cached and not self._is_expired(cached):
                return cached['explanation']

        # Build prompt
        prompt = self._build_prompt(result)

        # Call LLM
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=200,
                temperature=0.3,
            )

            explanation = response.choices[0].message.content.strip()

            # Cache result
            if self.cache_store:
                await self.cache_store.set_value(f"llm_{cache_key}", {
                    'explanation': explanation,
                    'created_at': datetime.utcnow().isoformat(),
                    'expires_at': (datetime.utcnow() + timedelta(hours=24)).isoformat()
                })

            return explanation

        except Exception as e:
            return f"Explanation unavailable: {str(e)}"

    def _build_prompt(self, result: dict) -> str:
        """Build user prompt from result data"""
        signals = result.get('top_signals', [])
        breakdown = result.get('breakdown', {})

        return USER_PROMPT_TEMPLATE.format(
            ticker=result['ticker'],
            company_name=result.get('company_name', result['ticker']),
            score=result['signal_score'],
            risk_level=result['risk_level'],
            delta=f"+{result.get('score_delta_7d', 0)}" if result.get('score_delta_7d', 0) >= 0 else result.get('score_delta_7d', 0),
            signals_list=format_signals_for_prompt(signals),
            regulatory_score=breakdown.get('regulatory', {}).get('score', 0),
            operational_score=breakdown.get('operational', {}).get('score', 0),
            narrative_score=breakdown.get('narrative', {}).get('score', 0),
            insider_score=breakdown.get('insider', {}).get('score', 0),
        )

    def _generate_cache_key(self, result: dict) -> str:
        """Generate cache key from significant result data"""
        key_data = {
            'ticker': result['ticker'],
            'score_bucket': int(result['signal_score'] / 10) * 10,  # Bucket by 10s
            'signals': sorted([s['type'] for s in result.get('top_signals', [])[:5]])
        }
        return hashlib.md5(json.dumps(key_data, sort_keys=True).encode()).hexdigest()[:16]

    def _is_expired(self, cached: dict) -> bool:
        """Check if cached entry is expired"""
        expires_at = cached.get('expires_at')
        if not expires_at:
            return True
        return datetime.fromisoformat(expires_at) < datetime.utcnow()
```

### Batch Processing

For efficiency, process multiple tickers in batches:

```python
async def explain_batch(self, results: list, top_n: int = 10) -> list:
    """Generate explanations for top N results"""

    # Sort by score, take top N
    sorted_results = sorted(results, key=lambda x: x['signal_score'], reverse=True)
    top_results = sorted_results[:top_n]

    # Generate explanations (with rate limiting)
    for result in top_results:
        result['llm_explanation'] = await self.explain(result)
        await asyncio.sleep(2.1)  # 30 req/min = 1 req/2 sec

    return results
```

---

## Example Outputs

### High Risk Example

**Input:**
```json
{
  "ticker": "XYZ",
  "signal_score": 78,
  "risk_level": "high",
  "top_signals": [
    {"type": "SEC_8K_ACCOUNTANT_CHANGE", "title": "Auditor Change Filed"},
    {"type": "INSIDER_SELL_CLUSTER", "title": "5 Executives Sold $12M in Shares"},
    {"type": "COMPLIANCE_HIRING_SPIKE", "title": "Compliance Roles Up 280%"}
  ]
}
```

**Output:**
> XYZ's SignalScore of 78 indicates elevated risk. Three concerning signals stand out: (1) The company changed auditors, which sometimes precedes financial restatements. (2) Five executives sold $12M worth of shares within a week - unusual clustering that may indicate insider concerns. (3) Compliance hiring surged 280%, often a sign of regulatory issues. Together, these signals suggest potential financial or regulatory challenges ahead. This is informational only - not investment advice.

### Low Risk Example

**Input:**
```json
{
  "ticker": "ABC",
  "signal_score": 22,
  "risk_level": "low",
  "top_signals": [
    {"type": "INSIDER_BUY_LARGE", "title": "CEO Purchased $2M in Shares"}
  ]
}
```

**Output:**
> ABC shows a low SignalScore of 22 with minimal risk signals. The main activity detected was the CEO purchasing $2M in shares, which is typically a positive signal indicating insider confidence. No regulatory concerns, negative press, or operational stress signals were detected in recent data. The company appears to be operating normally based on our monitored signals.

---

## Caching Strategy

### Why Cache?

1. **Cost Savings**: Avoid redundant API calls
2. **Speed**: Instant response for cached explanations
3. **Rate Limits**: Stay within Groq limits

### Cache Key Design

```python
# Cache key includes:
# - Ticker
# - Score bucket (0-10, 10-20, etc.)
# - Signal types (sorted list)

# Same ticker with same signals and similar score = cache hit
# Score changes by 10+ points or new signal types = cache miss
```

### Cache TTL

- **24 hours**: Default TTL
- **Rationale**: Signals don't change meaning, but context might

### Cache Storage

```python
# Store in Apify Key-Value Store
cache_entry = {
    "explanation": "...",
    "created_at": "2025-01-15T08:00:00Z",
    "expires_at": "2025-01-16T08:00:00Z",
    "model": "llama-3.3-70b-versatile",
    "prompt_hash": "abc123"
}
```

---

## Error Handling

### Rate Limit Exceeded

```python
from tenacity import retry, stop_after_attempt, wait_exponential

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=2, min=4, max=30))
async def call_groq_with_retry(self, messages):
    try:
        return self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            max_tokens=200,
            temperature=0.3
        )
    except RateLimitError:
        raise  # Let retry handle it
    except Exception as e:
        return {"error": str(e)}
```

### Fallback Responses

```python
FALLBACK_TEMPLATES = {
    'high': "This stock shows elevated risk signals including {signal_list}. Monitor closely.",
    'neutral': "This stock shows moderate activity. Key signals: {signal_list}.",
    'low': "This stock shows minimal risk signals. No major concerns detected.",
}

def generate_fallback(result: dict) -> str:
    """Generate fallback explanation without LLM"""
    risk = result['risk_level']
    signals = [s['title'] for s in result.get('top_signals', [])[:3]]
    signal_list = ', '.join(signals) if signals else 'none'
    return FALLBACK_TEMPLATES[risk].format(signal_list=signal_list)
```

---

## Quality Guardrails

### Output Validation

```python
def validate_explanation(explanation: str) -> bool:
    """Validate LLM output meets quality standards"""
    # Length check
    if len(explanation) < 50 or len(explanation) > 500:
        return False

    # No financial advice
    advice_phrases = ['buy', 'sell', 'should invest', 'recommend']
    if any(phrase in explanation.lower() for phrase in advice_phrases):
        return False

    # Contains substance
    if explanation.count('.') < 2:
        return False

    return True
```

### Post-Processing

```python
def post_process_explanation(explanation: str) -> str:
    """Clean up LLM output"""
    # Remove markdown formatting if present
    explanation = explanation.replace('**', '').replace('*', '')

    # Ensure ends with period
    if not explanation.endswith('.'):
        explanation += '.'

    # Truncate if too long
    if len(explanation) > 400:
        explanation = explanation[:397] + '...'

    return explanation.strip()
```

---

## TBD / Open Questions

### Critical

1. **Groq Account Setup**: Need to create account and get API key
   - **Action**: Sign up at console.groq.com
   - **Verify**: Free tier limits

2. **Prompt Refinement**: Current prompts need real-world testing
   - **Action**: Run on sample data, iterate
   - **Criteria**: Clear, concise, accurate

### Medium Priority

3. **Multiple Models**: Should we A/B test different models?
   - **Decision**: Start with Llama 3.3 70B only
   - **Later**: Test Mixtral, Gemma for comparison

4. **Explanation Types**: Different explanations for different users?
   - **Decision**: Single explanation type for MVP
   - **Later**: "Technical" vs "Simple" modes

### Lower Priority

5. **Translation**: Support non-English explanations?
   - **Decision**: English only for MVP
   - **Later**: Add language parameter

---

*Component Version: 1.0*
