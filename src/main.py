"""
SEC Filing Risk Scanner - Apify Actor Entry Point

Main entry point for the Apify Actor that analyzes SEC filings for risk signals.
"""

import asyncio
import logging

from apify import Actor

from .config import get_settings
from .collectors import StockUniverseCollector
from .services import RiskScannerService, WebhookService, IncrementalScanner
from .formatters.json_formatter import JsonFormatter


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger(__name__)


async def main():
    """Main Actor entry point"""
    async with Actor:
        # Get input
        actor_input = await Actor.get_input() or {}

        # Extract parameters
        scan_mode = actor_input.get("scanMode", "custom")
        custom_tickers = actor_input.get("tickers", [])
        batch_size = actor_input.get("batchSize", 50)
        incremental_mode = actor_input.get("incrementalMode", True)
        lookback_days = actor_input.get("lookbackDays", 30)
        include_explanation = actor_input.get("includeExplanation", True)
        alert_threshold = actor_input.get("alertThreshold", 70)
        webhook_url = actor_input.get("webhookUrl")

        settings = get_settings()

        # Clamp batch_size to valid range
        batch_size = max(
            settings.actor.min_batch_size,
            min(batch_size, settings.actor.max_batch_size)
        )

        # Clamp lookback_days to valid range
        original_lookback = lookback_days
        lookback_days = max(
            settings.actor.min_lookback_days,
            min(lookback_days, settings.actor.max_lookback_days)
        )
        if lookback_days != original_lookback:
            Actor.log.warning(
                f"lookbackDays clamped from {original_lookback} to {lookback_days} "
                f"(valid range: {settings.actor.min_lookback_days}-{settings.actor.max_lookback_days})"
            )

        # Check LLM configuration
        if not settings.llm.is_configured:
            Actor.log.error("GROQ_API_KEY is required. Set it in Actor environment variables.")
            raise RuntimeError("GROQ_API_KEY is required")

        # Get tickers based on scan mode
        universe_collector = None
        if scan_mode == "custom":
            if not custom_tickers:
                Actor.log.error("No tickers provided. Please specify at least one ticker for custom mode.")
                return
            tickers = [t.upper().strip() for t in custom_tickers]

            # Apply max_tickers limit for custom mode
            max_tickers = settings.actor.max_tickers
            if len(tickers) > max_tickers:
                Actor.log.warning(f"Too many tickers ({len(tickers)}). Processing first {max_tickers}.")
                tickers = tickers[:max_tickers]
        else:
            # Fetch from StockUniverseCollector
            universe_collector = StockUniverseCollector(settings)
            try:
                tickers = await universe_collector.get_tickers(scan_mode)
                Actor.log.info(f"Fetched {len(tickers)} tickers for {scan_mode} mode")
            except Exception as e:
                Actor.log.error(f"Failed to fetch ticker list for {scan_mode}: {e}")
                return
            finally:
                await universe_collector.close()

        Actor.log.info(f"Starting SEC risk analysis for {len(tickers)} ticker(s)")
        Actor.log.info(f"Scan mode: {scan_mode}, Lookback: {lookback_days} days, Include explanation: {include_explanation}")

        # Determine if we should use incremental scanning
        use_incremental = incremental_mode and scan_mode != "custom"
        if use_incremental:
            Actor.log.info("Incremental mode enabled - skipping stocks with no new filings")

        # Initialize services
        scanner = RiskScannerService(settings=settings)
        incremental_scanner = IncrementalScanner(scanner=scanner, settings=settings) if use_incremental else None
        webhook_service = WebhookService(settings=settings)
        formatter = JsonFormatter()

        # Process tickers
        all_results = []
        scan_stats = None

        try:
            if use_incremental:
                # Incremental scan for index modes (sp500/nasdaq100)
                Actor.log.info("Running incremental scan...")
                all_results, scan_stats = await incremental_scanner.scan_incremental(
                    tickers,
                    lookback_days=lookback_days,
                    include_explanation=include_explanation,
                )
                Actor.log.info(f"Incremental scan: {scan_stats}")

            elif scan_mode == "custom" or len(tickers) <= batch_size:
                # Small scan: process all at once
                all_results = await scanner.scan_multiple(
                    tickers,
                    lookback_days=lookback_days,
                    include_explanation=include_explanation,
                )
            else:
                # Large scan without incremental: process in batches
                total_batches = (len(tickers) + batch_size - 1) // batch_size
                Actor.log.info(f"Processing {len(tickers)} tickers in {total_batches} batches (batch size: {batch_size})")

                for batch_num, i in enumerate(range(0, len(tickers), batch_size), 1):
                    batch = tickers[i:i + batch_size]
                    Actor.log.info(f"Processing batch {batch_num}/{total_batches} ({len(batch)} tickers)")

                    batch_results = await scanner.scan_multiple(
                        batch,
                        lookback_days=lookback_days,
                        include_explanation=include_explanation,
                    )
                    all_results.extend(batch_results)

                    # Report progress
                    processed = min(i + batch_size, len(tickers))
                    Actor.log.info(f"Progress: {processed}/{len(tickers)} stocks processed")

        finally:
            # Clean up incremental scanner resources
            if incremental_scanner:
                await incremental_scanner.close()

        # Push results to dataset
        for result in all_results:
            if result.success and result.report:
                # Format and push successful result
                report_dict = formatter.to_dict(result.report)
                await Actor.push_data(report_dict)

                Actor.log.info(
                    f"{result.ticker}: Risk Score {result.report.risk_score}/100 "
                    f"({result.report.risk_level.value})"
                )

                # Send webhook if threshold exceeded
                if webhook_url and webhook_service.should_alert(result.report, alert_threshold):
                    Actor.log.info(f"Sending webhook alert for {result.ticker}")
                    try:
                        await webhook_service.send_alert(webhook_url, result.report)
                        Actor.log.info(f"Webhook sent successfully for {result.ticker}")
                    except Exception as e:
                        Actor.log.warning(f"Webhook failed for {result.ticker}: {e}")

            else:
                # Push error result
                error_data = {
                    "ticker": result.ticker,
                    "risk_score": None,
                    "risk_level": None,
                    "error": result.error,
                    "analyzed_at": None,
                }
                await Actor.push_data(error_data)
                Actor.log.error(f"{result.ticker}: {result.error}")

        # Log summary
        summary = scanner.get_summary(all_results)

        Actor.log.info("=" * 50)
        Actor.log.info("ANALYSIS COMPLETE")
        Actor.log.info("=" * 50)
        Actor.log.info(f"Scan mode: {scan_mode}")

        if scan_stats:
            # Incremental scan summary
            Actor.log.info(f"Total tickers: {scan_stats.total}")
            Actor.log.info(f"Scanned: {scan_stats.scanned} (new/changed filings)")
            Actor.log.info(f"Skipped: {scan_stats.skipped} (no new filings)")
            if scan_stats.reasons:
                Actor.log.info(f"Skip reasons: {scan_stats.reasons}")
        else:
            Actor.log.info(f"Processed: {summary['total']} tickers")

        Actor.log.info(f"Successful: {summary['successful']}")
        Actor.log.info(f"Failed: {summary['failed']}")

        if summary['high_risk_count'] > 0:
            Actor.log.warning(
                f"{summary['high_risk_count']} ticker(s) with HIGH risk: "
                f"{', '.join(summary['high_risk_tickers'])}"
            )

        if summary['elevated_count'] > 0:
            Actor.log.info(
                f"{summary['elevated_count']} ticker(s) with ELEVATED risk: "
                f"{', '.join(summary['elevated_tickers'])}"
            )

        # Store summary in key-value store
        default_kv = await Actor.open_key_value_store()
        summary_data = {
            **summary,
            "scan_mode": scan_mode,
            "batch_size": batch_size if scan_mode != "custom" else None,
            "incremental_mode": use_incremental,
        }
        if scan_stats:
            summary_data["incremental_stats"] = {
                "total": scan_stats.total,
                "scanned": scan_stats.scanned,
                "skipped": scan_stats.skipped,
                "skip_reasons": scan_stats.reasons,
            }
        await default_kv.set_value("summary", summary_data)

        Actor.log.info("Results saved to dataset. Summary saved to key-value store.")


if __name__ == "__main__":
    asyncio.run(main())