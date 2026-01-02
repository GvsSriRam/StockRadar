"""Tests for scoring module"""

import pytest

from src.core.models import RiskLevel, Severity
from src.scoring import RuleBasedScorer, CategoryScorer


class TestRuleBasedScorer:
    """Tests for the RuleBasedScorer class (rule-only mode)"""

    def test_score_with_no_adjustments(self, empty_analysis_result, empty_sec_data):
        """Score should match base when no rules trigger (rule-only mode)"""
        scorer = RuleBasedScorer(use_category_scoring=False)
        result = scorer.score(empty_analysis_result, empty_sec_data)

        assert result.risk_score == empty_analysis_result.risk_score
        assert result.adjustments == 0
        assert len(result.adjustment_reasons) == 0

    def test_score_with_auditor_change(self, auditor_change_analysis):
        """Auditor change should add penalty (rule-only mode)"""
        scorer = RuleBasedScorer(use_category_scoring=False)
        result = scorer.score(auditor_change_analysis)

        base = auditor_change_analysis.risk_score
        assert result.risk_score == base + 15  # Default auditor penalty
        assert "+15 for auditor change" in result.adjustment_reasons

    def test_score_with_combined_signals(self, sample_analysis_result, sample_sec_data):
        """Red flags + insider selling should add penalty"""
        scorer = RuleBasedScorer(use_category_scoring=False)
        result = scorer.score(sample_analysis_result, sample_sec_data)

        assert "+5 for red flags + insider selling combination" in result.adjustment_reasons

    def test_score_capped_at_100(self, auditor_change_analysis):
        """Score should never exceed 100"""
        from src.core.models import AnalysisResult, InsiderSummary

        high_score_analysis = AnalysisResult(
            red_flags=auditor_change_analysis.red_flags,
            insider_patterns=tuple(),
            insider_summary=InsiderSummary(
                net_activity="neutral",
                total_sold=0,
                total_bought=0,
                insiders_selling=0,
                insiders_buying=0,
            ),
            risk_score=95,
            risk_level=RiskLevel.HIGH,
            reasoning="Test",
            explanation=None,
        )

        scorer = RuleBasedScorer(use_category_scoring=False)
        result = scorer.score(high_score_analysis)

        assert result.risk_score <= 100

    def test_risk_level_boundaries(self, empty_analysis_result):
        """Test risk level determination at boundaries"""
        test_cases = [
            (10, RiskLevel.LOW),
            (29, RiskLevel.LOW),
            (30, RiskLevel.MODERATE),
            (49, RiskLevel.MODERATE),
            (50, RiskLevel.ELEVATED),
            (69, RiskLevel.ELEVATED),
            (70, RiskLevel.HIGH),
            (100, RiskLevel.HIGH),
        ]

        for score, expected_level in test_cases:
            assert RiskLevel.from_score(score) == expected_level

    def test_get_scoring_method_rule_only(self):
        """Should return rule-based method name when category scoring disabled"""
        scorer = RuleBasedScorer(use_category_scoring=False)
        assert scorer.get_scoring_method() == "Rule-based adjustments"

    def test_get_scoring_method_with_category(self):
        """Should return category method name when category scoring enabled"""
        scorer = RuleBasedScorer(use_category_scoring=True)
        assert scorer.get_scoring_method() == "Category-weighted scoring with rule adjustments"


class TestCategoryScorer:
    """Tests for the CategoryScorer class"""

    def test_category_weights_sum_to_one(self):
        """Category weights should sum to 1.0"""
        scorer = CategoryScorer()
        total = sum(scorer.CATEGORY_WEIGHTS.values())
        assert total == pytest.approx(1.0)

    def test_calculate_category_scores(self, sample_analysis_result):
        """Should calculate scores per category"""
        scorer = CategoryScorer()
        scores = scorer.calculate_category_scores(sample_analysis_result)

        # Should have all categories
        for cat in scorer.CATEGORY_WEIGHTS:
            assert cat in scores

    def test_weighted_score_capped_at_100(self, sample_analysis_result):
        """Weighted score should be capped at 100"""
        scorer = CategoryScorer()
        final_score, _ = scorer.calculate_weighted_score(sample_analysis_result)

        assert 0 <= final_score <= 100

    def test_insider_activity_adds_to_insider_category(self, sample_analysis_result):
        """Insider selling should add to insider category score"""
        scorer = CategoryScorer()
        scores = scorer.calculate_category_scores(sample_analysis_result)

        # sample_analysis_result has net_selling, should add points
        assert scores['insider'] > 0
