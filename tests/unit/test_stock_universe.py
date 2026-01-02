"""
Tests for Stock Universe Collector
"""

import pytest
import time
from unittest.mock import patch, AsyncMock, MagicMock


class TestStockUniverseCollector:
    """Tests for StockUniverseCollector"""

    @pytest.fixture
    def collector(self):
        """Create collector instance with mocked settings"""
        with patch("src.collectors.stock_universe.get_settings") as mock_settings:
            mock_settings.return_value.stock_universe.sp500_url = "https://example.com/sp500"
            mock_settings.return_value.stock_universe.nasdaq100_url = "https://example.com/nasdaq100"
            mock_settings.return_value.stock_universe.user_agent = "Test/1.0"
            mock_settings.return_value.stock_universe.request_delay = 0.01
            mock_settings.return_value.stock_universe.timeout = 30
            mock_settings.return_value.stock_universe.cache_ttl_hours = 24
            from src.collectors.stock_universe import StockUniverseCollector
            return StockUniverseCollector()

    def test_initializes_with_empty_cache(self, collector):
        """Collector starts with empty cache"""
        assert collector._cache == {}

    def test_initializes_without_client(self, collector):
        """Collector starts without HTTP client"""
        assert collector._client is None


class TestGetTickers:
    """Tests for get_tickers method"""

    @pytest.fixture
    def collector(self):
        """Create collector instance"""
        with patch("src.collectors.stock_universe.get_settings") as mock_settings:
            mock_settings.return_value.stock_universe.sp500_url = "https://example.com/sp500"
            mock_settings.return_value.stock_universe.nasdaq100_url = "https://example.com/nasdaq100"
            mock_settings.return_value.stock_universe.user_agent = "Test/1.0"
            mock_settings.return_value.stock_universe.request_delay = 0.01
            mock_settings.return_value.stock_universe.timeout = 30
            mock_settings.return_value.stock_universe.cache_ttl_hours = 24
            from src.collectors.stock_universe import StockUniverseCollector
            return StockUniverseCollector()

    @pytest.mark.asyncio
    async def test_custom_mode_returns_normalized_tickers(self, collector):
        """Custom mode returns uppercase normalized tickers"""
        result = await collector.get_tickers("custom", ["aapl", " MSFT ", "googl"])
        assert result == ["AAPL", "MSFT", "GOOGL"]

    @pytest.mark.asyncio
    async def test_custom_mode_requires_tickers(self, collector):
        """Custom mode raises error without tickers"""
        with pytest.raises(ValueError, match="Custom ticker list required"):
            await collector.get_tickers("custom", None)

    @pytest.mark.asyncio
    async def test_custom_mode_requires_non_empty_tickers(self, collector):
        """Custom mode raises error with empty list"""
        with pytest.raises(ValueError, match="Custom ticker list required"):
            await collector.get_tickers("custom", [])

    @pytest.mark.asyncio
    async def test_invalid_mode_raises_error(self, collector):
        """Invalid mode raises ValueError"""
        with pytest.raises(ValueError, match="Invalid scan mode"):
            await collector.get_tickers("invalid_mode", None)

    @pytest.mark.asyncio
    async def test_sp500_mode_calls_get_sp500(self, collector):
        """sp500 mode calls get_sp500 method"""
        collector.get_sp500 = AsyncMock(return_value=["AAPL", "MSFT"])
        result = await collector.get_tickers("sp500")
        collector.get_sp500.assert_called_once()
        assert result == ["AAPL", "MSFT"]

    @pytest.mark.asyncio
    async def test_nasdaq100_mode_calls_get_nasdaq100(self, collector):
        """nasdaq100 mode calls get_nasdaq100 method"""
        collector.get_nasdaq100 = AsyncMock(return_value=["AAPL", "NVDA"])
        result = await collector.get_tickers("nasdaq100")
        collector.get_nasdaq100.assert_called_once()
        assert result == ["AAPL", "NVDA"]


