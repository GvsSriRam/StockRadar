# SEC Collector: Deep Dive

## Purpose

Extract SEC filings from EDGAR to detect regulatory risk signals:
- 8-K filings (material events, executive changes, accountant changes)
- Form 4 (insider transactions)
- 10-K/10-Q (quarterly/annual reports with risk factors)

---

## Data Sources

### SEC EDGAR

**Base URL**: `https://www.sec.gov`

**Key Endpoints**:

| Endpoint | Purpose | Format |
|----------|---------|--------|
| `/cgi-bin/browse-edgar` | Search filings | HTML/Atom |
| `/cgi-bin/own-disp` | Insider transactions | HTML |
| `efts.sec.gov/LATEST/search-index` | Full-text search | JSON |

### CIK (Central Index Key)

Every company has a unique CIK number required for EDGAR queries.

**Lookup Options**:
1. **SEC Company Search**: Query by ticker/name
2. **Pre-built mapping**: Maintain JSON file of ticker→CIK
3. **SEC tickers.json**: Official mapping file at `sec.gov/files/company_tickers.json`

**Recommended**: Use official tickers.json (updated daily by SEC)

---

## Implementation

### CIK Resolution

```python
import httpx

class CIKResolver:
    TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"

    def __init__(self):
        self.cik_map = {}

    async def load_mapping(self):
        """Load official SEC ticker-to-CIK mapping"""
        async with httpx.AsyncClient() as client:
            response = await client.get(self.TICKERS_URL)
            data = response.json()

            # Format: {"0": {"cik_str": "320193", "ticker": "AAPL", "title": "Apple Inc"}, ...}
            for entry in data.values():
                ticker = entry['ticker'].upper()
                cik = str(entry['cik_str']).zfill(10)  # Pad to 10 digits
                self.cik_map[ticker] = cik

    def get_cik(self, ticker: str) -> str | None:
        return self.cik_map.get(ticker.upper())
```

### 8-K Filing Extraction

8-K filings disclose material events. Key items to detect:

| Item | Meaning | Risk Signal |
|------|---------|-------------|
| 1.01 | Material contracts | Medium |
| 1.02 | Termination of material contract | High |
| 2.01 | Acquisition/disposition | Medium |
| 2.02 | Results of operations | Medium |
| 2.05 | Material impairment | High |
| 4.01 | Accountant change | **Very High** |
| 4.02 | Non-reliance on financials | **Very High** |
| 5.02 | Executive departure | High |
| 8.01 | Other events | Low-Medium |

```python
import re
from datetime import datetime, timedelta

class Filing8KExtractor:
    ITEM_PATTERNS = {
        "4.01": r"Item\s*4\.01",
        "4.02": r"Item\s*4\.02",
        "5.02": r"Item\s*5\.02",
        "2.05": r"Item\s*2\.05",
    }

    async def fetch_8k_filings(self, cik: str, days: int = 30) -> list:
        """Fetch recent 8-K filings for a company"""
        url = "https://www.sec.gov/cgi-bin/browse-edgar"
        params = {
            "action": "getcompany",
            "CIK": cik,
            "type": "8-K",
            "dateb": "",
            "owner": "include",
            "count": 40,
            "output": "atom"
        }

        async with httpx.AsyncClient() as client:
            response = await client.get(url, params=params)
            return self._parse_atom_feed(response.text, days)

    def _parse_atom_feed(self, xml_content: str, days: int) -> list:
        """Parse Atom feed of filings"""
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(xml_content, 'lxml-xml')

        cutoff = datetime.now() - timedelta(days=days)
        filings = []

        for entry in soup.find_all('entry'):
            filing_date_elem = entry.find('filing-date')
            if not filing_date_elem:
                continue

            filing_date = datetime.strptime(filing_date_elem.text, "%Y-%m-%d")
            if filing_date < cutoff:
                continue

            filings.append({
                "form_type": "8-K",
                "date": filing_date_elem.text,
                "title": entry.find('title').text if entry.find('title') else "",
                "link": entry.find('link')['href'] if entry.find('link') else "",
            })

        return filings

    async def extract_items(self, filing_url: str) -> list:
        """Extract item numbers from 8-K filing"""
        async with httpx.AsyncClient() as client:
            response = await client.get(filing_url)
            content = response.text

            items_found = []
            for item, pattern in self.ITEM_PATTERNS.items():
                if re.search(pattern, content, re.IGNORECASE):
                    items_found.append(item)

            return items_found
```

