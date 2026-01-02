"""
Tests for formatters module
"""

import pytest

from src.formatters.json_formatter import JsonFormatter
from src.formatters.markdown_formatter import MarkdownFormatter
from src.formatters.webhook_formatter import WebhookFormatter
from src.core.models import RiskLevel


class TestJsonFormatter:
    """Tests for JsonFormatter"""

    def test_format_creates_report(self, sample_sec_data, sample_analysis_result, sample_scoring_result):
        """Should create RiskReport from components"""
        formatter = JsonFormatter()
        report = formatter.format(
            "TEST",
            sample_sec_data,
            sample_analysis_result,
            sample_scoring_result,
        )

        assert report.ticker == "TEST"
        assert report.risk_score == sample_scoring_result.risk_score
        assert report.risk_level == sample_scoring_result.risk_level

    def test_to_dict_serialization(self, sample_risk_report):
        """Should serialize report to dictionary"""
        formatter = JsonFormatter()
        result = formatter.to_dict(sample_risk_report)

        assert result["ticker"] == "TEST"
        assert result["risk_score"] == 70
        assert result["risk_level"] == "high"
        assert "analyzed_at" in result
        assert result["analyzed_at"].endswith("Z")

    def test_evidence_links_collected(self, sample_sec_data, sample_analysis_result, sample_scoring_result):
        """Should collect evidence links from all sources"""
        formatter = JsonFormatter()
        report = formatter.format(
            "TEST",
            sample_sec_data,
            sample_analysis_result,
            sample_scoring_result,
        )

        assert len(report.evidence_links) > 0

    def test_get_format_type(self):
        """Should return JSON"""
        formatter = JsonFormatter()
        assert formatter.get_format_type() == "JSON"


class TestMarkdownFormatter:
    """Tests for MarkdownFormatter"""

    def test_format_report_structure(self, sample_risk_report):
        """Should create markdown with expected sections"""
        formatter = MarkdownFormatter()
        markdown = formatter.format_report(sample_risk_report)

        assert "# Risk Report: TEST" in markdown
        assert "Risk Score: 70/100" in markdown
        assert "HIGH" in markdown
        assert "## Red Flags Detected" in markdown
        assert "## Insider Activity" in markdown

    def test_format_report_no_red_flags(self, sample_risk_report):
        """Should skip red flags section when empty"""
        from src.core.models import RiskReport, InsiderSummary
        from datetime import datetime, timezone

        empty_flags_report = RiskReport(
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
            explanation=None,
            reasoning="No signals",
            evidence_links=tuple(),
            filings_analyzed={"8k_count": 0, "form4_count": 0},
            scoring_details={},
            analyzed_at=datetime.now(timezone.utc),
            lookback_days=30,
        )

        formatter = MarkdownFormatter()
        markdown = formatter.format_report(empty_flags_report)

        assert "## Red Flags Detected" not in markdown

    def test_format_summary_table(self, sample_risk_report):
        """Should create summary table"""
        formatter = MarkdownFormatter()
        table = formatter.format_summary_table([sample_risk_report])

        assert "| Ticker |" in table
        assert "| TEST |" in table

    def test_format_summary_table_sorted(self):
        """Should sort by risk score descending"""
        from src.core.models import RiskReport, InsiderSummary
        from datetime import datetime, timezone

        def make_report(ticker: str, score: int) -> RiskReport:
            return RiskReport(
                ticker=ticker,
                risk_score=score,
                risk_level=RiskLevel.from_score(score),
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
                explanation=None,
                reasoning="Test",
                evidence_links=tuple(),
                filings_analyzed={},
                scoring_details={},
                analyzed_at=datetime.now(timezone.utc),
                lookback_days=30,
            )

        reports = [
            make_report("LOW", 20),
            make_report("HIGH", 80),
            make_report("MED", 50),
        ]

        formatter = MarkdownFormatter()
        table = formatter.format_summary_table(reports)

        lines = table.split("\n")
        data_lines = [l for l in lines if l.startswith("| ") and "Ticker" not in l and "---" not in l]

        # HIGH should come first
        assert "HIGH" in data_lines[0]
        assert "LOW" in data_lines[-1]


class TestWebhookFormatter:
    """Tests for WebhookFormatter"""

    def test_format_generic_payload(self, sample_risk_report):
        """Should create generic webhook payload"""
        formatter = WebhookFormatter()
        payload = formatter.format_generic_payload(sample_risk_report)

        assert payload["alert_type"] == "risk_signal"
        assert payload["ticker"] == "TEST"
        assert payload["risk_score"] == 70
        assert "timestamp" in payload

    def test_format_discord_embed(self, sample_risk_report):
        """Should create Discord embed structure"""
        formatter = WebhookFormatter()
        payload = formatter.format_discord_embed(sample_risk_report)

        assert "embeds" in payload
        assert len(payload["embeds"]) == 1
        assert "title" in payload["embeds"][0]
        assert "fields" in payload["embeds"][0]

    def test_format_slack_blocks(self, sample_risk_report):
        """Should create Slack blocks structure"""
        formatter = WebhookFormatter()
        payload = formatter.format_slack_blocks(sample_risk_report)

        assert "blocks" in payload
        assert len(payload["blocks"]) > 0
