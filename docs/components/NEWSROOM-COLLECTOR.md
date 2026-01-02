# Newsroom Collector: Deep Dive

## Purpose

Extract press releases and announcements from company investor relations / newsroom pages to detect narrative shift signals:
- Negative keyword mentions (investigation, restatement, material weakness)
- Communication pattern changes (frequency drops, Friday releases)
- Sentiment shifts in official communications

---

## Data Sources

### Primary: Company IR/Newsroom Pages

| Pattern | Example |
|---------|---------|
| `/news` | apple.com/news |
| `/newsroom` | apple.com/newsroom |
| `/press` | microsoft.com/press |
| `/investor-relations` | tesla.com/investor-relations |
| `/ir` | nvidia.com/ir |
| Subdomain | investors.google.com |

### Secondary: PR Distribution Services

| Service | Coverage | Access |
|---------|----------|--------|
| PR Newswire | Broad | API (paid) or scrape |
| Business Wire | Broad | API (paid) or scrape |
| GlobeNewswire | Good | Scrape |

**For MVP**: Focus on company pages only (free, reliable)

---

## URL Discovery

```python
NEWSROOM_URL_PATTERNS = [
    "https://{domain}/newsroom",
    "https://{domain}/news",
    "https://{domain}/press",
    "https://{domain}/press-releases",
    "https://{domain}/investor-relations",
    "https://{domain}/investors",
    "https://{domain}/ir",
    "https://investors.{domain}",
    "https://newsroom.{domain}",
    "https://ir.{domain}",
]

async def find_newsroom_page(domain: str) -> str | None:
    """Try URL patterns until one works"""
    async with httpx.AsyncClient(follow_redirects=True, timeout=10) as client:
        for pattern in NEWSROOM_URL_PATTERNS:
            url = pattern.format(domain=domain)
            try:
                response = await client.head(url)
                if response.status_code == 200:
                    return url
            except:
                continue
    return None
```

---

## Parsing Strategy

### HTML Extraction

```python
from bs4 import BeautifulSoup
from datetime import datetime
import re

class NewsroomParser:
    # Patterns to find press releases
    ARTICLE_SELECTORS = [
        'article',
        '.press-release',
        '.news-item',
        '.press-item',
        '[class*="release"]',
        '[class*="news"]',
    ]

    DATE_PATTERNS = [
        r'(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})',
        r'(\w+ \d{1,2}, \d{4})',
        r'(\d{4}-\d{2}-\d{2})',
    ]

    async def fetch_and_parse(self, url: str) -> dict:
        async with httpx.AsyncClient() as client:
            response = await client.get(url, timeout=30)
            return self._parse_html(response.text, url)

    def _parse_html(self, html: str, base_url: str) -> dict:
        soup = BeautifulSoup(html, 'lxml')

        press_releases = []

        # Try each selector
        for selector in self.ARTICLE_SELECTORS:
            elements = soup.select(selector)
            for elem in elements:
                pr = self._extract_press_release(elem, base_url)
                if pr:
                    press_releases.append(pr)

        # Fallback: Find links with "press" or "release" in href
        if not press_releases:
            links = soup.find_all('a', href=True)
            for link in links:
                href = link.get('href', '')
                text = link.get_text(strip=True)
                if 'release' in href.lower() or 'press' in href.lower():
                    if len(text) > 20:
                        press_releases.append({
                            'title': text[:200],
                            'url': self._resolve_url(href, base_url),
                            'date': None,
                            'snippet': ''
                        })

        # Deduplicate by title
        seen = set()
        unique = []
        for pr in press_releases:
            if pr['title'] not in seen:
                seen.add(pr['title'])
                unique.append(pr)

        return {
            'press_releases': unique[:50],  # Limit to 50
            'total_found': len(unique),
        }

    def _extract_press_release(self, elem, base_url: str) -> dict | None:
        # Find title
        title_elem = elem.find(['h1', 'h2', 'h3', 'a'])
        if not title_elem:
            return None

        title = title_elem.get_text(strip=True)
        if len(title) < 10:
            return None

        # Find link
        link_elem = elem.find('a', href=True)
        url = self._resolve_url(link_elem['href'], base_url) if link_elem else None

        # Find date
        date_text = elem.get_text()
        date = self._extract_date(date_text)

        # Get snippet
        snippet = elem.get_text(strip=True)[:200]

        return {
            'title': title[:200],
            'url': url,
            'date': date,
            'snippet': snippet
        }

    def _extract_date(self, text: str) -> str | None:
        for pattern in self.DATE_PATTERNS:
            match = re.search(pattern, text)
            if match:
                return match.group(1)
        return None

    def _resolve_url(self, href: str, base_url: str) -> str:
        from urllib.parse import urljoin
        return urljoin(base_url, href)
```

