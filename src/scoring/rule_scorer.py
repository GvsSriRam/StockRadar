"""
Rule-Based Scorer

Applies configurable rule-based adjustments to risk scores.
Implements the Strategy pattern for scoring algorithms.
"""

from typing import Optional

from ..config import Settings, get_settings
from ..core.interfaces import BaseScorer
from ..core.models import (
    SECFilingData,
    AnalysisResult,
    ScoringResult,
    RiskLevel,
    Severity,
)


class ScoringRule:
    """Represents a scoring rule with condition and adjustment"""

    def __init__(
        self,
        name: str,
        adjustment: int,
        reason_template: str
    ):
        self.name = name
        self.adjustment = adjustment
        self.reason_template = reason_template

    def apply(self, analysis: AnalysisResult, data: Optional[SECFilingData]) -> tuple[int, str]:
        """
        Apply rule and return adjustment and reason.

        Override in subclasses for specific rule logic.
        Returns (adjustment, reason) or (0, "") if rule doesn't apply.
        """
        raise NotImplementedError


class AuditorChangeRule(ScoringRule):
    """Adds penalty for auditor changes"""

    def __init__(self, penalty: int = 15):
        super().__init__(
            name="auditor_change",
            adjustment=penalty,
            reason_template="+{adj} for auditor change"
        )

    def apply(self, analysis: AnalysisResult, data: Optional[SECFilingData]) -> tuple[int, str]:
        for flag in analysis.red_flags:
            if flag.type == "AUDITOR_CHANGE":
                return self.adjustment, self.reason_template.format(adj=self.adjustment)
        return 0, ""


class FinancialRestatementRule(ScoringRule):
    """Adds penalty for financial restatements"""

    def __init__(self, penalty: int = 20):
        super().__init__(
            name="financial_restatement",
            adjustment=penalty,
            reason_template="+{adj} for financial restatement"
        )

    def apply(self, analysis: AnalysisResult, data: Optional[SECFilingData]) -> tuple[int, str]:
        for flag in analysis.red_flags:
            if flag.type == "FINANCIAL_RESTATEMENT":
                return self.adjustment, self.reason_template.format(adj=self.adjustment)
        return 0, ""


class MultipleRedFlagsRule(ScoringRule):
    """Adds penalty for multiple red flags"""

    def __init__(self, penalty: int = 10, threshold: int = 3):
        super().__init__(
            name="multiple_red_flags",
            adjustment=penalty,
            reason_template="+{adj} for {count} red flags"
        )
        self.threshold = threshold

    def apply(self, analysis: AnalysisResult, data: Optional[SECFilingData]) -> tuple[int, str]:
        count = len(analysis.red_flags)
        if count >= self.threshold:
            return self.adjustment, self.reason_template.format(adj=self.adjustment, count=count)
        return 0, ""


class HighSeverityPatternsRule(ScoringRule):
    """Adds penalty for multiple high-severity insider patterns"""

    def __init__(self, penalty: int = 10, threshold: int = 2):
        super().__init__(
            name="high_severity_patterns",
            adjustment=penalty,
            reason_template="+{adj} for multiple high-severity insider patterns"
        )
        self.threshold = threshold

    def apply(self, analysis: AnalysisResult, data: Optional[SECFilingData]) -> tuple[int, str]:
        high_severity = [
            p for p in analysis.insider_patterns
            if p.severity == Severity.HIGH
        ]
        if len(high_severity) >= self.threshold:
            return self.adjustment, self.reason_template.format(adj=self.adjustment)
        return 0, ""


class CombinedSignalsRule(ScoringRule):
    """Adds penalty for red flags combined with insider selling"""

    def __init__(self, penalty: int = 5):
        super().__init__(
            name="combined_signals",
            adjustment=penalty,
            reason_template="+{adj} for red flags + insider selling combination"
        )

    def apply(self, analysis: AnalysisResult, data: Optional[SECFilingData]) -> tuple[int, str]:
        has_red_flags = len(analysis.red_flags) > 0
        has_insider_selling = analysis.insider_summary.net_activity == "net_selling"

        if has_red_flags and has_insider_selling:
            return self.adjustment, self.reason_template.format(adj=self.adjustment)
        return 0, ""


