"""
Webhook Service

Handles sending notifications to webhook endpoints.
"""

import asyncio
from typing import Optional

import httpx

from ..config import Settings, get_settings
from ..core.models import RiskReport
from ..core.exceptions import WebhookError
from ..formatters.webhook_formatter import WebhookFormatter


class WebhookService:
    """
    Service for sending webhook notifications.

    Supports multiple webhook formats:
    - Generic JSON
    - Discord embeds
    - Slack blocks
    """

    def __init__(self, settings: Optional[Settings] = None):
        """
        Initialize webhook service.

        Args:
            settings: Application settings
        """
        self._settings = settings or get_settings()
        self._formatter = WebhookFormatter()

    async def send_alert(
        self,
        url: str,
        report: RiskReport,
        format_type: str = "generic"
    ) -> bool:
        """
        Send alert to webhook URL.

        Args:
            url: Webhook URL
            report: RiskReport to send
            format_type: "generic", "discord", or "slack"

        Returns:
            True if successful

        Raises:
            WebhookError: If delivery fails
        """
        payload = self._format_payload(report, format_type)

        for attempt in range(self._settings.webhook.max_retries + 1):
            try:
                async with httpx.AsyncClient() as client:
                    response = await client.post(
                        url,
                        json=payload,
                        timeout=self._settings.webhook.timeout,
                        headers={"Content-Type": "application/json"},
                    )

                    if response.status_code < 400:
                        return True

                    if response.status_code >= 500 and attempt < self._settings.webhook.max_retries:
                        await asyncio.sleep(2 ** attempt)
                        continue

                    raise WebhookError(
                        url=url,
                        status_code=response.status_code,
                        reason=response.text[:200]
                    )

            except httpx.TimeoutException:
                if attempt < self._settings.webhook.max_retries:
                    await asyncio.sleep(2 ** attempt)
                    continue
                raise WebhookError(url=url, reason="Timeout")

            except WebhookError:
                raise

            except Exception as e:
                raise WebhookError(url=url, reason=str(e))

        return False

    def _format_payload(self, report: RiskReport, format_type: str) -> dict:
        """Format report for webhook"""
        if format_type == "discord":
            return self._formatter.format_discord_embed(report)
        elif format_type == "slack":
            return self._formatter.format_slack_blocks(report)
        else:
            return self._formatter.format_generic_payload(report)

    def should_alert(self, report: RiskReport, threshold: Optional[int] = None) -> bool:
        """
        Check if report should trigger an alert.

        Args:
            report: RiskReport to check
            threshold: Override threshold (uses default if not provided)

        Returns:
            True if score exceeds threshold
        """
        threshold = threshold or self._settings.webhook.default_threshold
        return report.exceeds_threshold(threshold)
