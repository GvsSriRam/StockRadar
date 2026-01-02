"""
Incremental Scanner Service

Wraps RiskScannerService with incremental scanning logic to skip
tickers that haven't had new filings since their last scan.
"""

import logging
from typing import Optional

from ..config import Settings, get_settings
from ..collectors.sec_collector import SECCollector
from ..storage.scan_state import ScanStateStore, ScanStats
from .risk_scanner import RiskScannerService, ScanResult


logger = logging.getLogger(__name__)


class IncrementalScanner:
    """
    Wraps RiskScannerService with incremental scanning logic.

    Incremental scanning skips tickers that:
    1. Have been scanned within lookback_days
    2. Have no new 8-K or Form 4 filings since last scan

    This significantly reduces API calls on scheduled runs.
    """

    def __init__(
        self,
        scanner: Optional[RiskScannerService] = None,
        sec_collector: Optional[SECCollector] = None,
        state_store: Optional[ScanStateStore] = None,
        settings: Optional[Settings] = None,
    ):
        """
        Initialize incremental scanner.

        Args:
            scanner: RiskScannerService instance (creates default if not provided)
            sec_collector: SECCollector for filing checks (creates default if not provided)
            state_store: ScanStateStore for state persistence (creates default if not provided)
            settings: Application settings
        """
        self._settings = settings or get_settings()
        self._scanner = scanner or RiskScannerService(settings=self._settings)
        self._sec_collector = sec_collector or SECCollector(settings=self._settings)
        self._state_store = state_store or ScanStateStore()
        self._state_loaded = False

    async def _ensure_state_loaded(self) -> None:
        """Ensure state is loaded from store"""
        if not self._state_loaded:
            await self._state_store.load()
            self._state_loaded = True

    async def scan_incremental(
        self,
        tickers: list[str],
        lookback_days: int = 30,
        include_explanation: bool = True,
        force_rescan: bool = False,
    ) -> tuple[list[ScanResult], ScanStats]:
        """
        Scan only tickers that need rescanning.

        Decision tree for each ticker:
        1. If force_rescan=True → scan
        2. If never scanned → scan
        3. If last scan > lookback_days ago → scan (stale)
        4. If new 8-K filings since last scan → scan
        5. If new Form 4 filings since last scan → scan
        6. Otherwise → skip

        Args:
            tickers: List of ticker symbols
            lookback_days: Staleness threshold in days
            include_explanation: Generate plain-English explanations
            force_rescan: Bypass incremental logic, scan all tickers

        Returns:
            Tuple of (results, stats) where:
            - results: List of ScanResult for processed tickers
            - stats: ScanStats with counts and skip reasons
        """
        await self._ensure_state_loaded()

        results: list[ScanResult] = []
        skip_reasons: dict[str, int] = {}
        scanned_count = 0
        skipped_count = 0

        for i, ticker in enumerate(tickers):
            ticker = ticker.upper().strip()
            progress = f"[{i+1}/{len(tickers)}]"

            # Determine if we need to scan
            if force_rescan:
                should_scan = True
                reason = "force_rescan"
            else:
                should_scan, reason = await self._should_scan(ticker, lookback_days)

            if should_scan:
                logger.info(f"{progress} Scanning {ticker} (reason: {reason})")
                result = await self._scanner.scan_ticker(
                    ticker,
                    lookback_days=lookback_days,
                    include_explanation=include_explanation,
                )
                results.append(result)
                scanned_count += 1

                # Update state after successful scan
                if result.success and result.report:
                    await self._update_state_after_scan(ticker, result)

            else:
                logger.info(f"{progress} Skipping {ticker} (reason: {reason})")
                skip_reasons[reason] = skip_reasons.get(reason, 0) + 1
                skipped_count += 1

        # Save state after all scans complete
        await self._state_store.save()

        stats = ScanStats(
            total=len(tickers),
            scanned=scanned_count,
            skipped=skipped_count,
            reasons=skip_reasons,
        )

        logger.info(f"Incremental scan complete: {stats}")
        return results, stats

    async def _should_scan(
        self, ticker: str, lookback_days: int
    ) -> tuple[bool, str]:
        """
        Determine if a ticker should be scanned.

        Args:
            ticker: Stock ticker symbol
            lookback_days: Staleness threshold in days

        Returns:
            (should_scan, reason) tuple
        """
        # Check time-based staleness first (cheap, no API calls)
        should_scan, reason = self._state_store.needs_rescan(ticker, lookback_days)

        if should_scan:
            return True, reason

        # Time-based check passed, now check for new filings
        # This requires 2 API calls but avoids full scan if no new filings
        state = self._state_store.get_state(ticker)
        if state is None:
            return True, "never_scanned"

        # Check for new 8-K filings
        if state.last_8k_date:
            try:
                has_new_8k = await self._sec_collector.has_new_filings_8k(
                    ticker, state.last_8k_date
                )
                if has_new_8k:
                    return True, "new_8k_filing"
            except Exception as e:
                logger.warning(f"Failed to check 8-K filings for {ticker}: {e}")
                # On error, default to scanning
                return True, "filing_check_error"

        # Check for new Form 4 filings
        if state.last_form4_date:
            try:
                has_new_form4 = await self._sec_collector.has_new_filings_form4(
                    ticker, state.last_form4_date
                )
                if has_new_form4:
                    return True, "new_form4_filing"
            except Exception as e:
                logger.warning(f"Failed to check Form 4 filings for {ticker}: {e}")
                return True, "filing_check_error"

        # No new filings found
        return False, "unchanged"

    async def _update_state_after_scan(
        self, ticker: str, result: ScanResult
    ) -> None:
        """Update scan state after a successful scan"""
        if not result.report:
            return

        # Get latest filing dates from SEC
        try:
            latest_8k, latest_form4 = await self._sec_collector.get_latest_filing_dates(
                ticker
            )
        except Exception as e:
            logger.warning(f"Failed to get latest filing dates for {ticker}: {e}")
            latest_8k, latest_form4 = None, None

        self._state_store.update_state(
            ticker=ticker,
            risk_score=result.report.risk_score,
            last_8k_date=latest_8k,
            last_form4_date=latest_form4,
        )

    async def close(self) -> None:
        """Close resources"""
        await self._sec_collector.close()