### Form 4 (Insider Transactions)

Form 4 reports insider stock transactions within 2 business days.

**Key fields to extract**:
- Insider name and title
- Transaction type (P=Purchase, S=Sale)
- Shares transacted
- Price per share
- Transaction date

```python
class Form4Extractor:
    async def fetch_form4_filings(self, cik: str, days: int = 30) -> list:
        """Fetch recent Form 4 filings"""
        url = "https://www.sec.gov/cgi-bin/browse-edgar"
        params = {
            "action": "getcompany",
            "CIK": cik,
            "type": "4",
            "dateb": "",
            "owner": "only",  # Only insider filings
            "count": 100,
            "output": "atom"
        }

        async with httpx.AsyncClient() as client:
            response = await client.get(url, params=params)
            return self._parse_form4_feed(response.text, days)

    def _parse_form4_feed(self, xml_content: str, days: int) -> list:
        """Parse Form 4 filings"""
        # Similar to 8-K parsing
        # Each Form 4 contains transaction details in XML
        pass

    def detect_selling_cluster(self, transactions: list, window_days: int = 7) -> bool:
        """Detect if multiple insiders sold within a short window"""
        sells = [t for t in transactions if t['transaction_type'] == 'S']

        if len(sells) < 3:
            return False

        # Check if 3+ sells within window
        for i, sell in enumerate(sells):
            window_sells = [s for s in sells
                          if abs((s['date'] - sell['date']).days) <= window_days]
            if len(window_sells) >= 3:
                return True

        return False

    def calculate_net_activity(self, transactions: list) -> dict:
        """Calculate net insider buying/selling"""
        total_bought = sum(t['shares'] * t['price']
                         for t in transactions if t['transaction_type'] == 'P')
        total_sold = sum(t['shares'] * t['price']
                        for t in transactions if t['transaction_type'] == 'S')

        return {
            "total_bought": total_bought,
            "total_sold": total_sold,
            "net": total_bought - total_sold,
            "buy_sell_ratio": total_bought / total_sold if total_sold > 0 else float('inf')
        }
```

---

## Signal Extraction

### From 8-K Filings

```python
def extract_8k_signals(filings: list) -> list:
    signals = []

    for filing in filings:
        items = filing.get('items', [])

        # Accountant change = very high risk
        if "4.01" in items:
            signals.append({
                "type": "SEC_8K_ACCOUNTANT_CHANGE",
                "category": "regulatory",
                "severity": 1.5,
                "title": "Accountant/Auditor Change",
                "description": f"8-K filed on {filing['date']} with Item 4.01",
                "evidence_url": filing['link'],
                "date": filing['date']
            })

        # Executive departure
        if "5.02" in items:
            signals.append({
                "type": "SEC_8K_EXECUTIVE_DEPARTURE",
                "category": "regulatory",
                "severity": 1.0,
                "title": "Executive Departure/Appointment",
                "description": f"8-K filed on {filing['date']} with Item 5.02",
                "evidence_url": filing['link'],
                "date": filing['date']
            })

        # Add more item handlers...

    return signals
```

### From Form 4