class TestCaching:
    """Tests for caching behavior"""

    @pytest.fixture
    def collector(self):
        """Create collector instance"""
        with patch("src.collectors.stock_universe.get_settings") as mock_settings:
            mock_settings.return_value.stock_universe.sp500_url = "https://example.com/sp500"
            mock_settings.return_value.stock_universe.nasdaq100_url = "https://example.com/nasdaq100"
            mock_settings.return_value.stock_universe.user_agent = "Test/1.0"
            mock_settings.return_value.stock_universe.request_delay = 0.01
            mock_settings.return_value.stock_universe.timeout = 30
            mock_settings.return_value.stock_universe.cache_ttl_hours = 24
            from src.collectors.stock_universe import StockUniverseCollector
            return StockUniverseCollector()

    def test_cache_set_and_get(self, collector):
        """Cache set and get work correctly"""
        tickers = ["AAPL", "MSFT"]
        collector._set_cache("test_key", tickers)

        result = collector._get_from_cache("test_key")
        assert result == tickers

    def test_cache_returns_none_for_missing_key(self, collector):
        """Cache returns None for non-existent key"""
        result = collector._get_from_cache("missing_key")
        assert result is None

    def test_cache_expires_after_ttl(self, collector):
        """Cache entries expire after TTL"""
        # Manually set cache with old timestamp
        old_timestamp = time.time() - (25 * 60 * 60)  # 25 hours ago
        collector._cache["expired_key"] = (["AAPL"], old_timestamp)

        result = collector._get_from_cache("expired_key")
        assert result is None
        assert "expired_key" not in collector._cache

    def test_cache_valid_within_ttl(self, collector):
        """Cache entries valid within TTL"""
        # Set cache with recent timestamp
        collector._set_cache("valid_key", ["AAPL", "MSFT"])

        result = collector._get_from_cache("valid_key")
        assert result == ["AAPL", "MSFT"]


class TestParseSP500Table:
    """Tests for S&P 500 table parsing"""

    @pytest.fixture
    def collector(self):
        """Create collector instance"""
        with patch("src.collectors.stock_universe.get_settings") as mock_settings:
            mock_settings.return_value.stock_universe.sp500_url = "https://example.com/sp500"
            mock_settings.return_value.stock_universe.nasdaq100_url = "https://example.com/nasdaq100"
            mock_settings.return_value.stock_universe.user_agent = "Test/1.0"
            mock_settings.return_value.stock_universe.request_delay = 0.01
            mock_settings.return_value.stock_universe.timeout = 30
            mock_settings.return_value.stock_universe.cache_ttl_hours = 24
            from src.collectors.stock_universe import StockUniverseCollector
            return StockUniverseCollector()

    def test_parses_symbol_column(self, collector):
        """Parses tickers from Symbol column"""
        html = '''
        <html>
            <table class="wikitable">
                <tr><th>Symbol</th><th>Company</th></tr>
                <tr><td>AAPL</td><td>Apple Inc</td></tr>
                <tr><td>MSFT</td><td>Microsoft</td></tr>
            </table>
        </html>
        '''
        result = collector._parse_sp500_table(html)
        assert result == ["AAPL", "MSFT"]

    def test_removes_footnotes(self, collector):
        """Removes Wikipedia footnote markers"""
        html = '''
        <html>
            <table class="wikitable">
                <tr><th>Symbol</th><th>Company</th></tr>
                <tr><td>AAPL[1]</td><td>Apple Inc</td></tr>
                <tr><td>GOOGL[note 2]</td><td>Alphabet</td></tr>
            </table>
        </html>
        '''
        result = collector._parse_sp500_table(html)
        assert result == ["AAPL", "GOOGL"]

    def test_handles_missing_symbol_column(self, collector):
        """Returns empty list when Symbol column not found"""
        html = '''
        <html>
            <table class="wikitable">
                <tr><th>Company</th><th>Industry</th></tr>
                <tr><td>Apple Inc</td><td>Technology</td></tr>
            </table>
        </html>
        '''
        result = collector._parse_sp500_table(html)
        assert result == []

    def test_uppercase_normalization(self, collector):
        """Normalizes tickers to uppercase"""
        html = '''
        <html>
            <table class="wikitable">
                <tr><th>Symbol</th><th>Company</th></tr>
                <tr><td>aapl</td><td>Apple Inc</td></tr>
            </table>
        </html>
        '''
        result = collector._parse_sp500_table(html)
        assert result == ["AAPL"]


