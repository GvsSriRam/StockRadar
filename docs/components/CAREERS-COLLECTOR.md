# Careers Collector: Deep Dive

## Purpose

Extract job posting data from company career pages to detect operational stress signals:
- Compliance/legal hiring spikes (regulatory trouble incoming)
- Engineering hiring freezes (growth concerns)
- Restructuring keywords in job descriptions
- Overall hiring velocity changes

---

## Challenge: No Standard Format

Unlike SEC (structured data), career pages are highly variable:

| ATS Provider | URL Pattern | Format |
|--------------|-------------|--------|
| Greenhouse | `boards.greenhouse.io/{slug}` | JSON API available |
| Lever | `jobs.lever.co/{slug}` | JSON API available |
| Workday | `{company}.wd1.myworkdayjobs.com` | Complex JS rendering |
| Custom | `{company}.com/careers` | Varies wildly |
| LinkedIn | `linkedin.com/company/{slug}/jobs` | Rate-limited |

---

## URL Discovery Strategy

### Step 1: Resolve Company Domain

```python
# Ticker to domain mapping
TICKER_TO_DOMAIN = {
    "AAPL": "apple.com",
    "GOOGL": "google.com",
    "MSFT": "microsoft.com",
    "TSLA": "tesla.com",
    # ... expand as needed
}

# For unknown tickers, try to infer
def guess_domain(ticker: str, company_name: str) -> str:
    # Try common patterns
    patterns = [
        f"{company_name.lower().replace(' ', '')}.com",
        f"{ticker.lower()}.com",
    ]
    return patterns[0]  # Or verify which exists
```

### Step 2: Try URL Patterns

```python
CAREERS_URL_PATTERNS = [
    # Direct paths
    "https://{domain}/careers",
    "https://{domain}/jobs",
    "https://{domain}/careers/search",
    "https://{domain}/en/careers",

    # Subdomains
    "https://careers.{domain}",
    "https://jobs.{domain}",

    # Common ATS providers
    "https://boards.greenhouse.io/{company_slug}",
    "https://jobs.lever.co/{company_slug}",

    # Workday (requires special handling)
    "https://{company_slug}.wd1.myworkdayjobs.com/en-US/External",
]

async def find_careers_page(domain: str, company_slug: str) -> str | None:
    """Try URL patterns until one works"""
    async with httpx.AsyncClient(follow_redirects=True) as client:
        for pattern in CAREERS_URL_PATTERNS:
            url = pattern.format(domain=domain, company_slug=company_slug)
            try:
                response = await client.head(url, timeout=10)
                if response.status_code == 200:
                    return url
            except:
                continue
    return None
```

### Step 3: Fallback - Search Engine

```python
async def search_careers_page(company_name: str) -> str | None:
    """Use search to find careers page"""
    # Option 1: Google Custom Search API (limited free tier)
    # Option 2: DuckDuckGo HTML scraping
    # Option 3: Store manual mapping for top 500 companies

    # For MVP: Manual mapping is most reliable
    return None
```

---

## Parsing Strategies

### Strategy 1: Greenhouse (JSON API)

Greenhouse provides a public JSON API - easiest to parse.

