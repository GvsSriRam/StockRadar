# Demo & Deployment Guide (v2.0)

## Overview

This guide covers:
1. Store listing (MAU-optimized)
2. Local development setup
3. Apify deployment
4. Demo preparation
5. Launch checklist

---

## Store Listing (MAU-Optimized)

### Actor Name (SEO-Optimized)

```
SEC Filing Risk Scanner – 8-K Filings & Insider Trading Alerts
```

**Why this name wins:**
- Starts with "SEC" (high-value search term)
- Contains "8-K" (users search for this)
- Contains "Insider Trading" (money keyword)
- "Scanner" is action-oriented

### Store README (User-Focused, Not Architecture-Focused)

```markdown
# SEC Filing Risk Scanner

Scan any stock for SEC red flags before the market reacts.

## When Should I Run This?

| Situation | Why It Helps |
|-----------|--------------|
| **Before earnings** | Check for unusual insider selling |
| **After a price drop** | See if insiders sold beforehand |
| **Weekly portfolio check** | Monitor your holdings for new filings |
| **Due diligence** | Research a stock before buying |

## What Do I Get?

- **Risk Score** (0-100) with clear thresholds
- **Red Flags** detected from SEC filings
- **Insider Activity** summary (who sold, how much)
- **Evidence Links** to actual SEC filings
- **Plain-English Explanation** of what it means

## What Red Flags Are Detected?

| Signal | What It Means |
|--------|--------------|
| **Auditor Change** | Company switched accountants (often precedes restatements) |
| **Executive Departure** | C-suite resignation filed |
| **Insider Selling Cluster** | Multiple execs sold same week |
| **Large Insider Sale** | Single sale > $1M |

## Example Input

{
  "tickers": ["AAPL", "TSLA", "NVDA"],
  "lookbackDays": 30
}

Just paste your tickers. That's it.

## Example Output

{
  "ticker": "TSLA",
  "riskScore": 72,
  "riskLevel": "high",
  "redFlags": [
    {
      "type": "INSIDER_SELL_CLUSTER",
      "title": "3 Executives Sold $8.2M This Week",
      "evidenceUrl": "https://sec.gov/..."
    }
  ],
  "explanation": "Tesla shows elevated risk. Multiple executives sold shares within days..."
}

## Risk Score Explained

| Score | Level | Meaning |
|-------|-------|---------|
| 0-30 | Low | Normal activity |
| 31-50 | Moderate | Worth monitoring |
| 51-70 | Elevated | Pay attention |
| 71-100 | High | Significant red flags |

## Set Up Weekly Monitoring

1. Click "Schedule" in Apify Console
2. Select "Weekly"
3. Enter your tickers
4. Get automatic risk reports

## Pricing

~$0.01 per 10 tickers. Most users stay in free tier.

## Try It Now

1. Click "Try for free"
2. Enter: ["AAPL", "TSLA", "NVDA"]
3. Get your risk report in ~60 seconds
```

---

## Local Development Setup

### Prerequisites

```bash
# Python 3.11+
python --version  # Should be 3.11+

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### Required Accounts

| Service | Purpose | Setup |
|---------|---------|-------|
| **Apify** | Actor hosting | [apify.com](https://apify.com) - Free tier |
| **Groq** | LLM API | [console.groq.com](https://console.groq.com) - Free tier |

### Environment Variables

```bash
# .env file (local development only)
GROQ_API_KEY=your_groq_api_key_here
APIFY_TOKEN=your_apify_token_here  # For local testing
```

### Project Structure

```
sec-filing-risk-scanner/
├── .actor/
│   ├── actor.json
│   └── input_schema.json
├── src/
│   ├── __init__.py
│   ├── main.py
│   ├── sec_collector.py
│   ├── llm_analyzer.py
│   ├── scorer.py
│   └── formatter.py
├── tests/
├── requirements.txt
├── Dockerfile
└── README.md
```

---

## Local Testing

### Run Actor Locally

```bash
# Using Apify CLI
npm install -g apify-cli
apify login  # Enter your API token

# Run with test input
apify run --input='{"tickers": ["AAPL", "TSLA"], "includeLlmExplanation": false}'

# Or run directly with Python
python -m src.main
```

### Test Input Examples

```json
// Minimal test
{
  "tickers": ["AAPL"]
}

// Full test
{
  "tickers": ["AAPL", "TSLA", "NVDA", "MSFT", "GOOGL"],
  "includeLlmExplanation": true,
  "topSignalsCount": 5,
  "alertThreshold": 70
}

