"""
Stock Universe Collector

Fetches S&P 500 and NASDAQ 100 ticker lists from Wikipedia.
Follows the same patterns as SECCollector for consistency.
"""

import asyncio
import logging
import time
from typing import Optional

import httpx
from bs4 import BeautifulSoup
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)

from ..config import Settings, get_settings

logger = logging.getLogger(__name__)


# Fallback ticker lists when Wikipedia is unavailable
FALLBACK_TOP_100 = [
    "AAPL", "MSFT", "AMZN", "NVDA", "GOOGL", "META", "TSLA", "BRK.B", "UNH", "XOM",
    "JNJ", "JPM", "V", "PG", "MA", "HD", "CVX", "MRK", "ABBV", "LLY",
    "PEP", "KO", "COST", "AVGO", "WMT", "MCD", "CSCO", "TMO", "ACN", "ABT",
    "DHR", "NEE", "ADBE", "CRM", "NFLX", "AMD", "TXN", "NKE", "PM", "WFC",
    "UPS", "RTX", "HON", "BMY", "QCOM", "ORCL", "LOW", "INTC", "AMGN", "UNP",
    "IBM", "CAT", "SPGI", "BA", "GE", "DE", "ELV", "LMT", "INTU", "AMAT",
    "AXP", "SBUX", "MDLZ", "MS", "GS", "GILD", "BLK", "ADI", "ISRG", "CVS",
    "PLD", "SYK", "REGN", "VRTX", "C", "NOW", "CI", "LRCX", "TMUS", "SCHW",
    "ZTS", "MMC", "MO", "CB", "CME", "EOG", "SLB", "PYPL", "DUK", "SO",
    "APD", "NOC", "ITW", "HUM", "MRNA", "SNPS", "CDNS", "CL", "FDX", "ATVI",
]


