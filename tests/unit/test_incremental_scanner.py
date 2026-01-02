"""
Tests for Incremental Scanner Service
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone, timedelta

from src.services.incremental_scanner import IncrementalScanner
from src.services.risk_scanner import ScanResult
from src.storage.scan_state import TickerScanState, ScanStats
from src.core.models import RiskReport, RiskLevel


class TestIncrementalScanner:
    """Tests for IncrementalScanner"""

    @pytest.fixture
    def mock_scanner(self):
        """Create mock RiskScannerService"""
        scanner = AsyncMock()
        scanner.scan_ticker = AsyncMock()
        return scanner

    @pytest.fixture
    def mock_collector(self):
        """Create mock SECCollector"""
        collector = AsyncMock()
        collector.has_new_filings_8k = AsyncMock(return_value=False)
        collector.has_new_filings_form4 = AsyncMock(return_value=False)
        collector.get_latest_filing_dates = AsyncMock(return_value=(None, None))
        collector.close = AsyncMock()
        return collector

    @pytest.fixture
    def mock_state_store(self):
        """Create mock ScanStateStore"""
        store = MagicMock()
        store.load = AsyncMock(return_value={})
        store.save = AsyncMock()
        store.get_state = MagicMock(return_value=None)
        store.needs_rescan = MagicMock(return_value=(True, "never_scanned"))
        store.update_state = MagicMock()
        return store

    @pytest.fixture
    def incremental_scanner(self, mock_scanner, mock_collector, mock_state_store):
        """Create IncrementalScanner with mocked dependencies"""
        with patch("src.services.incremental_scanner.get_settings"):
            scanner = IncrementalScanner(
                scanner=mock_scanner,
                sec_collector=mock_collector,
                state_store=mock_state_store,
            )
            return scanner

    def _make_successful_result(self, ticker: str, score: int = 50) -> ScanResult:
        """Create a successful scan result"""
        report = MagicMock(spec=RiskReport)
        report.risk_score = score
        report.risk_level = RiskLevel.LOW
        return ScanResult(ticker=ticker, report=report, error=None, success=True)

    @pytest.mark.asyncio
    async def test_scan_incremental_first_run(
        self, incremental_scanner, mock_scanner, mock_state_store
    ):
        """First run scans all tickers (never scanned before)"""
        mock_scanner.scan_ticker.return_value = self._make_successful_result("AAPL")
        mock_state_store.needs_rescan.return_value = (True, "never_scanned")

        results, stats = await incremental_scanner.scan_incremental(
            ["AAPL", "MSFT"], lookback_days=30
        )

        assert len(results) == 2
        assert stats.scanned == 2
        assert stats.skipped == 0
        mock_scanner.scan_ticker.assert_called()

    @pytest.mark.asyncio
    async def test_scan_incremental_skips_unchanged(
        self, incremental_scanner, mock_scanner, mock_state_store, mock_collector
    ):
        """Skips tickers with no new filings"""
        # Setup: AAPL needs rescan, MSFT doesn't
        def needs_rescan_side_effect(ticker, lookback_days):
            if ticker == "AAPL":
                return (True, "never_scanned")
            return (False, "check_filings")

        mock_state_store.needs_rescan.side_effect = needs_rescan_side_effect

        # MSFT has recent state, no new filings
        recent_time = (datetime.now(timezone.utc) - timedelta(days=5)).isoformat()
        mock_state_store.get_state.return_value = TickerScanState(
            last_scan_time=recent_time,
            last_8k_date="2024-01-10",
            last_form4_date="2024-01-12",
            last_risk_score=50,
        )

        mock_scanner.scan_ticker.return_value = self._make_successful_result("AAPL")

        results, stats = await incremental_scanner.scan_incremental(
            ["AAPL", "MSFT"], lookback_days=30
        )

        assert stats.scanned == 1
        assert stats.skipped == 1
        assert "unchanged" in stats.reasons

    @pytest.mark.asyncio
    async def test_scan_incremental_rescans_on_new_8k(
        self, incremental_scanner, mock_scanner, mock_state_store, mock_collector
    ):
        """Rescans when new 8-K filings found"""
        mock_state_store.needs_rescan.return_value = (False, "check_filings")

        recent_time = (datetime.now(timezone.utc) - timedelta(days=5)).isoformat()
        mock_state_store.get_state.return_value = TickerScanState(
            last_scan_time=recent_time,
            last_8k_date="2024-01-10",
            last_form4_date="2024-01-12",
            last_risk_score=50,
        )

        # New 8-K filing found
        mock_collector.has_new_filings_8k.return_value = True

        mock_scanner.scan_ticker.return_value = self._make_successful_result("AAPL")

        results, stats = await incremental_scanner.scan_incremental(
            ["AAPL"], lookback_days=30
        )

        assert stats.scanned == 1
        assert stats.skipped == 0

    @pytest.mark.asyncio
    async def test_scan_incremental_rescans_on_new_form4(
        self, incremental_scanner, mock_scanner, mock_state_store, mock_collector
    ):
        """Rescans when new Form 4 filings found"""
        mock_state_store.needs_rescan.return_value = (False, "check_filings")

        recent_time = (datetime.now(timezone.utc) - timedelta(days=5)).isoformat()
        mock_state_store.get_state.return_value = TickerScanState(
            last_scan_time=recent_time,
            last_8k_date="2024-01-10",
            last_form4_date="2024-01-12",
            last_risk_score=50,
        )

        # New Form 4 filing found
        mock_collector.has_new_filings_8k.return_value = False
        mock_collector.has_new_filings_form4.return_value = True

        mock_scanner.scan_ticker.return_value = self._make_successful_result("AAPL")

        results, stats = await incremental_scanner.scan_incremental(
            ["AAPL"], lookback_days=30
        )

        assert stats.scanned == 1
        assert stats.skipped == 0

    @pytest.mark.asyncio
    async def test_scan_incremental_force_rescan(
        self, incremental_scanner, mock_scanner, mock_state_store
    ):
        """force_rescan bypasses incremental logic"""
        # Even though state says no rescan needed
        mock_state_store.needs_rescan.return_value = (False, "check_filings")

        mock_scanner.scan_ticker.return_value = self._make_successful_result("AAPL")

        results, stats = await incremental_scanner.scan_incremental(
            ["AAPL", "MSFT"], lookback_days=30, force_rescan=True
        )

        assert stats.scanned == 2
        assert stats.skipped == 0

    @pytest.mark.asyncio
    async def test_scan_incremental_updates_state_after_scan(
        self, incremental_scanner, mock_scanner, mock_state_store, mock_collector
    ):
        """Updates state after successful scan"""
        mock_scanner.scan_ticker.return_value = self._make_successful_result("AAPL", score=75)
        mock_collector.get_latest_filing_dates.return_value = ("2024-01-15", "2024-01-14")

        await incremental_scanner.scan_incremental(["AAPL"], lookback_days=30)

        # Verify state was updated
        mock_state_store.update_state.assert_called_once()
        call_args = mock_state_store.update_state.call_args
        assert call_args.kwargs["ticker"] == "AAPL"
        assert call_args.kwargs["risk_score"] == 75
        assert call_args.kwargs["last_8k_date"] == "2024-01-15"
        assert call_args.kwargs["last_form4_date"] == "2024-01-14"

    @pytest.mark.asyncio
    async def test_scan_incremental_saves_state_at_end(
        self, incremental_scanner, mock_scanner, mock_state_store
    ):
        """Saves state after all scans complete"""
        mock_scanner.scan_ticker.return_value = self._make_successful_result("AAPL")

        await incremental_scanner.scan_incremental(["AAPL", "MSFT"], lookback_days=30)

        mock_state_store.save.assert_called_once()

    @pytest.mark.asyncio
    async def test_scan_incremental_rescans_on_stale(
        self, incremental_scanner, mock_scanner, mock_state_store
    ):
        """Rescans stale tickers"""
        mock_state_store.needs_rescan.return_value = (True, "stale")

        mock_scanner.scan_ticker.return_value = self._make_successful_result("AAPL")

        results, stats = await incremental_scanner.scan_incremental(
            ["AAPL"], lookback_days=30
        )

        assert stats.scanned == 1
        assert stats.skipped == 0

    @pytest.mark.asyncio
    async def test_close_cleans_up_resources(
        self, incremental_scanner, mock_collector
    ):
        """Close cleans up SEC collector"""
        await incremental_scanner.close()

        mock_collector.close.assert_called_once()


class TestIncrementalScannerShouldScan:
    """Tests for _should_scan method"""

    @pytest.fixture
    def incremental_scanner(self):
        """Create IncrementalScanner with minimal mocks"""
        with patch("src.services.incremental_scanner.get_settings"):
            scanner = IncrementalScanner(
                scanner=AsyncMock(),
                sec_collector=AsyncMock(),
                state_store=MagicMock(),
            )
            return scanner

    @pytest.mark.asyncio
    async def test_should_scan_handles_filing_check_error(self, incremental_scanner):
        """Defaults to scanning on filing check error"""
        incremental_scanner._state_store.needs_rescan.return_value = (False, "check_filings")

        recent_time = (datetime.now(timezone.utc) - timedelta(days=5)).isoformat()
        incremental_scanner._state_store.get_state.return_value = TickerScanState(
            last_scan_time=recent_time,
            last_8k_date="2024-01-10",
            last_form4_date="2024-01-12",
            last_risk_score=50,
        )

        # Simulate error checking 8-K filings
        incremental_scanner._sec_collector.has_new_filings_8k.side_effect = Exception("API error")

        should_scan, reason = await incremental_scanner._should_scan("AAPL", 30)

        assert should_scan is True
        assert reason == "filing_check_error"
