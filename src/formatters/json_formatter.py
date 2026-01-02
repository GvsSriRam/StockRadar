"""
JSON Output Formatter

Formats risk analysis results as structured JSON for API consumers.
"""

from datetime import datetime, timezone

from ..core.interfaces import BaseFormatter
from ..core.models import (
    SECFilingData,
    AnalysisResult,
    ScoringResult,
    RiskReport,
)


class JsonFormatter(BaseFormatter):
    """
    Formats results as structured JSON.

    Output is suitable for:
    - Apify dataset storage
    - API responses
    - Downstream data processing
    """

    def get_format_type(self) -> str:
        return "JSON"

    def format(
        self,
        ticker: str,
        data: SECFilingData,
        analysis: AnalysisResult,
        scoring: ScoringResult,
    ) -> RiskReport:
        """
        Create a complete RiskReport from analysis results.

        Args:
            ticker: Stock ticker symbol
            data: Raw SEC data
            analysis: Analysis result
            scoring: Scoring result

        Returns:
            RiskReport with all details
        """
        evidence_links = self._collect_evidence_links(data, analysis)

        return RiskReport(
            ticker=ticker,
            risk_score=scoring.risk_score,
            risk_level=scoring.risk_level,
            red_flags=analysis.red_flags,
            red_flags_count=len(analysis.red_flags),
            insider_patterns=analysis.insider_patterns,
            insider_summary=analysis.insider_summary,
            explanation=analysis.explanation,
            reasoning=analysis.reasoning,
            evidence_links=evidence_links,
            filings_analyzed={
                "8k_count": len(data.filings_8k),
                "form4_count": len(data.filings_form4),
            },
            scoring_details={
                "base_score": scoring.base_score,
                "adjustments": scoring.adjustments,
                "adjustment_reasons": list(scoring.adjustment_reasons),
            },
            analyzed_at=datetime.now(timezone.utc),
            lookback_days=data.lookback_days,
        )

    def to_dict(self, report: RiskReport) -> dict:
        """
        Convert RiskReport to dictionary for serialization.

        Args:
            report: RiskReport to convert

        Returns:
            Dictionary representation
        """
        return {
            "ticker": report.ticker,
            "risk_score": report.risk_score,
            "risk_level": report.risk_level.value,
            "red_flags": [
                {
                    "type": f.type,
                    "title": f.title,
                    "severity": f.severity.value,
                    "details": f.details,
                    "evidence_url": f.evidence_url,
                    "filing_date": f.filing_date,
                }
                for f in report.red_flags
            ],
            "red_flags_count": report.red_flags_count,
            "insider_patterns": [
                {
                    "type": p.type,
                    "title": p.title,
                    "severity": p.severity.value,
                    "details": p.details,
                    "evidence_url": p.evidence_url,
                }
                for p in report.insider_patterns
            ],
            "insider_summary": {
                "net_activity": report.insider_summary.net_activity,
                "total_sold": report.insider_summary.total_sold,
                "total_bought": report.insider_summary.total_bought,
                "insiders_selling": report.insider_summary.insiders_selling,
                "insiders_buying": report.insider_summary.insiders_buying,
            },
            "explanation": report.explanation,
            "reasoning": report.reasoning,
            "evidence_links": list(report.evidence_links),
            "filings_analyzed": report.filings_analyzed,
            "scoring_details": report.scoring_details,
            "analyzed_at": report.analyzed_at.isoformat().replace("+00:00", "Z"),
            "lookback_days": report.lookback_days,
        }

    def _collect_evidence_links(
        self,
        data: SECFilingData,
        analysis: AnalysisResult
    ) -> tuple[str, ...]:
        """Collect all unique evidence URLs"""
        links = set()

        for filing in data.filings_8k:
            if filing.url:
                links.add(filing.url)

        for txn in data.filings_form4:
            if txn.url:
                links.add(txn.url)

        for flag in analysis.red_flags:
            if flag.evidence_url:
                links.add(flag.evidence_url)

        for pattern in analysis.insider_patterns:
            if pattern.evidence_url:
                links.add(pattern.evidence_url)

        return tuple(sorted(links))