class StockUniverseCollector:
    """
    Fetches stock universe lists (S&P 500, NASDAQ 100) from Wikipedia.

    Features:
    - Rate limiting for Wikipedia requests
    - In-memory caching with TTL
    - Fallback to hardcoded list on failure
    - Async HTTP client (lazy-loaded)
    """

    def __init__(self, settings: Optional[Settings] = None):
        """
        Initialize Stock Universe Collector.

        Args:
            settings: Application settings (uses global settings if not provided)
        """
        self._settings = settings or get_settings()
        self._client: Optional[httpx.AsyncClient] = None
        self._last_request_time: float = 0
        self._cache: dict[str, tuple[list[str], float]] = {}

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create reusable HTTP client (lazy-load pattern from SECCollector)"""
        if self._client is None:
            self._client = httpx.AsyncClient(
                headers=self._headers,
                timeout=self._settings.stock_universe.timeout,
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
        """HTTP headers for Wikipedia requests"""
        return {
            "User-Agent": self._settings.stock_universe.user_agent,
            "Accept": "text/html,application/xhtml+xml",
        }

    async def _rate_limit(self) -> None:
        """Enforce rate limiting (same pattern as SECCollector)"""
        now = asyncio.get_event_loop().time()
        elapsed = now - self._last_request_time
        delay = self._settings.stock_universe.request_delay

        if elapsed < delay:
            await asyncio.sleep(delay - elapsed)

        self._last_request_time = asyncio.get_event_loop().time()

    def _get_from_cache(self, key: str) -> Optional[list[str]]:
        """Get cached ticker list if not expired"""
        if key in self._cache:
            tickers, timestamp = self._cache[key]
            ttl_seconds = self._settings.stock_universe.cache_ttl_hours * 3600
            if time.time() - timestamp < ttl_seconds:
                return tickers
            del self._cache[key]
        return None

    def _set_cache(self, key: str, tickers: list[str]) -> None:
        """Cache ticker list with current timestamp"""
        self._cache[key] = (tickers, time.time())

    async def get_tickers(self, mode: str, custom: Optional[list[str]] = None) -> list[str]:
        """
        Get ticker list based on scan mode.

        Args:
            mode: One of "custom", "sp500", "nasdaq100"
            custom: Custom ticker list (required if mode="custom")

        Returns:
            List of ticker symbols

        Raises:
            ValueError: If mode is invalid or custom list missing for custom mode
        """
        if mode == "custom":
            if not custom:
                raise ValueError("Custom ticker list required for 'custom' mode")
            return [t.upper().strip() for t in custom]

        if mode == "sp500":
            return await self.get_sp500()

        if mode == "nasdaq100":
            return await self.get_nasdaq100()

        raise ValueError(f"Invalid scan mode: {mode}. Must be 'custom', 'sp500', or 'nasdaq100'")

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type(httpx.HTTPError),
        reraise=True,
    )
    async def get_sp500(self) -> list[str]:
        """
        Fetch S&P 500 ticker list from Wikipedia.

        Returns:
            List of ~500 ticker symbols
        """
        cache_key = "sp500"
        cached = self._get_from_cache(cache_key)
        if cached:
            logger.info(f"Using cached S&P 500 list ({len(cached)} tickers)")
            return cached

        try:
            await self._rate_limit()
            client = await self._get_client()
            response = await client.get(self._settings.stock_universe.sp500_url)
            response.raise_for_status()

            tickers = self._parse_sp500_table(response.text)

            if tickers:
                self._set_cache(cache_key, tickers)
                logger.info(f"Fetched S&P 500 list: {len(tickers)} tickers")
                return tickers

        except Exception as e:
            logger.warning(f"Failed to fetch S&P 500 list: {e}")

        # Fallback to hardcoded list
        logger.info(f"Using fallback list ({len(FALLBACK_TOP_100)} tickers)")
        return FALLBACK_TOP_100.copy()

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type(httpx.HTTPError),
        reraise=True,
    )
    async def get_nasdaq100(self) -> list[str]:
        """
        Fetch NASDAQ 100 ticker list from Wikipedia.

        Returns:
            List of ~100 ticker symbols
        """
        cache_key = "nasdaq100"
        cached = self._get_from_cache(cache_key)
        if cached:
            logger.info(f"Using cached NASDAQ 100 list ({len(cached)} tickers)")
            return cached

        try:
            await self._rate_limit()
            client = await self._get_client()
            response = await client.get(self._settings.stock_universe.nasdaq100_url)
            response.raise_for_status()

            tickers = self._parse_nasdaq100_table(response.text)

            if tickers:
                self._set_cache(cache_key, tickers)
                logger.info(f"Fetched NASDAQ 100 list: {len(tickers)} tickers")
                return tickers

        except Exception as e:
            logger.warning(f"Failed to fetch NASDAQ 100 list: {e}")

        # Fallback to hardcoded list
        logger.info(f"Using fallback list ({len(FALLBACK_TOP_100)} tickers)")
        return FALLBACK_TOP_100.copy()

    def _parse_sp500_table(self, html: str) -> list[str]:
        """Parse S&P 500 tickers from Wikipedia table"""
        tickers = []
        soup = BeautifulSoup(html, "lxml")

        # Find the first table with "Symbol" header
        for table in soup.find_all("table", class_="wikitable"):
            headers = [th.get_text(strip=True).lower() for th in table.find_all("th")]

            # S&P 500 table has "Symbol" column
            if "symbol" in headers:
                symbol_idx = headers.index("symbol")
                for row in table.find_all("tr")[1:]:
                    cells = row.find_all(["td", "th"])
                    if len(cells) > symbol_idx:
                        ticker = cells[symbol_idx].get_text(strip=True)
                        # Clean up ticker (remove footnotes, etc.)
                        ticker = ticker.split("[")[0].strip()
                        if ticker and ticker.isalpha():
                            tickers.append(ticker.upper())
                break

        return tickers

    def _parse_nasdaq100_table(self, html: str) -> list[str]:
        """Parse NASDAQ 100 tickers from Wikipedia table"""
        tickers = []
        soup = BeautifulSoup(html, "lxml")

        # Find the table with "Ticker" header
        for table in soup.find_all("table", class_="wikitable"):
            headers = [th.get_text(strip=True).lower() for th in table.find_all("th")]

            # NASDAQ 100 table has "Ticker" column
            if "ticker" in headers:
                ticker_idx = headers.index("ticker")
                for row in table.find_all("tr")[1:]:
                    cells = row.find_all(["td", "th"])
                    if len(cells) > ticker_idx:
                        ticker = cells[ticker_idx].get_text(strip=True)
                        # Clean up ticker (remove footnotes, etc.)
                        ticker = ticker.split("[")[0].strip()
                        if ticker and ticker.replace(".", "").isalpha():
                            tickers.append(ticker.upper())
                break

        return tickers