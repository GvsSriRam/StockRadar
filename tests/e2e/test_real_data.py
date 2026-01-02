"""
End-to-end tests with real SEC data.

These tests are marked as 'slow' and 'integration' so they can be skipped in CI.
They make real HTTP requests to SEC EDGAR.

Run with: pytest -m e2e tests/e2e/
Skip with: pytest -m "not e2e"
"""

import pytest
import os
import time
from datetime import datetime

# Skip all tests in this module if GROQ_API_KEY is not set
pytestmark = [
    pytest.mark.e2e,
    pytest.mark.slow,
    pytest.mark.skipif(
        not os.getenv("GROQ_API_KEY"),
        reason="GROQ_API_KEY environment variable not set"
    ),
]


class TestRealSECData:
    """E2E tests with real SEC EDGAR data"""

    @pytest.fixture
    def test_tickers(self):
        """Well-known tickers for testing"""
        return ["AAPL", "MSFT", "GOOGL"]

    @pytest.mark.asyncio
    async def test_sec_collector_real_data(self, test_tickers):
        """Test SEC collector with real EDGAR data"""
        from src.collectors.sec_collector import SECCollector

        collector = SECCollector()

        try:
            for ticker in test_tickers[:1]:  # Just test one to be fast
                data = await collector.collect(ticker, lookback_days=7)

                # Verify response structure
                assert data is not None
                assert data.ticker == ticker
                assert data.cik is not None
                assert isinstance(data.filings_8k, tuple)
                assert isinstance(data.filings_form4, tuple)
                assert data.collected_at is not None
                assert data.error is None

                # Add small delay to respect rate limits
                await collector._rate_limit()
        finally:
            await collector.close()

    @pytest.mark.asyncio
    async def test_full_pipeline_real_data(self, test_tickers):
        """Test full pipeline with real data (single ticker)"""
        from src.services.risk_scanner import RiskScannerBuilder
        from src.core.models import RiskLevel

        # Build the scanner
        builder = RiskScannerBuilder()
        service = builder.build()

        try:
            # Scan single ticker
            result = await service.scan_ticker(test_tickers[0], lookback_days=7)

            # Verify result structure
            assert result is not None
            assert result.success is True
            assert result.ticker == test_tickers[0]

            report = result.report
            assert report is not None
            assert 0 <= report.risk_score <= 100
            assert report.risk_level in RiskLevel
            assert report.analyzed_at is not None
            assert isinstance(report.evidence_links, tuple)
        finally:
            await service._collector.close()

    @pytest.mark.asyncio
    async def test_output_schema_validation(self):
        """Test that output matches expected schema"""
        from src.services.risk_scanner import RiskScannerBuilder
        from src.formatters.json_formatter import JsonFormatter

        builder = RiskScannerBuilder()
        service = builder.build()
        formatter = JsonFormatter()

        try:
            result = await service.scan_ticker("AAPL", lookback_days=7)
            assert result.success is True
            output = formatter.to_dict(result.report)

            # Validate required fields
            required_fields = [
                "ticker",
                "risk_score",
                "risk_level",
                "red_flags",
                "insider_summary",
                "evidence_links",
                "analyzed_at",
            ]

            for field in required_fields:
                assert field in output, f"Missing required field: {field}"

            # Validate types
            assert isinstance(output["ticker"], str)
            assert isinstance(output["risk_score"], int)
            assert isinstance(output["risk_level"], str)
            assert isinstance(output["red_flags"], list)
            assert isinstance(output["evidence_links"], list)
        finally:
            await service._collector.close()


class TestPerformanceTargets:
    """Test performance against documented targets"""

    @pytest.mark.asyncio
    async def test_single_ticker_performance(self):
        """Test that single ticker scan completes within target time"""
        from src.services.risk_scanner import RiskScannerBuilder

        builder = RiskScannerBuilder()
        service = builder.build()

        try:
            start_time = time.time()
            result = await service.scan_ticker("AAPL", lookback_days=7)
            elapsed = time.time() - start_time

            # Target: Should complete within 60 seconds for single ticker
            assert elapsed < 60, f"Single ticker scan took {elapsed:.1f}s (target: <60s)"
            assert result is not None
            assert result.success is True
        finally:
            await service._collector.close()

    @pytest.mark.asyncio
    @pytest.mark.skip(reason="Requires multiple API calls, run manually")
    async def test_batch_ticker_performance(self):
        """Test that batch scan of 10 tickers completes within 3 minutes"""
        from src.services.risk_scanner import RiskScannerBuilder

        tickers = ["AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "TSLA", "JPM", "V", "JNJ"]
        builder = RiskScannerBuilder()
        service = builder.build()

        try:
            start_time = time.time()
            results = await service.scan_multiple(tickers, lookback_days=7)
            elapsed = time.time() - start_time

            # Target: ~3 minutes for 10 tickers
            assert elapsed < 180, f"Batch scan took {elapsed:.1f}s (target: <180s)"
            assert len(results) == len(tickers)
        finally:
            await service._collector.close()


class TestErrorHandling:
    """E2E tests for error handling"""

    @pytest.mark.asyncio
    async def test_invalid_ticker_handling(self):
        """Test handling of invalid ticker symbols"""
        from src.collectors.sec_collector import SECCollector

        collector = SECCollector()

        try:
            # Invalid ticker should return error or empty data
            data = await collector.collect("INVALID123XYZ", lookback_days=7)

            # Either no CIK found or error returned
            assert data.cik is None or data.error is not None
        finally:
            await collector.close()

    @pytest.mark.asyncio
    async def test_empty_filings_handling(self):
        """Test handling when no filings are found in lookback period"""
        from src.services.risk_scanner import RiskScannerBuilder
        from src.core.models import RiskLevel

        builder = RiskScannerBuilder()
        service = builder.build()

        try:
            # Use very short lookback to get empty results
            result = await service.scan_ticker("AAPL", lookback_days=1)

            # Should still return valid result
            assert result is not None
            assert result.success is True
            report = result.report
            assert 0 <= report.risk_score <= 100
            assert report.risk_level in RiskLevel
        finally:
            await service._collector.close()


class TestRetryBehavior:
    """E2E tests for retry behavior (rate limiting)"""

    @pytest.mark.asyncio
    async def test_rate_limit_handling(self):
        """Test that rate limiting works correctly"""
        from src.collectors.sec_collector import SECCollector

        collector = SECCollector()

        try:
            # Make multiple requests - rate limiter should prevent 429 errors
            start_time = time.time()

            for i in range(3):
                await collector._rate_limit()

            elapsed = time.time() - start_time

            # Should have delays between requests
            # With 0.1s delay, 3 requests should take at least 0.2s
            assert elapsed >= 0.1, "Rate limiting not applied"
        finally:
            await collector.close()
