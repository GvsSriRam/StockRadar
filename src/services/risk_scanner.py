"""
Risk Scanner Service

Main orchestration service that coordinates all components.
Implements dependency injection for flexible component configuration.
"""

import logging
from dataclasses import dataclass
from typing import Optional, Protocol

from ..config import Settings, get_settings
from ..core.interfaces import DataCollector, BaseAnalyzer, BaseScorer
from ..core.models import RiskReport
from ..core.exceptions import StockRadarError, CollectorError, AnalyzerError
from ..collectors.sec_collector import SECCollector
from ..analyzers.llm_analyzer import GroqLLMAnalyzer
from ..scoring.rule_scorer import RuleBasedScorer
from ..formatters.json_formatter import JsonFormatter


logger = logging.getLogger(__name__)


@dataclass
class ScanResult:
    """Result of scanning a single ticker"""
    ticker: str
    report: Optional[RiskReport]
    error: Optional[str]
    success: bool


class RiskScannerService:
    """
    Main service for scanning stocks for risk signals.

    Coordinates:
    - Data collection from SEC
    - Risk analysis via LLM
    - Scoring adjustments
    - Output formatting

    Uses dependency injection for all components, enabling
    easy testing and component swapping.
    """

    def __init__(
        self,
        collector: Optional[DataCollector] = None,
        analyzer: Optional[BaseAnalyzer] = None,
        scorer: Optional[BaseScorer] = None,
        settings: Optional[Settings] = None,
    ):
        """
        Initialize with injectable components.

        Args:
            collector: Data collector (defaults to SECCollector)
            analyzer: Risk analyzer (defaults to GroqLLMAnalyzer)
            scorer: Risk scorer (defaults to RuleBasedScorer)
            settings: Application settings

        Raises:
            AnalyzerError: If GROQ_API_KEY is not configured
        """
        self._settings = settings or get_settings()
        self._collector = collector or self._create_default_collector()
        self._analyzer = analyzer or self._create_default_analyzer()
        self._scorer = scorer or self._create_default_scorer()
        self._formatter = JsonFormatter()

    def _create_default_collector(self) -> DataCollector:
        """Create default SEC collector"""
        return SECCollector(settings=self._settings)

    def _create_default_analyzer(self) -> BaseAnalyzer:
        """Create default LLM analyzer. Requires GROQ_API_KEY."""
        if not self._settings.llm.is_configured:
            raise AnalyzerError("GROQ_API_KEY is required. Set it in .env file.")
        return GroqLLMAnalyzer(settings=self._settings)

    def _create_default_scorer(self) -> BaseScorer:
        """Create default scorer"""
        return RuleBasedScorer(settings=self._settings)

    async def scan_ticker(
        self,
        ticker: str,
        lookback_days: int = 30,
        include_explanation: bool = True,
    ) -> ScanResult:
        """
        Scan a single ticker for risk signals.

        Args:
            ticker: Stock ticker symbol
            lookback_days: Days of filings to analyze
            include_explanation: Generate plain-English explanation

        Returns:
            ScanResult with report or error
        """
        ticker = ticker.upper().strip()
        logger.info(f"Scanning {ticker} (lookback: {lookback_days} days)")

        try:
            # Step 1: Collect SEC data
            logger.debug(f"Collecting SEC data for {ticker}")
            sec_data = await self._collector.collect(ticker, lookback_days)

            if sec_data.error:
                logger.warning(f"Collection warning for {ticker}: {sec_data.error}")

            logger.info(f"Found {sec_data.total_filings} filings for {ticker}")

            # Step 2: Analyze for risk signals
            logger.debug(f"Analyzing {ticker} with {self._analyzer.get_provider_name()}")
            analysis = await self._analyzer.analyze(sec_data, include_explanation)

            # Step 3: Apply scoring adjustments
            logger.debug(f"Scoring {ticker} with {self._scorer.get_scoring_method()}")
            scoring = self._scorer.score(analysis, sec_data)

            # Step 4: Format output
            report = self._formatter.format(ticker, sec_data, analysis, scoring)

            logger.info(
                f"{ticker}: Score {report.risk_score}/100 ({report.risk_level.value})"
            )

            return ScanResult(
                ticker=ticker,
                report=report,
                error=None,
                success=True,
            )

        except CollectorError as e:
            logger.error(f"Collection error for {ticker}: {e}")
            return ScanResult(
                ticker=ticker,
                report=None,
                error=f"Collection failed: {e.message}",
                success=False,
            )

        except AnalyzerError as e:
            logger.error(f"Analysis error for {ticker}: {e}")
            return ScanResult(
                ticker=ticker,
                report=None,
                error=f"Analysis failed: {e.message}",
                success=False,
            )

        except Exception as e:
            logger.error(f"Unexpected error for {ticker}: {e}")
            return ScanResult(
                ticker=ticker,
                report=None,
                error=str(e),
                success=False,
            )

    async def scan_multiple(
        self,
        tickers: list[str],
        lookback_days: int = 30,
        include_explanation: bool = True,
    ) -> list[ScanResult]:
        """
        Scan multiple tickers sequentially.

        Args:
            tickers: List of ticker symbols
            lookback_days: Days of filings to analyze
            include_explanation: Generate plain-English explanations

        Returns:
            List of ScanResults
        """
        results = []

        for i, ticker in enumerate(tickers):
            logger.info(f"[{i+1}/{len(tickers)}] Processing {ticker}")

            result = await self.scan_ticker(
                ticker,
                lookback_days=lookback_days,
                include_explanation=include_explanation,
            )
            results.append(result)

        return results

    def get_summary(self, results: list[ScanResult]) -> dict:
        """
        Generate summary statistics from results.

        Args:
            results: List of ScanResults

        Returns:
            Summary dictionary
        """
        successful = [r for r in results if r.success and r.report]
        failed = [r for r in results if not r.success]

        high_risk = [
            r for r in successful
            if r.report and r.report.risk_level.value == "high"
        ]
        elevated = [
            r for r in successful
            if r.report and r.report.risk_level.value == "elevated"
        ]

        return {
            "total": len(results),
            "successful": len(successful),
            "failed": len(failed),
            "high_risk_count": len(high_risk),
            "elevated_count": len(elevated),
            "high_risk_tickers": [r.ticker for r in high_risk],
            "elevated_tickers": [r.ticker for r in elevated],
            "failed_tickers": [r.ticker for r in failed],
        }