```python
class GreenhouseParser:
    async def fetch_jobs(self, company_slug: str) -> dict:
        url = f"https://boards-api.greenhouse.io/v1/boards/{company_slug}/jobs"

        async with httpx.AsyncClient() as client:
            response = await client.get(url)
            if response.status_code != 200:
                return {"error": "Not found"}

            data = response.json()
            return self._parse_jobs(data)

    def _parse_jobs(self, data: dict) -> dict:
        jobs = data.get('jobs', [])

        by_department = {}
        for job in jobs:
            dept = job.get('departments', [{}])[0].get('name', 'Other')
            dept_normalized = self._normalize_department(dept)
            by_department[dept_normalized] = by_department.get(dept_normalized, 0) + 1

        return {
            "total_jobs": len(jobs),
            "jobs_by_department": by_department,
            "sample_titles": [j.get('title', '') for j in jobs[:10]]
        }

    def _normalize_department(self, dept: str) -> str:
        dept_lower = dept.lower()

        if any(x in dept_lower for x in ['engineer', 'develop', 'tech', 'software']):
            return 'engineering'
        elif any(x in dept_lower for x in ['legal', 'counsel', 'attorney']):
            return 'legal'
        elif any(x in dept_lower for x in ['compliance', 'regulatory', 'risk']):
            return 'compliance'
        elif any(x in dept_lower for x in ['sales', 'business dev', 'account']):
            return 'sales'
        elif any(x in dept_lower for x in ['hr', 'human', 'people', 'recruit']):
            return 'hr'
        elif any(x in dept_lower for x in ['finance', 'account', 'treasury']):
            return 'finance'
        elif any(x in dept_lower for x in ['market', 'brand', 'commun']):
            return 'marketing'
        else:
            return 'other'
```

### Strategy 2: Lever (JSON API)

Similar to Greenhouse:

```python
class LeverParser:
    async def fetch_jobs(self, company_slug: str) -> dict:
        url = f"https://api.lever.co/v0/postings/{company_slug}"

        async with httpx.AsyncClient() as client:
            response = await client.get(url)
            if response.status_code != 200:
                return {"error": "Not found"}

            jobs = response.json()
            return self._parse_jobs(jobs)

    def _parse_jobs(self, jobs: list) -> dict:
        by_department = {}
        for job in jobs:
            dept = job.get('categories', {}).get('department', 'Other')
            dept_normalized = self._normalize_department(dept)
            by_department[dept_normalized] = by_department.get(dept_normalized, 0) + 1

        return {
            "total_jobs": len(jobs),
            "jobs_by_department": by_department,
            "sample_titles": [j.get('text', '') for j in jobs[:10]]
        }
```

### Strategy 3: HTML Parsing (Generic)

For custom career pages, parse HTML:

```python
from bs4 import BeautifulSoup

class GenericHTMLParser:
    JOB_KEYWORDS = ['job', 'position', 'career', 'opening', 'role']

    async def fetch_jobs(self, url: str) -> dict:
        async with httpx.AsyncClient() as client:
            response = await client.get(url, timeout=30)
            return self._parse_html(response.text)

    def _parse_html(self, html: str) -> dict:
        soup = BeautifulSoup(html, 'lxml')

        # Try to find job listings
        job_elements = []

        # Common patterns
        job_elements.extend(soup.find_all(class_=lambda x: x and 'job' in x.lower()))
        job_elements.extend(soup.find_all('a', href=lambda x: x and '/jobs/' in x.lower()))

        # Count unique jobs
        job_titles = set()
        for elem in job_elements:
            text = elem.get_text(strip=True)
            if len(text) > 5 and len(text) < 200:
                job_titles.add(text)

        # Keyword analysis
        full_text = soup.get_text().lower()
        keyword_counts = {
            'restructuring': full_text.count('restructur'),
            'compliance': full_text.count('compliance'),
            'regulatory': full_text.count('regulatory'),
            'legal': full_text.count('legal'),
        }

        return {
            "total_jobs": len(job_titles),
            "jobs_by_department": {},  # Can't reliably extract
            "sample_titles": list(job_titles)[:10],
            "keyword_counts": keyword_counts
        }
```

### Strategy 4: LLM Extraction (Fallback)

When HTML is complex, use LLM to extract:

```python
from groq import Groq

class LLMJobExtractor:
    def __init__(self, api_key: str):
        self.client = Groq(api_key=api_key)

    async def extract_jobs(self, html: str, company_name: str) -> dict:
        # Truncate HTML to fit context
        text = BeautifulSoup(html, 'lxml').get_text()[:8000]

        response = self.client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {
                    "role": "system",
                    "content": """Extract job posting information from this careers page.
                    Return JSON with:
                    - total_jobs: estimated number of open positions
                    - departments: object with department names and job counts
                    - notable_keywords: any mentions of restructuring, compliance, layoffs, etc.
                    Return only valid JSON."""
                },
                {"role": "user", "content": f"Careers page for {company_name}:\n\n{text}"}
            ],
            max_tokens=500,
            temperature=0
        )

        try:
            import json
            return json.loads(response.choices[0].message.content)
        except:
            return {"error": "LLM extraction failed"}
```

---

## Signal Extraction

### Baseline Comparison

```python
class CareersSignalExtractor:
    def __init__(self):
        self.baselines = {}

    def extract_signals(self, current_data: dict, ticker: str) -> list:
        signals = []
        baseline = self.baselines.get(ticker, {})

        # Legal/Compliance hiring spike
        current_legal = current_data.get('jobs_by_department', {}).get('legal', 0)
        current_compliance = current_data.get('jobs_by_department', {}).get('compliance', 0)
        baseline_legal = baseline.get('legal_avg', current_legal)
        baseline_compliance = baseline.get('compliance_avg', current_compliance)

        if current_legal > baseline_legal * 2 and current_legal > 3:
            signals.append({
                "type": "LEGAL_HIRING_SPIKE",
                "category": "operational",
                "severity": min(2.0, current_legal / baseline_legal),
                "title": f"Legal Hiring Spike ({current_legal} roles)",
                "description": f"Legal jobs up {((current_legal/baseline_legal)-1)*100:.0f}% vs baseline",
            })

        if current_compliance > baseline_compliance * 2 and current_compliance > 3:
            signals.append({
                "type": "COMPLIANCE_HIRING_SPIKE",
                "category": "operational",
                "severity": min(2.0, current_compliance / baseline_compliance),
                "title": f"Compliance Hiring Spike ({current_compliance} roles)",
                "description": f"Compliance jobs up {((current_compliance/baseline_compliance)-1)*100:.0f}% vs baseline",
            })

        # Engineering hiring drop
        current_eng = current_data.get('jobs_by_department', {}).get('engineering', 0)
        baseline_eng = baseline.get('engineering_avg', current_eng)

        if baseline_eng > 10 and current_eng < baseline_eng * 0.5:
            signals.append({
                "type": "ENGINEERING_HIRING_DROP",
                "category": "operational",
                "severity": 1.0,
                "title": f"Engineering Hiring Slowdown",
                "description": f"Engineering jobs down {(1-(current_eng/baseline_eng))*100:.0f}% vs baseline",
            })

        # Keyword signals
        keywords = current_data.get('keyword_counts', {})
        if keywords.get('restructuring', 0) > 0:
            signals.append({
                "type": "RESTRUCTURING_KEYWORD",
                "category": "operational",
                "severity": 0.8,
                "title": "Restructuring Keywords Detected",
                "description": f"Found {keywords['restructuring']} mentions of 'restructuring' in job posts",
            })

        return signals

    def update_baseline(self, ticker: str, current_data: dict):
        """Update rolling baseline"""
        if ticker not in self.baselines:
            self.baselines[ticker] = {
                'history': [],
                'legal_avg': 0,
                'compliance_avg': 0,
                'engineering_avg': 0,
            }

        baseline = self.baselines[ticker]
        baseline['history'].append(current_data)
        baseline['history'] = baseline['history'][-30:]  # Keep 30 samples

        # Recalculate averages
        dept_data = [h.get('jobs_by_department', {}) for h in baseline['history']]
        baseline['legal_avg'] = sum(d.get('legal', 0) for d in dept_data) / len(dept_data)
        baseline['compliance_avg'] = sum(d.get('compliance', 0) for d in dept_data) / len(dept_data)
        baseline['engineering_avg'] = sum(d.get('engineering', 0) for d in dept_data) / len(dept_data)
```