class TestParseNasdaq100Table:
    """Tests for NASDAQ 100 table parsing"""

    @pytest.fixture
    def collector(self):
        """Create collector instance"""
        with patch("src.collectors.stock_universe.get_settings") as mock_settings:
            mock_settings.return_value.stock_universe.sp500_url = "https://example.com/sp500"
            mock_settings.return_value.stock_universe.nasdaq100_url = "https://example.com/nasdaq100"
            mock_settings.return_value.stock_universe.user_agent = "Test/1.0"
            mock_settings.return_value.stock_universe.request_delay = 0.01
            mock_settings.return_value.stock_universe.timeout = 30
            mock_settings.return_value.stock_universe.cache_ttl_hours = 24
            from src.collectors.stock_universe import StockUniverseCollector
            return StockUniverseCollector()

    def test_parses_ticker_column(self, collector):
        """Parses tickers from Ticker column"""
        html = '''
        <html>
            <table class="wikitable">
                <tr><th>Ticker</th><th>Company</th></tr>
                <tr><td>AAPL</td><td>Apple Inc</td></tr>
                <tr><td>NVDA</td><td>NVIDIA</td></tr>
            </table>
        </html>
        '''
        result = collector._parse_nasdaq100_table(html)
        assert result == ["AAPL", "NVDA"]

    def test_handles_tickers_with_dots(self, collector):
        """Handles tickers with dots like BRK.B"""
        html = '''
        <html>
            <table class="wikitable">
                <tr><th>Ticker</th><th>Company</th></tr>
                <tr><td>BRK.B</td><td>Berkshire</td></tr>
            </table>
        </html>
        '''
        result = collector._parse_nasdaq100_table(html)
        assert result == ["BRK.B"]


class TestFallbackBehavior:
    """Tests for fallback to hardcoded list"""

    @pytest.fixture
    def collector(self):
        """Create collector instance"""
        with patch("src.collectors.stock_universe.get_settings") as mock_settings:
            mock_settings.return_value.stock_universe.sp500_url = "https://example.com/sp500"
            mock_settings.return_value.stock_universe.nasdaq100_url = "https://example.com/nasdaq100"
            mock_settings.return_value.stock_universe.user_agent = "Test/1.0"
            mock_settings.return_value.stock_universe.request_delay = 0.01
            mock_settings.return_value.stock_universe.timeout = 30
            mock_settings.return_value.stock_universe.cache_ttl_hours = 24
            from src.collectors.stock_universe import StockUniverseCollector
            return StockUniverseCollector()

    @pytest.mark.asyncio
    async def test_fallback_on_http_error(self, collector):
        """Falls back to hardcoded list on HTTP error"""
        import httpx

        mock_client = AsyncMock()
        mock_client.get.side_effect = httpx.HTTPError("Connection failed")
        collector._get_client = AsyncMock(return_value=mock_client)

        result = await collector.get_sp500()

        # Should return fallback list
        from src.collectors.stock_universe import FALLBACK_TOP_100
        assert result == FALLBACK_TOP_100

    @pytest.mark.asyncio
    async def test_fallback_on_parse_failure(self, collector):
        """Falls back when parsing returns empty list"""
        mock_response = MagicMock()
        mock_response.text = "<html><body>No table here</body></html>"
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response
        collector._get_client = AsyncMock(return_value=mock_client)

        result = await collector.get_sp500()

        # Should return fallback list
        from src.collectors.stock_universe import FALLBACK_TOP_100
        assert result == FALLBACK_TOP_100


class TestResourceCleanup:
    """Tests for resource cleanup"""

    @pytest.fixture
    def collector(self):
        """Create collector instance"""
        with patch("src.collectors.stock_universe.get_settings") as mock_settings:
            mock_settings.return_value.stock_universe.sp500_url = "https://example.com/sp500"
            mock_settings.return_value.stock_universe.nasdaq100_url = "https://example.com/nasdaq100"
            mock_settings.return_value.stock_universe.user_agent = "Test/1.0"
            mock_settings.return_value.stock_universe.request_delay = 0.01
            mock_settings.return_value.stock_universe.timeout = 30
            mock_settings.return_value.stock_universe.cache_ttl_hours = 24
            from src.collectors.stock_universe import StockUniverseCollector
            return StockUniverseCollector()

    @pytest.mark.asyncio
    async def test_close_with_no_client(self, collector):
        """Close works when client was never created"""
        await collector.close()
        assert collector._client is None

    @pytest.mark.asyncio
    async def test_close_closes_client(self, collector):
        """Close properly closes HTTP client"""
        mock_client = AsyncMock()
        collector._client = mock_client

        await collector.close()

        mock_client.aclose.assert_called_once()
        assert collector._client is None