class RiskScannerBuilder:
    """
    Builder for RiskScannerService.

    Provides fluent API for configuring the service.
    """

    def __init__(self):
        self._collector: Optional[DataCollector] = None
        self._analyzer: Optional[BaseAnalyzer] = None
        self._scorer: Optional[BaseScorer] = None
        self._settings: Optional[Settings] = None

    def with_settings(self, settings: Settings) -> "RiskScannerBuilder":
        """Set custom settings"""
        self._settings = settings
        return self

    def with_collector(self, collector: DataCollector) -> "RiskScannerBuilder":
        """Set custom collector"""
        self._collector = collector
        return self

    def with_analyzer(self, analyzer: BaseAnalyzer) -> "RiskScannerBuilder":
        """Set custom analyzer"""
        self._analyzer = analyzer
        return self

    def with_scorer(self, scorer: BaseScorer) -> "RiskScannerBuilder":
        """Set custom scorer"""
        self._scorer = scorer
        return self

    def with_llm(self, api_key: str) -> "RiskScannerBuilder":
        """Enable LLM with API key"""
        settings = self._settings or get_settings()
        self._settings = settings.with_llm_key(api_key)
        return self

    def build(self) -> RiskScannerService:
        """Build the configured service"""
        return RiskScannerService(
            collector=self._collector,
            analyzer=self._analyzer,
            scorer=self._scorer,
            settings=self._settings,
        )