---

## Keyword Detection

### Negative Keywords

```python
NEGATIVE_KEYWORDS = {
    # Regulatory/Legal
    'investigation': {'weight': 1.0, 'category': 'regulatory'},
    'investigated': {'weight': 1.0, 'category': 'regulatory'},
    'subpoena': {'weight': 1.2, 'category': 'regulatory'},
    'enforcement': {'weight': 0.8, 'category': 'regulatory'},
    'settlement': {'weight': 0.7, 'category': 'regulatory'},
    'lawsuit': {'weight': 0.8, 'category': 'regulatory'},
    'litigation': {'weight': 0.7, 'category': 'regulatory'},

    # Financial/Accounting
    'restatement': {'weight': 1.5, 'category': 'financial'},
    'restated': {'weight': 1.5, 'category': 'financial'},
    'material weakness': {'weight': 1.3, 'category': 'financial'},
    'impairment': {'weight': 0.9, 'category': 'financial'},
    'writedown': {'weight': 0.8, 'category': 'financial'},
    'write-down': {'weight': 0.8, 'category': 'financial'},

    # Operational
    'restructuring': {'weight': 0.7, 'category': 'operational'},
    'layoff': {'weight': 0.9, 'category': 'operational'},
    'workforce reduction': {'weight': 0.9, 'category': 'operational'},
    'furlough': {'weight': 0.8, 'category': 'operational'},
    'downsizing': {'weight': 0.8, 'category': 'operational'},

    # Leadership
    'resignation': {'weight': 0.6, 'category': 'leadership'},
    'departure': {'weight': 0.5, 'category': 'leadership'},
    'terminated': {'weight': 0.8, 'category': 'leadership'},
}

def scan_for_keywords(text: str) -> dict:
    """Scan text for negative keywords"""
    text_lower = text.lower()
    found = {}

    for keyword, info in NEGATIVE_KEYWORDS.items():
        count = text_lower.count(keyword)
        if count > 0:
            found[keyword] = {
                'count': count,
                'weight': info['weight'],
                'category': info['category'],
                'weighted_score': count * info['weight']
            }

    return found
```

### Release Timing Analysis

```python
from datetime import datetime

def analyze_timing(press_releases: list) -> dict:
    """Analyze release timing for bad news patterns"""
    results = {
        'friday_releases': 0,
        'after_hours_releases': 0,
        'holiday_releases': 0,
    }

    for pr in press_releases:
        if not pr.get('date'):
            continue

        try:
            date = parse_date(pr['date'])
            if date.weekday() == 4:  # Friday
                results['friday_releases'] += 1
            # Add more timing analysis...
        except:
            continue

    return results
```

---

## Signal Extraction

```python
class NewsroomSignalExtractor:
    def extract_signals(self, data: dict, baseline: dict = None) -> list:
        signals = []
        press_releases = data.get('press_releases', [])

        # Scan all recent press releases for keywords
        all_text = ' '.join([
            f"{pr.get('title', '')} {pr.get('snippet', '')}"
            for pr in press_releases
        ])
        keywords_found = scan_for_keywords(all_text)

        # Investigation mentioned
        if 'investigation' in keywords_found or 'investigated' in keywords_found:
            signals.append({
                'type': 'INVESTIGATION_MENTIONED',
                'category': 'narrative',
                'severity': 1.2,
                'title': 'Investigation Mentioned in Press Release',
                'description': 'Company referenced investigation in official communication',
            })

        # Restatement mentioned
        if 'restatement' in keywords_found or 'restated' in keywords_found:
            signals.append({
                'type': 'RESTATEMENT_MENTIONED',
                'category': 'narrative',
                'severity': 1.5,
                'title': 'Financial Restatement Mentioned',
                'description': 'Company referenced financial restatement',
            })

        # Material weakness
        if 'material weakness' in keywords_found:
            signals.append({
                'type': 'MATERIAL_WEAKNESS_MENTIONED',
                'category': 'narrative',
                'severity': 1.3,
                'title': 'Material Weakness Disclosed',
                'description': 'Company disclosed material weakness in internal controls',
            })

        # Layoff/restructuring
        layoff_keywords = ['layoff', 'workforce reduction', 'restructuring', 'downsizing']
        if any(k in keywords_found for k in layoff_keywords):
            signals.append({
                'type': 'LAYOFF_ANNOUNCED',
                'category': 'narrative',
                'severity': 1.0,
                'title': 'Layoff/Restructuring Announced',
                'description': 'Company announced workforce changes',
            })

        # Friday release pattern (bad news timing)
        timing = analyze_timing(press_releases)
        if timing['friday_releases'] >= 2:
            signals.append({
                'type': 'FRIDAY_RELEASE_PATTERN',
                'category': 'narrative',
                'severity': 0.5,
                'title': 'Friday Release Pattern Detected',
                'description': f"{timing['friday_releases']} releases on Fridays (potential bad news timing)",
            })

        # Communication frequency drop
        if baseline:
            baseline_freq = baseline.get('avg_releases_per_month', 5)
            current_freq = len([pr for pr in press_releases if self._is_recent(pr, days=30)])
            if baseline_freq > 3 and current_freq < baseline_freq * 0.5:
                signals.append({
                    'type': 'COMMUNICATION_DROP',
                    'category': 'narrative',
                    'severity': 0.6,
                    'title': 'Communication Frequency Dropped',
                    'description': f'Press releases down {(1-current_freq/baseline_freq)*100:.0f}% vs baseline',
                })

        return signals

    def _is_recent(self, pr: dict, days: int = 30) -> bool:
        date_str = pr.get('date')
        if not date_str:
            return True  # Assume recent if no date
        try:
            date = parse_date(date_str)
            return (datetime.now() - date).days <= days
        except:
            return True
```