// With webhook
{
  "tickers": ["AAPL"],
  "webhookUrl": "https://webhook.site/your-unique-url"
}
```

### Unit Tests

```bash
# Run all tests
pytest tests/

# Run specific test
pytest tests/test_scorer.py -v

# With coverage
pytest --cov=src tests/
```

---

## Apify Deployment

### Step 1: Create Actor on Apify

```bash
# Login to Apify
apify login

# Push to Apify (creates Actor if doesn't exist)
apify push
```

Or via Apify Console:
1. Go to [console.apify.com](https://console.apify.com)
2. Click "Actors" → "Create new"
3. Choose "Start from scratch" → Python
4. Upload your code

### Step 2: Configure Secrets

In Apify Console:
1. Go to Actor → Settings → Environment variables
2. Add: `GROQ_API_KEY` = your_api_key (mark as secret)

### Step 3: Test on Apify

1. Go to Actor → Console
2. Enter test input
3. Click "Start"
4. Check output in Dataset

### Step 4: Publish to Store

1. Go to Actor → Publication
2. Fill in all fields:
   - Title: `SEC Filing Risk Scanner – 8-K Filings & Insider Trading Alerts`
   - Categories: Finance, News
   - Description: Use the Store README from above
3. Add screenshots:
   - Input screen with sample tickers
   - JSON output showing scores and signals
   - A clear "before/after" or risk level visualization
4. Click "Publish"

---

## Demo Preparation

### Demo Script (3 minutes)

#### Opening (30 sec)
> "By the time bad news hits CNBC, the stock has already dropped.
> What if you could see warning signs in SEC filings before everyone else?"

#### Demo (2 min)

1. **Show the input** (10 sec)
   > "Just paste your tickers. That's it."
   ```
   Input: ["AAPL", "TSLA", "NVDA"]
   ```

2. **Run and show results** (60 sec)
   - Point to the risk score
   - Show the red flags detected
   - Click the SEC evidence link
   - Read the AI explanation aloud

3. **Show scheduled monitoring** (30 sec)
   > "Set this to run weekly. Get alerts when scores spike."

#### Case Study (30 sec)
> "Last month, this scanner detected an auditor change at [Company].
> Score jumped to 78. Three weeks later, they announced a restatement."

#### Close (15 sec)
> "Try it free. Paste your portfolio tickers. Get your risk report in 60 seconds."

### Demo Data Preparation

```python
# Create compelling demo data ahead of time
DEMO_TICKERS = [
    "AAPL",   # Usually low score (stable)
    "TSLA",   # Often has insider activity
    "NVDA",   # Good for comparison
    "XYZ",    # Pick one with actual signals
]

# Pre-run the Actor to ensure data is fresh
# Save screenshots of interesting outputs
```

### Demo Video Recording

1. **Screen recording** with Loom or OBS
2. **Voiceover** explaining each step
3. **Captions** for accessibility
4. **Length**: 2-3 minutes max
5. **Upload** to YouTube, embed in README

---

## Alert Integrations

### Discord Webhook

```python
async def send_discord_alert(webhook_url: str, result: dict):
    """Send alert to Discord"""
    embed = {
        "title": f"🚨 Signal Alert: {result['ticker']}",
        "description": f"SignalScore: **{result['signal_score']}** ({result['risk_level'].upper()})",
        "color": 15158332 if result['signal_score'] > 70 else 16776960,
        "fields": [
            {
                "name": "Top Signal",
                "value": result['top_signals'][0]['title'] if result['top_signals'] else "None",
                "inline": False
            },
            {
                "name": "Explanation",
                "value": result.get('llm_explanation', 'N/A')[:500],
                "inline": False
            }
        ],
        "timestamp": datetime.utcnow().isoformat()
    }

    async with httpx.AsyncClient() as client:
        await client.post(webhook_url, json={"embeds": [embed]})
```

### Telegram Bot

```python
async def send_telegram_alert(bot_token: str, chat_id: str, result: dict):
    """Send alert to Telegram"""
    message = f"""
🚨 *Signal Alert: {result['ticker']}*

SignalScore: *{result['signal_score']}* ({result['risk_level'].upper()})

Top Signal: {result['top_signals'][0]['title'] if result['top_signals'] else 'None'}

{result.get('llm_explanation', '')[:300]}
"""
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    async with httpx.AsyncClient() as client:
        await client.post(url, json={
            "chat_id": chat_id,
            "text": message,
            "parse_mode": "Markdown"
        })
