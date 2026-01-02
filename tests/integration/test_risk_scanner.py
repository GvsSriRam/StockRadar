"""
Integration tests for RiskScannerService.

Tests the orchestration service with mocked dependencies.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone

from src.services.risk_scanner import RiskScannerService, RiskScannerBuilder
from src.core.models import (
    SECFilingData,
    Filing8K,
    InsiderTransaction,
    AnalysisResult,
    ScoringResult,
    RiskReport,
    RedFlag,
    InsiderPattern,
    InsiderSummary,
    RiskLevel,
    Severity,
)


class TestRiskScannerService:
    """Integration tests for RiskScannerService"""

    @pytest.fixture
    def mock_collector(self):
        """Mock SEC collector"""
        collector = AsyncMock()
        collector.collect.return_value = SECFilingData(
            ticker="TEST",
            cik="0001234567",
            filings_8k=(
                Filing8K(
                    date="2025-01-15",
                    form_type="8-K",
                    title="Current Report",
                    url="https://sec.gov/test/8k",
                    content_snippet="Executive departure announced...",
                    items=("5.02 - Departure/Appointment of Directors or Officers",),
                ),
            ),
            filings_form4=(
                InsiderTransaction(
                    date="2025-01-14",
                    insider_name="John Smith",
                    insider_title="CFO",
                    is_director=False,
                    is_officer=True,
                    transaction_type="S",
                    shares=50000,
                    price=150.00,
                    total_value=7500000,
                    url="https://sec.gov/test/form4",
                ),
            ),
            collected_at=datetime.now(timezone.utc),
            lookback_days=30,
            error=None,
        )
        collector.health_check.return_value = True
        collector.close = AsyncMock()
        return collector

    @pytest.fixture
    def mock_analyzer(self):
        """Mock LLM analyzer"""
        analyzer = AsyncMock()
        analyzer.analyze.return_value = AnalysisResult(
            red_flags=(
                RedFlag(
                    type="EXECUTIVE_DEPARTURE",
                    title="CFO Resignation",
                    severity=Severity.HIGH,
                    details="CFO resigned effective immediately",
                    evidence_url="https://sec.gov/test/8k",
                    filing_date="2025-01-15",
                ),
            ),
            insider_patterns=(
                InsiderPattern(
                    type="LARGE_SALE",
                    title="CFO Sold $7.5M",
                    severity=Severity.HIGH,
                    details="CFO sold 50,000 shares before resignation",
                    evidence_url="https://sec.gov/test/form4",
                ),
            ),
            insider_summary=InsiderSummary(
                net_activity="net_selling",
                total_sold=7500000,
                total_bought=0,
                insiders_selling=1,
                insiders_buying=0,
            ),
            risk_score=65,
            risk_level=RiskLevel.ELEVATED,
            reasoning="Executive departure with preceding insider selling",
            explanation="TEST shows elevated risk due to CFO departure and significant insider selling.",
        )
        analyzer.get_provider_name.return_value = "Groq (llama-3.3-70b-versatile)"
        return analyzer

    @pytest.fixture
    def mock_scorer(self):
        """Mock scorer"""
        scorer = MagicMock()
        scorer.score.return_value = ScoringResult(
            risk_score=70,
            risk_level=RiskLevel.HIGH,
            base_score=65,
            adjustments=5,
            adjustment_reasons=("+5 for red flags + insider selling combination",),
        )
        scorer.get_scoring_method.return_value = "Category-weighted scoring with rule adjustments"
        return scorer

    @pytest.mark.asyncio
    async def test_scan_single_ticker(self, mock_collector, mock_analyzer, mock_scorer):
        """Test scanning a single ticker"""
        # Mock the formatter to return a proper RiskReport
        mock_formatter = MagicMock()
        mock_formatter.format.return_value = RiskReport(
            ticker="TEST",
            risk_score=70,
            risk_level=RiskLevel.HIGH,
            red_flags=(
                RedFlag(
                    type="EXECUTIVE_DEPARTURE",
                    title="CFO Resignation",
                    severity=Severity.HIGH,
                    details="CFO resigned",
                ),
            ),
            red_flags_count=1,
            insider_patterns=(
                InsiderPattern(
                    type="LARGE_SALE",
                    title="CFO Sold $7.5M",
                    severity=Severity.HIGH,
                    details="CFO sold shares",
                ),
            ),
            insider_summary=InsiderSummary(
                net_activity="net_selling",
                total_sold=7500000,
                total_bought=0,
                insiders_selling=1,
                insiders_buying=0,
            ),
            explanation="Test explanation",
            reasoning="Test reasoning",
            evidence_links=("https://sec.gov/test",),
            filings_analyzed={"8k_count": 1, "form4_count": 1},
            scoring_details={},
            analyzed_at=datetime.now(timezone.utc),
            lookback_days=30,
        )

        service = RiskScannerService(
            collector=mock_collector,
            analyzer=mock_analyzer,
            scorer=mock_scorer,
        )
        service._formatter = mock_formatter

        result = await service.scan_ticker("TEST", lookback_days=30)

        assert result is not None
        assert result.success is True
        assert result.ticker == "TEST"
        assert result.report.risk_score == 70
        assert result.report.risk_level == RiskLevel.HIGH

        # Verify collector was called
        mock_collector.collect.assert_called_once_with("TEST", 30)

        # Verify analyzer was called
        mock_analyzer.analyze.assert_called_once()

        # Verify scorer was called
        mock_scorer.score.assert_called_once()

    @pytest.mark.asyncio
    async def test_scan_multiple_tickers(self, mock_collector, mock_analyzer, mock_scorer):
        """Test scanning multiple tickers"""
        mock_formatter = MagicMock()
        mock_formatter.format.return_value = RiskReport(
            ticker="TEST",
            risk_score=50,
            risk_level=RiskLevel.ELEVATED,
            red_flags=tuple(),
            red_flags_count=0,
            insider_patterns=tuple(),
            insider_summary=InsiderSummary(
                net_activity="neutral",
                total_sold=0,
                total_bought=0,
                insiders_selling=0,
                insiders_buying=0,
            ),
            explanation="Test",
            reasoning="Test",
            evidence_links=tuple(),
            filings_analyzed={},
            scoring_details={},
            analyzed_at=datetime.now(timezone.utc),
            lookback_days=30,
        )

        service = RiskScannerService(
            collector=mock_collector,
            analyzer=mock_analyzer,
            scorer=mock_scorer,
        )
        service._formatter = mock_formatter

        results = await service.scan_multiple(["AAPL", "MSFT", "GOOGL"], lookback_days=30)

        assert len(results) == 3
        assert mock_collector.collect.call_count == 3

    @pytest.mark.asyncio
    async def test_scan_handles_collector_error(self, mock_analyzer, mock_scorer):
        """Test that service handles collector errors gracefully"""
        from src.core.exceptions import CollectorError

        mock_collector = AsyncMock()
        mock_collector.collect.side_effect = CollectorError("Network error")
        mock_collector.close = AsyncMock()

        service = RiskScannerService(
            collector=mock_collector,
            analyzer=mock_analyzer,
            scorer=mock_scorer,
        )

        result = await service.scan_ticker("TEST", lookback_days=30)

        # Should return ScanResult with error
        assert result is not None
        assert result.success is False
        assert result.error is not None
        assert "Collection failed" in result.error

    @pytest.mark.asyncio
    async def test_scan_with_empty_filings(self, mock_analyzer, mock_scorer):
        """Test scanning when no filings are found"""
        mock_collector = AsyncMock()
        mock_collector.collect.return_value = SECFilingData(
            ticker="EMPTY",
            cik="0009999999",
            filings_8k=tuple(),
            filings_form4=tuple(),
            collected_at=datetime.now(timezone.utc),
            lookback_days=30,
            error=None,
        )
        mock_collector.close = AsyncMock()

        # Adjust analyzer mock for empty data
        mock_analyzer.analyze.return_value = AnalysisResult(
            red_flags=tuple(),
            insider_patterns=tuple(),
            insider_summary=InsiderSummary(
                net_activity="neutral",
                total_sold=0,
                total_bought=0,
                insiders_selling=0,
                insiders_buying=0,
            ),
            risk_score=10,
            risk_level=RiskLevel.LOW,
            reasoning="No filings found",
            explanation="No SEC filings in the lookback period.",
        )

        mock_scorer.score.return_value = ScoringResult(
            risk_score=10,
            risk_level=RiskLevel.LOW,
            base_score=10,
            adjustments=0,
            adjustment_reasons=tuple(),
        )

        mock_formatter = MagicMock()
        mock_formatter.format.return_value = RiskReport(
            ticker="EMPTY",
            risk_score=10,
            risk_level=RiskLevel.LOW,
            red_flags=tuple(),
            red_flags_count=0,
            insider_patterns=tuple(),
            insider_summary=InsiderSummary(
                net_activity="neutral",
                total_sold=0,
                total_bought=0,
                insiders_selling=0,
                insiders_buying=0,
            ),
            explanation="No filings",
            reasoning="No filings",
            evidence_links=tuple(),
            filings_analyzed={},
            scoring_details={},
            analyzed_at=datetime.now(timezone.utc),
            lookback_days=30,
        )

        service = RiskScannerService(
            collector=mock_collector,
            analyzer=mock_analyzer,
            scorer=mock_scorer,
        )
        service._formatter = mock_formatter

        result = await service.scan_ticker("EMPTY", lookback_days=30)

        assert result is not None
        assert result.success is True
        assert result.report.risk_level == RiskLevel.LOW
        assert len(result.report.red_flags) == 0


class TestRiskScannerBuilder:
    """Tests for RiskScannerBuilder fluent API"""

    def test_builder_creates_default_service(self):
        """Test that builder can create service with defaults"""
        with patch.dict('os.environ', {'GROQ_API_KEY': 'test-key'}):
            builder = RiskScannerBuilder()
            # Builder should be able to instantiate
            assert builder is not None

    def test_builder_custom_components(self):
        """Test that builder accepts custom components"""
        mock_collector = AsyncMock()
        mock_analyzer = AsyncMock()
        mock_scorer = MagicMock()

        builder = RiskScannerBuilder()
        builder = builder.with_collector(mock_collector)
        builder = builder.with_analyzer(mock_analyzer)
        builder = builder.with_scorer(mock_scorer)

        service = builder.build()

        assert service._collector is mock_collector
        assert service._analyzer is mock_analyzer
        assert service._scorer is mock_scorer


class TestWebhookIntegration:
    """Integration tests for webhook functionality"""

    @pytest.fixture
    def high_risk_report(self):
        """High risk report that should trigger webhook"""
        return RiskReport(
            ticker="RISK",
            risk_score=85,
            risk_level=RiskLevel.HIGH,
            red_flags=(
                RedFlag(
                    type="AUDITOR_CHANGE",
                    title="Auditor Resigned",
                    severity=Severity.HIGH,
                    details="Auditor resigned citing disagreements",
                ),
            ),
            red_flags_count=1,
            insider_patterns=tuple(),
            insider_summary=InsiderSummary(
                net_activity="neutral",
                total_sold=0,
                total_bought=0,
                insiders_selling=0,
                insiders_buying=0,
            ),
            explanation="High risk detected",
            reasoning="Auditor change is a critical signal",
            evidence_links=("https://sec.gov/test",),
            filings_analyzed={"8k_count": 1, "form4_count": 0},
            scoring_details={},
            analyzed_at=datetime.now(timezone.utc),
            lookback_days=30,
        )

    def test_webhook_threshold_check(self, high_risk_report):
        """Test that high risk reports exceed webhook threshold"""
        threshold = 70
        assert high_risk_report.risk_score >= threshold

    def test_webhook_payload_format(self, high_risk_report):
        """Test webhook payload can be generated"""
        from src.formatters.webhook_formatter import WebhookFormatter

        formatter = WebhookFormatter()
        payload = formatter.format_generic_payload(high_risk_report)

        assert isinstance(payload, dict)
        assert "ticker" in payload
        assert "risk_score" in payload
        assert payload["risk_score"] == 85
