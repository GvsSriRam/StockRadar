"""
Markdown Output Formatter

Formats risk analysis results as human-readable Markdown reports.
"""

from datetime import datetime, timezone

from ..core.models import (
    SECFilingData,
    AnalysisResult,
    ScoringResult,
    RiskReport,
    RiskLevel,
    Severity,
)


class MarkdownFormatter:
    """
    Formats results as Markdown reports.

    Output is suitable for:
    - Human readability
    - Documentation
    - Discord/Slack formatting
    """

    RISK_INDICATORS = {
        RiskLevel.LOW: ("Low", ""),
        RiskLevel.MODERATE: ("Moderate", ""),
        RiskLevel.ELEVATED: ("Elevated", ""),
        RiskLevel.HIGH: ("High", ""),
    }

    SEVERITY_ICONS = {
        Severity.HIGH: "",
        Severity.MEDIUM: "",
        Severity.LOW: "",
    }

    def format_report(self, report: RiskReport) -> str:
        """
        Format RiskReport as Markdown.

        Args:
            report: RiskReport to format

        Returns:
            Markdown formatted string
        """
        level_name, indicator = self.RISK_INDICATORS.get(
            report.risk_level,
            ("Unknown", "")
        )

        lines = [
            f"# Risk Report: {report.ticker}",
            "",
            f"**Risk Score: {report.risk_score}/100 ({level_name.upper()})** {indicator}",
            "",
        ]

        # Red flags section
        if report.red_flags:
            lines.extend(self._format_red_flags_section(report))

        # Insider activity section
        lines.extend(self._format_insider_section(report))

        # AI Analysis section
        if report.explanation:
            lines.extend([
                "## Analysis",
                "",
                report.explanation,
                "",
            ])

        # Evidence links
        if report.evidence_links:
            lines.extend(self._format_evidence_section(report))

        # Footer
        lines.extend([
            "---",
            f"*Analyzed: {report.analyzed_at.strftime('%Y-%m-%d %H:%M')} UTC*",
        ])

        return "\n".join(lines)

    def _format_red_flags_section(self, report: RiskReport) -> list[str]:
        """Format red flags section"""
        lines = [
            "## Red Flags Detected",
            "",
        ]

        for flag in report.red_flags:
            icon = self.SEVERITY_ICONS.get(flag.severity, "")
            lines.append(f"- {icon} **{flag.title}**")
            if flag.details:
                lines.append(f"  - {flag.details}")

        lines.append("")
        return lines

    def _format_insider_section(self, report: RiskReport) -> list[str]:
        """Format insider activity section"""
        summary = report.insider_summary

        # Skip if no activity
        if (summary.total_sold == 0 and
            summary.total_bought == 0 and
            summary.insiders_selling == 0 and
            summary.insiders_buying == 0):
            return []

        lines = [
            "## Insider Activity",
            "",
        ]

        net_display = {
            "net_selling": "Selling",
            "net_buying": "Buying",
            "neutral": "Neutral"
        }
        lines.append(f"- **Net Activity**: {net_display.get(summary.net_activity, summary.net_activity)}")

        if summary.total_sold > 0:
            lines.append(f"- **Total Sold**: ${summary.total_sold:,}")

        if summary.total_bought > 0:
            lines.append(f"- **Total Bought**: ${summary.total_bought:,}")

        if summary.insiders_selling > 0:
            lines.append(f"- **Insiders Selling**: {summary.insiders_selling}")

        if summary.insiders_buying > 0:
            lines.append(f"- **Insiders Buying**: {summary.insiders_buying}")

        lines.append("")
        return lines

    def _format_evidence_section(self, report: RiskReport) -> list[str]:
        """Format evidence links section"""
        lines = [
            "## Evidence Links",
            "",
        ]

        for link in report.evidence_links[:5]:
            lines.append(f"- [{link}]({link})")

        lines.append("")
        return lines

    def format_summary_table(self, reports: list[RiskReport]) -> str:
        """
        Format multiple reports as a summary table.

        Args:
            reports: List of RiskReports

        Returns:
            Markdown table
        """
        if not reports:
            return "No results to display."

        lines = [
            "| Ticker | Risk Score | Level | Red Flags | Insider Activity |",
            "|--------|------------|-------|-----------|------------------|",
        ]

        sorted_reports = sorted(
            reports,
            key=lambda r: r.risk_score,
            reverse=True
        )

        net_display = {
            "net_selling": "Selling",
            "net_buying": "Buying",
            "neutral": "-"
        }

        for r in sorted_reports:
            level_name = r.risk_level.value.capitalize()
            net = net_display.get(r.insider_summary.net_activity, "-")

            lines.append(
                f"| {r.ticker} | {r.risk_score} | {level_name} | "
                f"{r.red_flags_count} | {net} |"
            )

        return "\n".join(lines)