---

## Unified Collector

```python
class CareersCollector:
    def __init__(self, groq_api_key: str = None):
        self.greenhouse = GreenhouseParser()
        self.lever = LeverParser()
        self.html_parser = GenericHTMLParser()
        self.llm_extractor = LLMJobExtractor(groq_api_key) if groq_api_key else None

    async def collect(self, ticker: str) -> dict:
        """Main entry point"""
        domain = self._get_domain(ticker)
        company_slug = self._get_slug(ticker)

        # Try strategies in order of reliability
        result = await self._try_greenhouse(company_slug)
        if result and not result.get('error'):
            return {'source': 'greenhouse', **result}

        result = await self._try_lever(company_slug)
        if result and not result.get('error'):
            return {'source': 'lever', **result}

        url = await find_careers_page(domain, company_slug)
        if url:
            result = await self.html_parser.fetch_jobs(url)
            if result.get('total_jobs', 0) > 0:
                return {'source': 'html', 'url': url, **result}

            # Fallback to LLM
            if self.llm_extractor:
                html = await self._fetch_html(url)
                result = await self.llm_extractor.extract_jobs(html, ticker)
                return {'source': 'llm', 'url': url, **result}

        return {'error': 'No careers page found', 'source': None}

    async def _try_greenhouse(self, slug: str) -> dict:
        return await self.greenhouse.fetch_jobs(slug)

    async def _try_lever(self, slug: str) -> dict:
        return await self.lever.fetch_jobs(slug)
```

---

## Output Schema

```python
{
    "ticker": "AAPL",
    "careers_data": {
        "source": "greenhouse",  # or lever, html, llm
        "url": "https://boards.greenhouse.io/apple",
        "total_jobs": 145,
        "jobs_by_department": {
            "engineering": 45,
            "legal": 12,
            "compliance": 8,
            "sales": 30,
            "marketing": 15,
            "hr": 5,
            "finance": 10,
            "other": 20
        },
        "sample_titles": [
            "Senior Software Engineer",
            "Compliance Manager",
            ...
        ],
        "keyword_counts": {
            "restructuring": 0,
            "compliance": 3,
            "regulatory": 2,
            "incident": 0
        }
    },
    "signals": [
        {
            "type": "COMPLIANCE_HIRING_SPIKE",
            "category": "operational",
            "severity": 1.5,
            "title": "Compliance Hiring Spike (8 roles)",
            "description": "Compliance jobs up 150% vs baseline"
        }
    ],
    "collected_at": "2025-01-15T08:00:00Z"
}
```

---

## TBD / Open Questions

### Critical

1. **Ticker-to-Domain Mapping**: Need comprehensive mapping for target tickers
   - **Decision**: Build initial mapping for S&P 100, expand as needed
   - **How**: Manually curate or use company data API

2. **ATS Detection**: How to reliably detect which ATS a company uses?
   - **Decision**: Try Greenhouse/Lever APIs first, then fall back to HTML
   - **How**: Test against 50 sample companies

### Medium Priority

3. **Rate Limiting**: Some career sites may block rapid requests
   - **Decision**: Add delays, rotate user agents
   - **How**: Test and adjust per site

4. **JavaScript Rendering**: Workday and some custom sites need JS
   - **Decision**: Skip for MVP, add Playwright later if needed
   - **How**: Track which sites fail, prioritize for Phase 2

### Lower Priority

5. **LinkedIn as Backup**: Can we use LinkedIn job counts?
   - **Decision**: Avoid - heavy rate limiting, ToS concerns
   - **Alternative**: Manual spot-checks only

---

## Testing Plan

1. **Unit Tests**: Test each parser with sample HTML/JSON
2. **Integration**: Test URL discovery on 50 companies
3. **Coverage**: Track success rate by ATS type
4. **Edge Cases**: Handle companies with no career pages

---

*Component Version: 1.0*