```python
def extract_form4_signals(transactions: list) -> list:
    signals = []

    net = calculate_net_activity(transactions)

    # Large insider selling
    if net['total_sold'] > 1_000_000:
        signals.append({
            "type": "INSIDER_SELL_LARGE",
            "category": "insider",
            "severity": min(2.0, net['total_sold'] / 1_000_000),
            "title": f"Large Insider Selling (${net['total_sold']:,.0f})",
            "description": f"{len([t for t in transactions if t['transaction_type'] == 'S'])} insider sells totaling ${net['total_sold']:,.0f}",
            "date": transactions[0]['date'] if transactions else None
        })

    # Selling cluster
    if detect_selling_cluster(transactions):
        signals.append({
            "type": "INSIDER_SELL_CLUSTER",
            "category": "insider",
            "severity": 1.5,
            "title": "Insider Selling Cluster Detected",
            "description": "Multiple insiders sold shares within 7-day window",
            "date": transactions[0]['date'] if transactions else None
        })

    # Large insider buying (positive signal)
    if net['total_bought'] > 500_000:
        signals.append({
            "type": "INSIDER_BUY_LARGE",
            "category": "insider",
            "severity": -1.0,  # Negative = reduces risk
            "title": f"Large Insider Buying (${net['total_bought']:,.0f})",
            "description": "Insiders buying significant shares",
            "date": transactions[0]['date'] if transactions else None
        })

    return signals
```

---

## Rate Limiting & Politeness

SEC has rate limits and expects polite behavior:

```python
import asyncio
from tenacity import retry, stop_after_attempt, wait_exponential

class RateLimiter:
    def __init__(self, requests_per_second: float = 10):
        self.delay = 1.0 / requests_per_second
        self.last_request = 0

    async def wait(self):
        now = asyncio.get_event_loop().time()
        elapsed = now - self.last_request
        if elapsed < self.delay:
            await asyncio.sleep(self.delay - elapsed)
        self.last_request = asyncio.get_event_loop().time()

# Use with retries
@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
async def fetch_with_retry(url: str, rate_limiter: RateLimiter):
    await rate_limiter.wait()
    async with httpx.AsyncClient() as client:
        response = await client.get(url, timeout=30)
        response.raise_for_status()
        return response
```

---

## Output Schema

```python
{
    "ticker": "AAPL",
    "cik": "0000320193",
    "sec_data": {
        "filings_8k": [
            {
                "form_type": "8-K",
                "date": "2025-01-15",
                "items": ["5.02"],
                "title": "Form 8-K",
                "link": "https://sec.gov/..."
            }
        ],
        "filings_form4": [
            {
                "date": "2025-01-14",
                "insider_name": "Tim Cook",
                "insider_title": "CEO",
                "transaction_type": "S",
                "shares": 50000,
                "price": 185.50,
                "total_value": 9275000
            }
        ],
        "summary": {
            "total_8k_30d": 2,
            "total_form4_30d": 5,
            "net_insider_activity": -5000000,
            "high_risk_items_detected": ["5.02"]
        }
    },
    "signals": [
        {
            "type": "SEC_8K_EXECUTIVE_DEPARTURE",
            "category": "regulatory",
            "severity": 1.0,
            "title": "Executive Departure",
            "evidence_url": "https://sec.gov/...",
            "date": "2025-01-15"
        }
    ],
    "collected_at": "2025-01-15T08:00:00Z"
}
```

---

## TBD / Open Questions

1. **SEC Terms of Service**: Verify automated access is permitted (likely yes for EDGAR)
2. **Item Parsing Accuracy**: Need to test item extraction regex on sample filings
3. **Form 4 XML Parsing**: Need to implement detailed Form 4 XML parsing
4. **Historical Data**: How far back should we look for baseline calculation?

### How to Decide

- **SEC ToS**: Read https://www.sec.gov/privacy#security - check for rate limits/restrictions
- **Item Parsing**: Download 20 sample 8-K filings, test regex accuracy
- **Form 4 Parsing**: Use SEC's official Form 4 XML schema for parsing
- **Historical Lookback**: Start with 30 days, adjust based on signal frequency

---

*Component Version: 1.0*
