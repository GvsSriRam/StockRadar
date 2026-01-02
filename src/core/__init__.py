"""Core module - interfaces, models, and exceptions"""

from .interfaces import DataCollector, BaseAnalyzer, BaseScorer, BaseFormatter
from .models import (
    RiskLevel,
    Severity,
    Filing8K,
    InsiderTransaction,
    SECFilingData,
    RedFlag,
    InsiderPattern,
    InsiderSummary,
    AnalysisResult,
    ScoringResult,
    RiskReport,
)
from .exceptions import (
    StockRadarError,
    CollectorError,
    AnalyzerError,
    WebhookError,
)

__all__ = [
    # Interfaces
    "DataCollector",
    "BaseAnalyzer",
    "BaseScorer",
    "BaseFormatter",
    # Models
    "RiskLevel",
    "Severity",
    "Filing8K",
    "InsiderTransaction",
    "SECFilingData",
    "RedFlag",
    "InsiderPattern",
    "InsiderSummary",
    "AnalysisResult",
    "ScoringResult",
    "RiskReport",
    # Exceptions
    "StockRadarError",
    "CollectorError",
    "AnalyzerError",
    "WebhookError",
]