```

### Email (SendGrid)

```python
import sendgrid
from sendgrid.helpers.mail import Mail

def send_email_alert(api_key: str, to_email: str, result: dict):
    """Send alert via SendGrid"""
    sg = sendgrid.SendGridAPIClient(api_key=api_key)

    message = Mail(
        from_email='alerts@stocksignalradar.com',
        to_emails=to_email,
        subject=f'🚨 Signal Alert: {result["ticker"]} - Score {result["signal_score"]}',
        html_content=f"""
        <h2>Stock Signal Alert</h2>
        <p><strong>{result['ticker']}</strong> - SignalScore: {result['signal_score']} ({result['risk_level']})</p>
        <h3>Top Signals:</h3>
        <ul>
        {''.join(f"<li>{s['title']}</li>" for s in result['top_signals'][:3])}
        </ul>
        <h3>AI Analysis:</h3>
        <p>{result.get('llm_explanation', 'N/A')}</p>
        """
    )

    sg.send(message)
```

---

## Launch Checklist

### Pre-Launch (1-2 days before)

- [ ] All tests passing
- [ ] Actor runs successfully on Apify
- [ ] Store listing complete with screenshots
- [ ] Demo video recorded and uploaded
- [ ] README polished
- [ ] Groq API key configured as secret
- [ ] Test run with 10+ tickers
- [ ] Webhook integrations tested

### Launch Day

- [ ] Publish Actor to Store
- [ ] Post to r/algotrading
- [ ] Post to r/stocks (if allowed)
- [ ] Tweet announcement
- [ ] Post on Dev.to
- [ ] Share in Apify Discord
- [ ] Notify personal network

### Post-Launch (Week 1)

- [ ] Monitor for errors/issues
- [ ] Respond to user feedback
- [ ] Fix any bugs reported
- [ ] Track MAU progress
- [ ] Post daily "signal of the day" on Twitter
- [ ] Engage with community questions

### Week 2+

- [ ] Create case study content
- [ ] Product Hunt launch (if ready)
- [ ] Hacker News Show HN
- [ ] Weekly newsletter format
- [ ] Iterate based on feedback

---

## Monitoring & Analytics

### Apify Dashboard

- **Runs**: Track daily/weekly usage
- **Success Rate**: Monitor for failures
- **Cost**: Track CU usage

### Custom Analytics

```python
# Log key metrics to dataset
analytics = {
    "run_id": Actor.get_env()['actorRunId'],
    "timestamp": datetime.utcnow().isoformat(),
    "tickers_analyzed": len(tickers),
    "signals_detected": total_signals,
    "avg_score": avg_score,
    "high_risk_count": len([r for r in results if r['signal_score'] > 70]),
    "llm_calls": llm_call_count,
    "duration_seconds": run_duration,
}
await dataset.push_data({"_analytics": analytics})
```

---

## Troubleshooting

### Common Issues

| Issue | Cause | Solution |
|-------|-------|----------|
| SEC rate limiting | Too many requests | Add delays between requests |
| Career page not found | URL pattern mismatch | Add company to manual mapping |
| LLM timeout | Groq rate limit | Add retry with backoff |
| Empty signals | Data collection failed | Check logs, verify URLs |
| High CU usage | Memory/time issues | Reduce concurrency, optimize |

### Logging

```python
from apify import Actor

# Info logging
Actor.log.info(f"Processing {ticker}")

# Warning
Actor.log.warning(f"No careers page found for {ticker}")

# Error
Actor.log.error(f"SEC fetch failed: {error}")

# Debug (only in development)
Actor.log.debug(f"Raw data: {data}")
```

---

## Cost Estimation

### Apify CU Usage

| Scenario | Memory | Duration | CU per Run |
|----------|--------|----------|------------|
| 5 tickers | 256MB | 2 min | 0.008 |
| 20 tickers | 256MB | 5 min | 0.02 |
| 50 tickers | 512MB | 10 min | 0.08 |

### Monthly Estimates (Free Tier: 5 CU)

| Usage | Runs/Day | CU/Month | Status |
|-------|----------|----------|--------|
| Light | 5 | 3 | OK |
| Medium | 10 | 6 | Slightly over |
| Heavy | 20 | 12 | Need paid |

### LLM Costs (Groq Free)

- 30 requests/minute
- 14,400 requests/day
- Our usage: ~50-100 requests/day
- **Status**: Well within free tier

---

*Document Version: 1.0*
*Last Updated: December 29, 2024*
