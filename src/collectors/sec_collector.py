"""
SEC EDGAR Data Collector

Collects 8-K filings and Form 4 insider transactions from SEC EDGAR.
Implements the DataCollector protocol with proper rate limiting and error handling.
"""

import asyncio
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Optional
from xml.etree import ElementTree

import httpx
from bs4 import BeautifulSoup
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)

logger = logging.getLogger(__name__)

from ..config import Settings, get_settings
from ..core.interfaces import DataCollector
from ..core.models import (
    Filing8K,
    InsiderTransaction,
    SECFilingData,
)
from ..core.exceptions import (
    CollectorError,
    TickerNotFoundError,
    SECRateLimitError,
    SECFetchError,
)


class SECCollector(DataCollector):
    """
    Collects SEC filings from EDGAR.

    Features:
    - Rate limiting (10 requests/second)
    - CIK caching
    - Async HTTP client
    - Proper error handling with retries
    """

    # 8-K Items of interest
    ITEM_PATTERNS = [
        (r"Item\s*1\.01", "1.01 - Entry into Material Agreement"),
        (r"Item\s*1\.02", "1.02 - Termination of Material Agreement"),
        (r"Item\s*2\.01", "2.01 - Completion of Acquisition/Disposition"),
        (r"Item\s*2\.02", "2.02 - Results of Operations"),
        (r"Item\s*2\.05", "2.05 - Costs for Exit Activities"),
        (r"Item\s*2\.06", "2.06 - Material Impairments"),
        (r"Item\s*3\.01", "3.01 - Notice of Delisting"),
        (r"Item\s*4\.01", "4.01 - Changes in Registrant's Certifying Accountant"),
        (r"Item\s*4\.02", "4.02 - Non-Reliance on Financial Statements"),
        (r"Item\s*5\.01", "5.01 - Changes in Control"),
        (r"Item\s*5\.02", "5.02 - Departure/Appointment of Directors or Officers"),
        (r"Item\s*5\.03", "5.03 - Amendments to Articles"),
        (r"Item\s*7\.01", "7.01 - Regulation FD Disclosure"),
        (r"Item\s*8\.01", "8.01 - Other Events"),
    ]

    def __init__(self, settings: Optional[Settings] = None):
        """
        Initialize SEC Collector.

        Args:
            settings: Application settings (uses global settings if not provided)
        """
        self._settings = settings or get_settings()
        self._cik_cache: dict[str, str] = {}
        self._last_request_time: float = 0
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create reusable HTTP client"""
        if self._client is None:
            self._client = httpx.AsyncClient(
                headers=self._headers,
                timeout=self._settings.sec.timeout,
                follow_redirects=True,
            )
        return self._client

    async def close(self) -> None:
        """Close HTTP client and release resources"""
        if self._client:
            await self._client.aclose()
            self._client = None

    @property
    def _headers(self) -> dict[str, str]:
        return {
            "User-Agent": self._settings.sec.user_agent,
            "Accept": "application/json, text/html, application/xml",
        }

    async def _rate_limit(self) -> None:
        """Enforce SEC rate limiting"""
        now = asyncio.get_event_loop().time()
        elapsed = now - self._last_request_time
        delay = self._settings.sec.request_delay

        if elapsed < delay:
            await asyncio.sleep(delay - elapsed)

        self._last_request_time = asyncio.get_event_loop().time()

    async def health_check(self) -> bool:
        """Check if SEC EDGAR is accessible"""
        try:
            await self._rate_limit()
            client = await self._get_client()
            response = await client.get(self._settings.sec.base_url)
            return response.status_code == 200
        except Exception as e:
            logger.warning(f"SEC health check failed: {e}")
            return False

    async def collect(self, ticker: str, lookback_days: int = 30) -> SECFilingData:
        """
        Collect SEC filings for a ticker.

        Args:
            ticker: Stock ticker symbol (e.g., "AAPL")
            lookback_days: Number of days to look back for filings

        Returns:
            SECFilingData containing collected filings

        Raises:
            TickerNotFoundError: If ticker CIK cannot be resolved
            CollectorError: If collection fails
        """
        ticker = ticker.upper().strip()
        collected_at = datetime.now(timezone.utc)

        try:
            cik = await self._get_cik(ticker)
            if not cik:
                return self._empty_result(ticker, collected_at, lookback_days, "CIK not found")

            # Fetch both filing types concurrently
            filings_8k, filings_form4 = await asyncio.gather(
                self._fetch_8k_filings(cik, ticker, lookback_days),
                self._fetch_form4_filings(cik, ticker, lookback_days),
                return_exceptions=True,
            )

            # Handle exceptions from gather
            if isinstance(filings_8k, Exception):
                filings_8k = []
            if isinstance(filings_form4, Exception):
                filings_form4 = []

            return SECFilingData(
                ticker=ticker,
                cik=cik,
                filings_8k=tuple(filings_8k),
                filings_form4=tuple(filings_form4),
                collected_at=collected_at,
                lookback_days=lookback_days,
                error=None,
            )

        except TickerNotFoundError:
            raise
        except Exception as e:
            return self._empty_result(ticker, collected_at, lookback_days, str(e))

    def _empty_result(
        self,
        ticker: str,
        collected_at: datetime,
        lookback_days: int,
        error: Optional[str] = None
    ) -> SECFilingData:
        """Create empty result structure"""
        return SECFilingData(
            ticker=ticker,
            cik=None,
            filings_8k=tuple(),
            filings_form4=tuple(),
            collected_at=collected_at,
            lookback_days=lookback_days,
            error=error,
        )

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((httpx.HTTPError, SECRateLimitError)),
        reraise=True,
    )
    async def _get_cik(self, ticker: str) -> Optional[str]:
        """Get CIK (Central Index Key) for a ticker"""
        if ticker in self._cik_cache:
            return self._cik_cache[ticker]

        await self._rate_limit()
        client = await self._get_client()

        try:
            response = await client.get(self._settings.sec.company_tickers_url)

            if response.status_code == 429:
                raise SECRateLimitError()

            response.raise_for_status()
            data = response.json()

            # Build lookup from ticker to CIK
            for entry in data.values():
                t = entry.get("ticker", "").upper()
                cik = str(entry.get("cik_str", "")).zfill(10)
                self._cik_cache[t] = cik

            return self._cik_cache.get(ticker)

        except httpx.HTTPStatusError as e:
            raise SECFetchError(
                url=self._settings.sec.company_tickers_url,
                status_code=e.response.status_code,
            )
        except Exception as e:
            logger.warning(f"Failed to get CIK for {ticker}: {e}")
            return None

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((httpx.HTTPError, SECRateLimitError)),
        reraise=True,
    )
    async def _fetch_8k_filings(
        self,
        cik: str,
        ticker: str,
        lookback_days: int
    ) -> list[Filing8K]:
        """Fetch 8-K filings from EDGAR"""
        filings = []
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=lookback_days)

        await self._rate_limit()
        client = await self._get_client()

        filings_url = (
            f"{self._settings.sec.base_url}/cgi-bin/browse-edgar"
            f"?action=getcompany&CIK={cik}&type=8-K&dateb=&owner=include&count=40&output=atom"
        )

        try:
            response = await client.get(filings_url)
            response.raise_for_status()

            root = ElementTree.fromstring(response.content)
            ns = {"atom": "http://www.w3.org/2005/Atom"}

            for entry in root.findall("atom:entry", ns):
                filing = await self._parse_8k_entry(entry, ns, cutoff_date)
                if filing:
                    filings.append(filing)

        except Exception as e:
            logger.warning(f"Failed to fetch 8-K filings for {ticker} (CIK: {cik}): {e}")

        return filings

    async def _parse_8k_entry(
        self,
        entry: ElementTree.Element,
        ns: dict,
        cutoff_date: datetime
    ) -> Optional[Filing8K]:
        """Parse a single 8-K entry from Atom feed"""
        title_elem = entry.find("atom:title", ns)
        link_elem = entry.find("atom:link", ns)

        # Prefer filing-date over updated for more accurate lookback
        date_elem = entry.find("atom:filing-date", ns)
        if date_elem is None or date_elem.text is None:
            date_elem = entry.find("atom:updated", ns)

        if date_elem is None or date_elem.text is None:
            return None

        filing_date = datetime.fromisoformat(
            date_elem.text.replace("Z", "+00:00")
        )

        if filing_date.replace(tzinfo=None) < cutoff_date.replace(tzinfo=None):
            return None

        filing_url = link_elem.get("href") if link_elem is not None else None

        content_data = {"snippet": None, "items": []}
        if filing_url:
            content_data = await self._fetch_8k_content(filing_url)

        return Filing8K(
            date=filing_date.strftime("%Y-%m-%d"),
            form_type="8-K",
            title=title_elem.text if title_elem is not None else "8-K Filing",
            url=filing_url,
            content_snippet=content_data.get("snippet"),
            items=tuple(content_data.get("items", [])),
        )

    async def _fetch_8k_content(self, filing_url: str) -> dict:
        """Fetch and parse 8-K filing content"""
        await self._rate_limit()
        client = await self._get_client()

        result = {"snippet": None, "items": []}

        try:
            response = await client.get(filing_url)
            response.raise_for_status()

            soup = BeautifulSoup(response.text, "lxml")
            main_doc = self._find_main_document(soup, filing_url)

            if main_doc:
                await self._rate_limit()
                doc_response = await client.get(main_doc)
                doc_response.raise_for_status()

                doc_soup = BeautifulSoup(doc_response.text, "lxml")
                text = doc_soup.get_text(separator=" ", strip=True)

                result["snippet"] = text[:2000]
                result["items"] = self._extract_8k_items(text)

        except Exception as e:
            logger.warning(f"Failed to fetch 8-K content from {filing_url}: {e}")

        return result

    def _find_main_document(self, soup: BeautifulSoup, filing_url: str) -> Optional[str]:
        """Find the main document link in filing index"""
        # Common 8-K document naming patterns
        patterns = ["8-k", "8k", "d8k", "form8k"]
        extensions = [".htm", ".html", ".txt"]

        # Try direct links - check both href and link text
        for link in soup.find_all("a", href=True):
            href = link.get("href", "").lower()
            text = link.get_text().lower()

            # Check if href or text contains 8-K pattern
            if any(p in href or p in text for p in patterns):
                if any(ext in href for ext in extensions):
                    return self._build_full_url(link.get("href"), filing_url)

        # Try table-based filing index
        table = soup.find("table", class_="tableFile")
        if table:
            for row in table.find_all("tr")[1:]:
                cells = row.find_all("td")
                if len(cells) >= 4:
                    doc_type = cells[3].get_text().strip().upper()
                    if any(p.upper() in doc_type for p in patterns):
                        link = cells[2].find("a")
                        if link:
                            return self._build_full_url(link.get("href"), filing_url)

        return None

    def _build_full_url(self, href: str, base_url: str) -> str:
        """Build full URL from relative or absolute href"""
        if href.startswith("http"):
            return href
        if href.startswith("/"):
            # Absolute path - use base domain only
            from urllib.parse import urlparse
            parsed = urlparse(base_url)
            return f"{parsed.scheme}://{parsed.netloc}{href}"
        # Relative path - append to base directory
        base_path = base_url.rsplit("/", 1)[0]
        return f"{base_path}/{href}"

    def _extract_8k_items(self, text: str) -> list[str]:
        """Extract 8-K item numbers from filing text"""
        found_items = []
        text_upper = text.upper()

        for pattern, item_name in self.ITEM_PATTERNS:
            if re.search(pattern, text_upper, re.IGNORECASE):
                found_items.append(item_name)

        return found_items

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((httpx.HTTPError, SECRateLimitError)),
        reraise=True,
    )
    async def _fetch_form4_filings(
        self,
        cik: str,
        ticker: str,
        lookback_days: int
    ) -> list[InsiderTransaction]:
        """Fetch Form 4 insider transaction filings"""
        transactions = []
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=lookback_days)

        await self._rate_limit()
        client = await self._get_client()

        filings_url = (
            f"{self._settings.sec.base_url}/cgi-bin/browse-edgar"
            f"?action=getcompany&CIK={cik}&type=4&dateb=&owner=only&count=40&output=atom"
        )

        try:
            response = await client.get(filings_url)
            response.raise_for_status()

            root = ElementTree.fromstring(response.content)
            ns = {"atom": "http://www.w3.org/2005/Atom"}

            for entry in root.findall("atom:entry", ns):
                txns = await self._parse_form4_entry(entry, ns, cutoff_date)
                transactions.extend(txns)

        except Exception as e:
            logger.warning(f"Failed to fetch Form 4 filings for {ticker} (CIK: {cik}): {e}")

        return transactions

    async def _parse_form4_entry(
        self,
        entry: ElementTree.Element,
        ns: dict,
        cutoff_date: datetime
    ) -> list[InsiderTransaction]:
        """Parse Form 4 entry and fetch transaction details"""
        link_elem = entry.find("atom:link", ns)

        # Prefer filing-date over updated for more accurate lookback
        date_elem = entry.find("atom:filing-date", ns)
        if date_elem is None or date_elem.text is None:
            date_elem = entry.find("atom:updated", ns)

        if date_elem is None or date_elem.text is None:
            return []

        filing_date = datetime.fromisoformat(
            date_elem.text.replace("Z", "+00:00")
        )

        if filing_date.replace(tzinfo=None) < cutoff_date.replace(tzinfo=None):
            return []

        filing_url = link_elem.get("href") if link_elem is not None else None

        if filing_url:
            return await self._parse_form4_details(filing_url, filing_date)

        return []

    async def _parse_form4_details(
        self,
        filing_url: str,
        filing_date: datetime
    ) -> list[InsiderTransaction]:
        """Parse Form 4 XML to extract transaction details"""
        await self._rate_limit()
        client = await self._get_client()

        transactions = []

        try:
            response = await client.get(filing_url)
            response.raise_for_status()

            soup = BeautifulSoup(response.text, "lxml")
            xml_link = self._find_form4_xml(soup, filing_url)

            if xml_link:
                await self._rate_limit()
                xml_response = await client.get(xml_link)
                xml_response.raise_for_status()

                root = ElementTree.fromstring(xml_response.content)
                transactions = self._extract_transactions(root, filing_date, filing_url)

        except Exception as e:
            logger.warning(f"Failed to parse Form 4 details from {filing_url}: {e}")

        return transactions

    def _find_form4_xml(self, soup: BeautifulSoup, filing_url: str) -> Optional[str]:
        """Find Form 4 XML file in filing index"""
        for link in soup.find_all("a", href=True):
            href = link.get("href", "")
            # Skip XSLT-transformed files (they return HTML, not XML)
            if "xsl" in href.lower():
                continue
            # Look for raw XML files (typically named like wk-form4_*.xml or form4.xml)
            if href.endswith(".xml"):
                return self._build_full_url(href, filing_url)
        return None

    def _extract_transactions(
        self,
        root: ElementTree.Element,
        filing_date: datetime,
        filing_url: str
    ) -> list[InsiderTransaction]:
        """Extract transactions from Form 4 XML"""
        transactions = []

        owner_name = self._get_xml_text(root, ".//rptOwnerName")
        owner_title = self._get_xml_text(root, ".//officerTitle")
        is_director = self._get_xml_text(root, ".//isDirector") == "1"
        is_officer = self._get_xml_text(root, ".//isOfficer") == "1"

        for txn in root.findall(".//nonDerivativeTransaction"):
            trans_code = self._get_xml_text(txn, ".//transactionCode")
            shares = self._get_xml_float(txn, ".//transactionShares/value")
            price = self._get_xml_float(txn, ".//transactionPricePerShare/value")

            if shares and trans_code:
                total_value = int(shares * price) if price else None

                transactions.append(InsiderTransaction(
                    date=filing_date.strftime("%Y-%m-%d"),
                    insider_name=owner_name or "Unknown",
                    insider_title=owner_title or ("Director" if is_director else ""),
                    is_director=is_director,
                    is_officer=is_officer,
                    transaction_type=trans_code,
                    shares=int(shares),
                    price=price,
                    total_value=total_value,
                    url=filing_url,
                ))

        return transactions

    @staticmethod
    def _get_xml_text(element: ElementTree.Element, xpath: str) -> Optional[str]:
        """Safely get text from XML element"""
        found = element.find(xpath)
        return found.text.strip() if found is not None and found.text else None

    @staticmethod
    def _get_xml_float(element: ElementTree.Element, xpath: str) -> Optional[float]:
        """Safely get float from XML element"""
        text = SECCollector._get_xml_text(element, xpath)
        if text:
            try:
                return float(text)
            except ValueError:
                pass
        return None

    # -------------------------------------------------------------------------
    # Incremental Scanning Support
    # -------------------------------------------------------------------------

    async def has_new_filings_8k(self, ticker: str, since_date: str) -> bool:
        """
        Quick check if any 8-K filings exist after since_date.

        Only fetches Atom feed dates, no content parsing.

        Args:
            ticker: Stock ticker symbol
            since_date: Date string in YYYY-MM-DD format

        Returns:
            True if new filings exist after since_date
        """
        ticker = ticker.upper().strip()
        cik = await self._get_cik(ticker)
        if not cik:
            return False

        since_dt = datetime.strptime(since_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)

        await self._rate_limit()
        client = await self._get_client()

        filings_url = (
            f"{self._settings.sec.base_url}/cgi-bin/browse-edgar"
            f"?action=getcompany&CIK={cik}&type=8-K&dateb=&owner=include&count=10&output=atom"
        )

        try:
            response = await client.get(filings_url)
            response.raise_for_status()

            root = ElementTree.fromstring(response.content)
            ns = {"atom": "http://www.w3.org/2005/Atom"}

            for entry in root.findall("atom:entry", ns):
                filing_date = self._get_entry_date(entry, ns)
                if filing_date and filing_date > since_dt:
                    return True

        except Exception as e:
            logger.warning(f"Failed to check 8-K filings for {ticker}: {e}")

        return False

    async def has_new_filings_form4(self, ticker: str, since_date: str) -> bool:
        """
        Quick check if any Form 4 filings exist after since_date.

        Only fetches Atom feed dates, no content parsing.

        Args:
            ticker: Stock ticker symbol
            since_date: Date string in YYYY-MM-DD format

        Returns:
            True if new filings exist after since_date
        """
        ticker = ticker.upper().strip()
        cik = await self._get_cik(ticker)
        if not cik:
            return False

        since_dt = datetime.strptime(since_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)

        await self._rate_limit()
        client = await self._get_client()

        filings_url = (
            f"{self._settings.sec.base_url}/cgi-bin/browse-edgar"
            f"?action=getcompany&CIK={cik}&type=4&dateb=&owner=only&count=10&output=atom"
        )

        try:
            response = await client.get(filings_url)
            response.raise_for_status()

            root = ElementTree.fromstring(response.content)
            ns = {"atom": "http://www.w3.org/2005/Atom"}

            for entry in root.findall("atom:entry", ns):
                filing_date = self._get_entry_date(entry, ns)
                if filing_date and filing_date > since_dt:
                    return True

        except Exception as e:
            logger.warning(f"Failed to check Form 4 filings for {ticker}: {e}")

        return False

    async def get_latest_filing_dates(
        self, ticker: str
    ) -> tuple[Optional[str], Optional[str]]:
        """
        Get most recent 8-K and Form 4 filing dates for a ticker.

        Args:
            ticker: Stock ticker symbol

        Returns:
            Tuple of (latest_8k_date, latest_form4_date) in YYYY-MM-DD format.
            Either may be None if no filings found.
        """
        ticker = ticker.upper().strip()
        cik = await self._get_cik(ticker)
        if not cik:
            return None, None

        # Fetch both feeds concurrently
        latest_8k, latest_form4 = await asyncio.gather(
            self._get_latest_filing_date(cik, "8-K"),
            self._get_latest_filing_date(cik, "4"),
            return_exceptions=True,
        )

        # Handle exceptions
        if isinstance(latest_8k, Exception):
            latest_8k = None
        if isinstance(latest_form4, Exception):
            latest_form4 = None

        return latest_8k, latest_form4

    async def _get_latest_filing_date(
        self, cik: str, form_type: str
    ) -> Optional[str]:
        """Get the most recent filing date for a form type"""
        await self._rate_limit()
        client = await self._get_client()

        owner_param = "only" if form_type == "4" else "include"
        filings_url = (
            f"{self._settings.sec.base_url}/cgi-bin/browse-edgar"
            f"?action=getcompany&CIK={cik}&type={form_type}&dateb=&owner={owner_param}&count=1&output=atom"
        )

        try:
            response = await client.get(filings_url)
            response.raise_for_status()

            root = ElementTree.fromstring(response.content)
            ns = {"atom": "http://www.w3.org/2005/Atom"}

            entry = root.find("atom:entry", ns)
            if entry is not None:
                filing_date = self._get_entry_date(entry, ns)
                if filing_date:
                    return filing_date.strftime("%Y-%m-%d")

        except Exception as e:
            logger.warning(f"Failed to get latest {form_type} date for CIK {cik}: {e}")

        return None

    def _get_entry_date(
        self, entry: ElementTree.Element, ns: dict
    ) -> Optional[datetime]:
        """Extract filing date from Atom entry"""
        # Prefer filing-date over updated
        date_elem = entry.find("atom:filing-date", ns)
        if date_elem is None or date_elem.text is None:
            date_elem = entry.find("atom:updated", ns)

        if date_elem is None or date_elem.text is None:
            return None

        try:
            date_text = date_elem.text.replace("Z", "+00:00")
            dt = datetime.fromisoformat(date_text)

            # Ensure timezone-aware (date-only strings are naive)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)

            return dt
        except ValueError:
            return None