class Critical8KItemsRule(ScoringRule):
    """Checks raw SEC data for critical 8-K items"""

    CRITICAL_ITEMS = {
        "4.01": 15,  # Auditor change
        "4.02": 20,  # Financial restatement
    }

    def __init__(self):
        super().__init__(
            name="critical_8k_items",
            adjustment=0,
            reason_template="+{adj} for Item {item}"
        )

    def apply(self, analysis: AnalysisResult, data: Optional[SECFilingData]) -> tuple[int, str]:
        if not data:
            return 0, ""

        total_adjustment = 0
        reasons = []

        for filing in data.filings_8k:
            for item in filing.items:
                for critical_item, penalty in self.CRITICAL_ITEMS.items():
                    if critical_item in item:
                        total_adjustment += penalty
                        reasons.append(f"+{penalty} for Item {critical_item}")

        if total_adjustment > 0:
            return total_adjustment, "; ".join(reasons)
        return 0, ""


class CategoryScorer:
    """
    Category-based weighted scoring as per SCORING-ENGINE.md.

    Categorizes signals and applies weighted scoring:
    - Regulatory: 30% (auditor changes, restatements, SEC filings)
    - Operational: 25% (layoffs, restructuring, management changes)
    - Narrative: 20% (press releases, communication patterns)
    - Insider: 15% (insider trading patterns)
    - Momentum: 10% (score changes over time)
    """

    CATEGORY_WEIGHTS = {
        'regulatory': 0.30,
        'operational': 0.25,
        'narrative': 0.20,
        'insider': 0.15,
        'momentum': 0.10,
    }

    # Maps red flag types to categories
    FLAG_CATEGORIES = {
        # Regulatory signals
        'AUDITOR_CHANGE': 'regulatory',
        'FINANCIAL_RESTATEMENT': 'regulatory',
        'MATERIAL_WEAKNESS': 'regulatory',
        'NON_RELIANCE': 'regulatory',
        'DELISTING_NOTICE': 'regulatory',
        'SEC_INVESTIGATION': 'regulatory',

        # Operational signals
        'EXECUTIVE_DEPARTURE': 'operational',
        'LAYOFF_ANNOUNCEMENT': 'operational',
        'RESTRUCTURING': 'operational',
        'COST_REDUCTION': 'operational',
        'IMPAIRMENT': 'operational',
        'CONTRACT_TERMINATION': 'operational',

        # Narrative signals
        'EARNINGS_MISS': 'narrative',
        'GUIDANCE_LOWERED': 'narrative',
        'MATERIAL_EVENT': 'narrative',
        'REGULATORY_FD': 'narrative',

        # Default for unknown types
        'UNKNOWN': 'operational',
    }

    # Base severity scores
    SEVERITY_SCORES = {
        'high': 25,
        'medium': 15,
        'low': 5,
    }

    def calculate_category_scores(self, analysis: AnalysisResult) -> dict[str, float]:
        """
        Calculate raw scores for each category.

        Returns dict with category names as keys and raw scores as values.
        """
        category_scores = {cat: 0.0 for cat in self.CATEGORY_WEIGHTS}

        # Score red flags
        for flag in analysis.red_flags:
            category = self.FLAG_CATEGORIES.get(flag.type, 'operational')
            severity_score = self.SEVERITY_SCORES.get(flag.severity.value, 15)
            category_scores[category] += severity_score

        # Score insider patterns
        for pattern in analysis.insider_patterns:
            severity_score = self.SEVERITY_SCORES.get(pattern.severity.value, 15)
            category_scores['insider'] += severity_score

        # Add insider summary contribution
        if analysis.insider_summary.net_activity == 'heavy_selling':
            category_scores['insider'] += 20
        elif analysis.insider_summary.net_activity == 'net_selling':
            category_scores['insider'] += 10

        return category_scores

    def calculate_weighted_score(self, analysis: AnalysisResult) -> tuple[int, dict[str, float]]:
        """
        Calculate the final weighted score.

        Returns:
            Tuple of (final_score, category_breakdown)
        """
        category_scores = self.calculate_category_scores(analysis)

        # Apply weights and sum
        weighted_total = 0.0
        category_breakdown = {}

        for category, weight in self.CATEGORY_WEIGHTS.items():
            raw_score = category_scores[category]
            # Cap individual category contribution at 100 points before weighting
            capped_score = min(raw_score, 100)
            weighted_contribution = capped_score * weight
            category_breakdown[category] = weighted_contribution
            weighted_total += weighted_contribution

        # Cap final score at 100
        final_score = min(int(weighted_total), 100)

        return final_score, category_breakdown


