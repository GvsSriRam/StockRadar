"""Custom exceptions for SEC Filing Risk Scanner"""


class StockRadarError(Exception):
    """Base exception for all Stock Radar errors"""

    def __init__(self, message: str, details: dict | None = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}


class CollectorError(StockRadarError):
    """Base exception for data collection errors"""
    pass


class TickerNotFoundError(CollectorError):
    """Raised when a ticker symbol cannot be resolved"""

    def __init__(self, ticker: str):
        super().__init__(f"Ticker '{ticker}' not found", details={"ticker": ticker})
        self.ticker = ticker


class SECRateLimitError(CollectorError):
    """Raised when SEC rate limit is exceeded"""

    def __init__(self, retry_after: int | None = None):
        message = "SEC rate limit exceeded"
        if retry_after:
            message += f", retry after {retry_after}s"
        super().__init__(message, details={"retry_after": retry_after})
        self.retry_after = retry_after


class SECFetchError(CollectorError):
    """Raised when fetching SEC data fails"""

    def __init__(self, url: str, status_code: int | None = None, reason: str | None = None):
        message = f"Failed to fetch SEC data from {url}"
        if status_code:
            message += f" (HTTP {status_code})"
        super().__init__(message, details={"url": url, "status_code": status_code})


class AnalyzerError(StockRadarError):
    """Base exception for analysis errors"""
    pass


class LLMRateLimitError(AnalyzerError):
    """Raised when LLM rate limit is exceeded"""

    def __init__(self, provider: str, retry_after: int | None = None):
        message = f"LLM rate limit exceeded ({provider})"
        if retry_after:
            message += f", retry after {retry_after}s"
        super().__init__(message, details={"provider": provider, "retry_after": retry_after})


class WebhookError(StockRadarError):
    """Raised when webhook delivery fails"""

    def __init__(self, url: str, status_code: int | None = None, reason: str | None = None):
        message = f"Webhook delivery failed to {url}"
        if status_code:
            message += f" (HTTP {status_code})"
        super().__init__(message, details={"url": url, "status_code": status_code})