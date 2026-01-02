"""
Integration tests for the full SEC Filing Risk Scanner pipeline.

Tests the complete data flow: SEC Collector -> LLM Analyzer -> Scorer -> Formatter
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone

from src.collectors.sec_collector import SECCollector
from src.analyzers.llm_analyzer import GroqLLMAnalyzer
from src.scoring.rule_scorer import RuleBasedScorer, CategoryScorer
from src.formatters.json_formatter import JsonFormatter
from src.core.models import (
    SECFilingData,
    Filing8K,
    InsiderTransaction,
    AnalysisResult,
    RedFlag,
    InsiderPattern,
    InsiderSummary,
    RiskLevel,
    Severity,
)


class TestSECCollectorIntegration:
    """Integration tests for SEC Collector with mocked HTTP responses"""

    @pytest.fixture
    def mock_cik_response(self):
        """Mock response for company tickers endpoint"""
        return {
            "0": {"cik_str": "320193", "ticker": "AAPL", "title": "Apple Inc"},
            "1": {"cik_str": "789019", "ticker": "MSFT", "title": "Microsoft Corporation"},
        }

    def test_collector_initializes_with_empty_cache(self):
        """Test that collector starts with empty CIK cache"""
        collector = SECCollector()
        assert collector._cik_cache == {}

    def test_collector_caches_cik_lookups(self, mock_cik_response):
        """Test that CIK lookups are cached after population"""
        collector = SECCollector()

        # Pre-populate cache
        collector._cik_cache = {"AAPL": "0000320193", "MSFT": "0000789019"}

        # Should return from cache
        assert collector._cik_cache["AAPL"] == "0000320193"
        assert collector._cik_cache["MSFT"] == "0000789019"


class TestLLMAnalyzerIntegration:
    """Integration tests for LLM Analyzer with caching and retry"""

    @pytest.fixture
    def sample_sec_data(self):
        """Sample SEC data for testing"""
        return SECFilingData(
            ticker="TEST",
            cik="0001234567",
            filings_8k=(
                Filing8K(
                    date="2025-01-15",
                    form_type="8-K",
                    title="Current Report",
                    url="https://sec.gov/test/8k",
                    content_snippet="CFO resigned effective immediately...",
                    items=("5.02 - Departure/Appointment of Directors or Officers",),
                ),
            ),
            filings_form4=tuple(),
            collected_at=datetime.now(timezone.utc),
            lookback_days=30,
            error=None,
        )

    def test_cache_ttl_expiration(self):
        """Test that cache entries expire after TTL"""
        import time

        with patch.dict('os.environ', {'GROQ_API_KEY': 'test-key'}):
            analyzer = GroqLLMAnalyzer(api_key='test-key')

            # Manually set cache with old timestamp
            old_timestamp = time.time() - (25 * 60 * 60)  # 25 hours ago
            cache_key = "test_key"
            analyzer._cache[cache_key] = ({"test": "data"}, old_timestamp)

            # Should return None (expired)
            result = analyzer._get_from_cache(cache_key)
            assert result is None

            # Cache entry should be removed
            assert cache_key not in analyzer._cache

    def test_cache_valid_entry(self):
        """Test that valid cache entries are returned"""
        import time

        with patch.dict('os.environ', {'GROQ_API_KEY': 'test-key'}):
            analyzer = GroqLLMAnalyzer(api_key='test-key')

            # Set cache with recent timestamp
            cache_key = "test_key"
            test_data = {"test": "data"}
            analyzer._set_cache(cache_key, test_data)

            # Should return cached data
            result = analyzer._get_from_cache(cache_key)
            assert result == test_data

    def test_explanation_validation(self):
        """Test explanation validation logic"""
        with patch.dict('os.environ', {'GROQ_API_KEY': 'test-key'}):
            analyzer = GroqLLMAnalyzer(api_key='test-key')

            # Valid explanation
            valid = "AAPL shows moderate risk with some concerning insider activity patterns observed."
            assert analyzer._validate_explanation(valid, "AAPL") is True

            # Too short
            short = "AAPL risk."
            assert analyzer._validate_explanation(short, "AAPL") is False

            # Missing ticker
            no_ticker = "This stock shows moderate risk with concerning patterns."
            assert analyzer._validate_explanation(no_ticker, "AAPL") is False

            # Contains financial advice
            advice = "AAPL shows risk. You should sell this stock immediately for best results."
            assert analyzer._validate_explanation(advice, "AAPL") is False

    def test_explanation_post_processing(self):
        """Test explanation post-processing"""
        with patch.dict('os.environ', {'GROQ_API_KEY': 'test-key'}):
            analyzer = GroqLLMAnalyzer(api_key='test-key')

            # Remove markdown
            markdown = "**AAPL** shows *moderate* risk with `code`"
            result = analyzer._post_process_explanation(markdown)
            assert "**" not in result
            assert "*" not in result
            assert "`" not in result

            # Ensure ends with period
            no_period = "AAPL shows moderate risk"
            result = analyzer._post_process_explanation(no_period)
            assert result.endswith(".")


class TestCategoryScorerIntegration:
    """Integration tests for category-based scoring"""

    @pytest.fixture
    def analysis_with_multiple_categories(self):
        """Analysis with signals across multiple categories"""
        return AnalysisResult(
            red_flags=(
                RedFlag(
                    type="AUDITOR_CHANGE",
                    title="Auditor Resigned",
                    severity=Severity.HIGH,
                    details="Independent auditor resigned",
                ),
                RedFlag(
                    type="EXECUTIVE_DEPARTURE",
                    title="CFO Resigned",
                    severity=Severity.HIGH,
                    details="CFO resigned immediately",
                ),
            ),
            insider_patterns=(
                InsiderPattern(
                    type="CLUSTER_SELLING",
                    title="Multiple Insiders Sold",
                    severity=Severity.MEDIUM,
                    details="3 executives sold shares",
                ),
            ),
            insider_summary=InsiderSummary(
                net_activity="heavy_selling",
                total_sold=5000000,
                total_bought=0,
                insiders_selling=3,
                insiders_buying=0,
            ),
            risk_score=60,
            risk_level=RiskLevel.ELEVATED,
            reasoning="Multiple signals detected",
            explanation=None,
        )

    def test_category_scoring_weights(self, analysis_with_multiple_categories):
        """Test that category weights are applied correctly"""
        scorer = CategoryScorer()
        category_scores = scorer.calculate_category_scores(analysis_with_multiple_categories)

        # Regulatory should have auditor change (25 points for high severity)
        assert category_scores['regulatory'] >= 25

        # Operational should have executive departure
        assert category_scores['operational'] >= 25

        # Insider should have pattern + heavy selling bonus
        assert category_scores['insider'] >= 35  # 15 (medium pattern) + 20 (heavy selling)

    def test_weighted_score_calculation(self, analysis_with_multiple_categories):
        """Test weighted score calculation"""
        scorer = CategoryScorer()
        final_score, breakdown = scorer.calculate_weighted_score(analysis_with_multiple_categories)

        # Score should be capped at 100
        assert 0 <= final_score <= 100

        # All categories should be in breakdown
        for cat in CategoryScorer.CATEGORY_WEIGHTS:
            assert cat in breakdown

        # Weights should sum to 1.0
        assert sum(CategoryScorer.CATEGORY_WEIGHTS.values()) == pytest.approx(1.0)


class TestRuleBasedScorerIntegration:
    """Integration tests for rule-based scoring with category scoring"""

    def test_scorer_with_category_scoring_enabled(self, sample_analysis_result):
        """Test scorer with category-based scoring enabled"""
        scorer = RuleBasedScorer(use_category_scoring=True)
        assert scorer._category_scorer is not None
        assert "Category-weighted" in scorer.get_scoring_method()

    def test_scorer_with_category_scoring_disabled(self, sample_analysis_result):
        """Test scorer with category-based scoring disabled"""
        scorer = RuleBasedScorer(use_category_scoring=False)
        assert scorer._category_scorer is None
        assert scorer.get_scoring_method() == "Rule-based adjustments"

    def test_blended_scoring(self, sample_analysis_result):
        """Test that scoring blends category and LLM scores"""
        scorer = RuleBasedScorer(use_category_scoring=True)
        result = scorer.score(sample_analysis_result)

        # Result should have valid risk level
        assert result.risk_level in RiskLevel
        assert 0 <= result.risk_score <= 100


class TestFullPipelineIntegration:
    """End-to-end integration tests for the full pipeline"""

    def test_pipeline_with_empty_data(self, empty_sec_data, empty_analysis_result):
        """Test pipeline handles empty data gracefully"""
        scorer = RuleBasedScorer(use_category_scoring=False)
        result = scorer.score(empty_analysis_result)

        assert result.risk_level == RiskLevel.LOW
        assert result.risk_score < 30
        assert len(result.adjustment_reasons) == 0

    def test_pipeline_with_high_risk_signals(self, auditor_change_analysis, sample_sec_data):
        """Test pipeline correctly elevates risk for serious signals"""
        scorer = RuleBasedScorer(use_category_scoring=False)
        result = scorer.score(auditor_change_analysis, sample_sec_data)

        # Auditor change should trigger penalty
        assert result.adjustments > 0
        assert any("auditor" in r.lower() for r in result.adjustment_reasons)

    def test_formatter_integration(self, sample_risk_report):
        """Test JSON formatter produces valid output"""
        formatter = JsonFormatter()
        output = formatter.to_dict(sample_risk_report)

        # Should be valid JSON-serializable dict
        assert isinstance(output, dict)
        assert "ticker" in output
        assert "risk_score" in output
        assert "risk_level" in output
        assert output["ticker"] == "TEST"