---

## Unified Collector

```python
class NewsroomCollector:
    def __init__(self):
        self.parser = NewsroomParser()
        self.signal_extractor = NewsroomSignalExtractor()

    async def collect(self, ticker: str) -> dict:
        domain = get_domain_for_ticker(ticker)
        url = await find_newsroom_page(domain)

        if not url:
            return {
                'ticker': ticker,
                'error': 'No newsroom page found',
                'newsroom_data': None,
                'signals': []
            }

        data = await self.parser.fetch_and_parse(url)

        # Keyword analysis
        all_text = ' '.join([
            f"{pr.get('title', '')} {pr.get('snippet', '')}"
            for pr in data.get('press_releases', [])
        ])
        keywords = scan_for_keywords(all_text)

        # Extract signals
        signals = self.signal_extractor.extract_signals(data)

        return {
            'ticker': ticker,
            'newsroom_url': url,
            'newsroom_data': {
                'press_releases': data.get('press_releases', [])[:20],  # Top 20
                'total_found': data.get('total_found', 0),
                'keywords_detected': keywords,
            },
            'signals': signals,
            'collected_at': datetime.utcnow().isoformat()
        }
```

---

## Output Schema

```python
{
    "ticker": "TSLA",
    "newsroom_url": "https://ir.tesla.com",
    "newsroom_data": {
        "press_releases": [
            {
                "title": "Tesla Announces Q4 2024 Results",
                "url": "https://ir.tesla.com/press/q4-2024",
                "date": "2025-01-14",
                "snippet": "Tesla reports record deliveries..."
            }
        ],
        "total_found": 45,
        "keywords_detected": {
            "restructuring": {
                "count": 2,
                "weight": 0.7,
                "category": "operational",
                "weighted_score": 1.4
            }
        }
    },
    "signals": [
        {
            "type": "LAYOFF_ANNOUNCED",
            "category": "narrative",
            "severity": 1.0,
            "title": "Layoff/Restructuring Announced",
            "description": "Company announced workforce changes"
        }
    ],
    "collected_at": "2025-01-15T08:00:00Z"
}
```

---

## TBD / Open Questions

### Critical

1. **URL Discovery Success Rate**: What % of companies have detectable newsroom pages?
   - **Test**: Try patterns on S&P 100 companies
   - **Fallback**: Manual mapping for failures

2. **Date Parsing Accuracy**: Many formats exist
   - **Decision**: Use dateutil.parser with fuzzy=True
   - **Fallback**: Treat undated as recent

### Medium Priority

3. **Sentiment Analysis**: Should we add NLP sentiment beyond keywords?
   - **Decision**: Keep keyword-based for MVP (simpler, explainable)
   - **Later**: Add LLM sentiment for top signals

4. **Historical Depth**: How far back should we look?
   - **Decision**: 30 days for signals, 90 days for baseline
   - **Rationale**: Captures recent events without noise

### Lower Priority

5. **PR Wire Integration**: Add PR Newswire / Business Wire?
   - **Decision**: Skip for MVP (adds complexity)
   - **Revisit**: If company pages have poor coverage

---

## Testing Plan

1. **URL Discovery**: Test on S&P 100, track success rate
2. **Parsing**: Validate extracted titles match actual headlines
3. **Keyword Detection**: Test with known bad-news releases
4. **Edge Cases**: Empty pages, heavily JS-rendered sites

---

*Component Version: 1.0*