class RuleBasedScorer(BaseScorer):
    """
    Applies rule-based adjustments to analysis scores.

    Uses a collection of ScoringRules that can be configured
    or extended at runtime. Optionally uses category-based
    weighted scoring for more nuanced risk assessment.
    """

    def __init__(self, settings: Optional[Settings] = None, use_category_scoring: bool = True):
        """
        Initialize with configurable rules.

        Args:
            settings: Application settings
            use_category_scoring: Whether to use category-based weighted scoring
        """
        self._settings = settings or get_settings()
        self._rules = self._create_default_rules()
        self._use_category_scoring = use_category_scoring
        self._category_scorer = CategoryScorer() if use_category_scoring else None

    def _create_default_rules(self) -> list[ScoringRule]:
        """Create default scoring rules from settings"""
        s = self._settings.scoring
        return [
            AuditorChangeRule(penalty=s.auditor_change_penalty),
            FinancialRestatementRule(penalty=s.financial_restatement_penalty),
            MultipleRedFlagsRule(penalty=s.multiple_flags_penalty, threshold=s.multiple_flags_threshold),
            HighSeverityPatternsRule(penalty=s.high_severity_pattern_penalty, threshold=s.high_severity_pattern_threshold),
            CombinedSignalsRule(penalty=s.insider_combo_penalty),
            Critical8KItemsRule(),
        ]

    def add_rule(self, rule: ScoringRule) -> None:
        """Add a custom scoring rule"""
        self._rules.append(rule)

    def get_scoring_method(self) -> str:
        if self._use_category_scoring:
            return "Category-weighted scoring with rule adjustments"
        return "Rule-based adjustments"

    def score(
        self,
        analysis: AnalysisResult,
        data: Optional[SECFilingData] = None
    ) -> ScoringResult:
        """
        Apply scoring to analysis result.

        When category scoring is enabled:
        1. Calculate category-weighted base score
        2. Apply rule-based adjustments

        Args:
            analysis: Analysis result to score
            data: Optional raw data for additional checks

        Returns:
            ScoringResult with adjusted score
        """
        # Determine base score
        if self._use_category_scoring and self._category_scorer:
            category_score, category_breakdown = self._category_scorer.calculate_weighted_score(analysis)
            # Use category score as base, but blend with LLM score for stability
            # 60% category-based, 40% LLM-based (as per documentation)
            base_score = int(0.6 * category_score + 0.4 * analysis.risk_score)
        else:
            base_score = analysis.risk_score

        # Apply rule-based adjustments
        total_adjustments = 0
        adjustment_reasons = []

        for rule in self._rules:
            adjustment, reason = rule.apply(analysis, data)
            if adjustment != 0:
                total_adjustments += adjustment
                if reason:
                    adjustment_reasons.append(reason)

        final_score = min(100, max(0, base_score + total_adjustments))

        return ScoringResult(
            risk_score=final_score,
            risk_level=RiskLevel.from_score(final_score),
            base_score=base_score,
            adjustments=total_adjustments,
            adjustment_reasons=tuple(adjustment_reasons),
        )
