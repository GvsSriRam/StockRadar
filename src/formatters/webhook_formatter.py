"""
Webhook Output Formatter

Formats risk analysis results as webhook payloads for notifications.
"""

from datetime import datetime, timezone

from ..core.models import RiskReport, RiskLevel


class WebhookFormatter:
    """
    Formats results as webhook payloads.

    Output is suitable for:
    - Discord webhooks
    - Slack webhooks
    - Custom alert endpoints
    """

    RISK_INDICATORS = {
        RiskLevel.LOW: "",
        RiskLevel.MODERATE: "",
        RiskLevel.ELEVATED: "",
        RiskLevel.HIGH: "",
    }

    def format_generic_payload(self, report: RiskReport) -> dict:
        """
        Format as generic JSON webhook payload.

        Args:
            report: RiskReport to format

        Returns:
            Dictionary for webhook POST
        """
        indicator = self.RISK_INDICATORS.get(report.risk_level, "")

        top_flag = report.red_flags[0] if report.red_flags else None

        return {
            "alert_type": "risk_signal",
            "ticker": report.ticker,
            "risk_score": report.risk_score,
            "risk_level": report.risk_level.value,
            "title": f"{indicator} Risk Alert: {report.ticker} - Score {report.risk_score}",
            "message": report.explanation or f"{report.ticker} triggered a risk alert",
            "top_signal": {
                "type": top_flag.type,
                "title": top_flag.title,
            } if top_flag else None,
            "red_flags_count": report.red_flags_count,
            "insider_summary": {
                "net_activity": report.insider_summary.net_activity,
                "total_sold": report.insider_summary.total_sold,
                "total_bought": report.insider_summary.total_bought,
            },
            "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        }

    def format_discord_embed(self, report: RiskReport) -> dict:
        """
        Format as Discord webhook embed.

        Args:
            report: RiskReport to format

        Returns:
            Dictionary with Discord embed structure
        """
        indicator = self.RISK_INDICATORS.get(report.risk_level, "")

        # Discord embed colors
        color_map = {
            RiskLevel.LOW: 0x00FF00,      # Green
            RiskLevel.MODERATE: 0xFFFF00,  # Yellow
            RiskLevel.ELEVATED: 0xFFA500,  # Orange
            RiskLevel.HIGH: 0xFF0000,      # Red
        }

        fields = [
            {
                "name": "Risk Score",
                "value": f"{report.risk_score}/100",
                "inline": True
            },
            {
                "name": "Level",
                "value": report.risk_level.value.upper(),
                "inline": True
            },
            {
                "name": "Red Flags",
                "value": str(report.red_flags_count),
                "inline": True
            },
        ]

        if report.red_flags:
            top_flags = "\n".join([f"- {f.title}" for f in report.red_flags[:3]])
            fields.append({
                "name": "Top Signals",
                "value": top_flags,
                "inline": False
            })

        if report.explanation:
            fields.append({
                "name": "Analysis",
                "value": report.explanation[:1000],
                "inline": False
            })

        return {
            "embeds": [
                {
                    "title": f"{indicator} Signal Alert: {report.ticker}",
                    "color": color_map.get(report.risk_level, 0x808080),
                    "fields": fields,
                    "timestamp": report.analyzed_at.isoformat(),
                    "footer": {
                        "text": "SEC Filing Risk Scanner"
                    }
                }
            ]
        }

    def format_slack_blocks(self, report: RiskReport) -> dict:
        """
        Format as Slack webhook blocks.

        Args:
            report: RiskReport to format

        Returns:
            Dictionary with Slack blocks structure
        """
        indicator = self.RISK_INDICATORS.get(report.risk_level, "")

        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"{indicator} Risk Alert: {report.ticker}",
                    "emoji": True
                }
            },
            {
                "type": "section",
                "fields": [
                    {
                        "type": "mrkdwn",
                        "text": f"*Risk Score:*\n{report.risk_score}/100"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Level:*\n{report.risk_level.value.upper()}"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Red Flags:*\n{report.red_flags_count}"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Insider Activity:*\n{report.insider_summary.net_activity}"
                    }
                ]
            }
        ]

        if report.explanation:
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Analysis:*\n{report.explanation[:500]}"
                }
            })

        blocks.append({
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": f"Analyzed: {report.analyzed_at.strftime('%Y-%m-%d %H:%M')} UTC"
                }
            ]
        })

        return {"blocks": blocks}
