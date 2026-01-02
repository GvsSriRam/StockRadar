"""
Data models for SEC Filing Risk Scanner

Uses dataclasses for immutable, type-safe data structures.
These models represent the domain entities and value objects.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class RiskLevel(str, Enum):
    """
    Risk level classification.

    Note: Uses "MODERATE" instead of "neutral" (as in SCORING-ENGINE.md)
    because "moderate" is clearer for users understanding risk levels.
    """
    LOW = "low"           # 0-29: No significant concerns
    MODERATE = "moderate"  # 30-49: Some signals worth monitoring
    ELEVATED = "elevated"  # 50-69: Notable risk signals present
    HIGH = "high"          # 70-100: Significant risk indicators

    @classmethod
    def from_score(cls, score: int) -> "RiskLevel":
        """Determine risk level from numeric score"""
        if score < 30:
            return cls.LOW
        elif score < 50:
            return cls.MODERATE
        elif score < 70:
            return cls.ELEVATED
        else:
            return cls.HIGH


class TransactionType(str, Enum):
    """Insider transaction types"""
    PURCHASE = "P"
    SALE = "S"
    GRANT = "A"
    DISPOSITION = "D"
    TAX_WITHHOLDING = "F"
    OPTION_EXERCISE = "M"
    GIFT = "G"
    CONVERSION = "C"
    OTHER = "J"

    @property
    def description(self) -> str:
        """Human-readable description"""
        descriptions = {
            "P": "Purchase",
            "S": "Sale",
            "A": "Grant/Award",
            "D": "Sale to issuer",
            "F": "Tax withholding",
            "M": "Option exercise",
            "G": "Gift",
            "C": "Conversion",
            "J": "Other acquisition",
        }
        return descriptions.get(self.value, f"Other ({self.value})")


class Severity(str, Enum):
    """Signal severity levels"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


@dataclass(frozen=True)
class Filing8K:
    """Represents an SEC 8-K filing"""
    date: str
    form_type: str
    title: str
    url: Optional[str] = None
    content_snippet: Optional[str] = None
    items: tuple[str, ...] = field(default_factory=tuple)

    def has_critical_item(self) -> bool:
        """Check if filing contains critical items (4.01 or 4.02)"""
        critical_items = ("4.01", "4.02")
        return any(
            any(critical in item for critical in critical_items)
            for item in self.items
        )


@dataclass(frozen=True)
class InsiderTransaction:
    """Represents a Form 4 insider transaction"""
    date: str
    insider_name: str
    insider_title: str
    transaction_type: str
    shares: int
    price: Optional[float] = None
    total_value: Optional[int] = None
    url: Optional[str] = None
    is_director: bool = False
    is_officer: bool = False

    @property
    def is_sale(self) -> bool:
        return self.transaction_type == "S"

    @property
    def is_purchase(self) -> bool:
        return self.transaction_type == "P"

    @property
    def transaction_description(self) -> str:
        """Get human-readable transaction description"""
        try:
            return TransactionType(self.transaction_type).description
        except ValueError:
            return f"Other ({self.transaction_type})"


@dataclass(frozen=True)
class SECFilingData:
    """Container for all SEC data collected for a ticker"""
    ticker: str
    cik: Optional[str]
    filings_8k: tuple[Filing8K, ...]
    filings_form4: tuple[InsiderTransaction, ...]
    collected_at: datetime
    lookback_days: int
    error: Optional[str] = None

    @property
    def has_data(self) -> bool:
        return bool(self.filings_8k or self.filings_form4)

    @property
    def total_filings(self) -> int:
        return len(self.filings_8k) + len(self.filings_form4)


@dataclass(frozen=True)
class RedFlag:
    """A detected red flag signal"""
    type: str
    title: str
    severity: Severity
    details: Optional[str] = None
    evidence_url: Optional[str] = None
    filing_date: Optional[str] = None


@dataclass(frozen=True)
class InsiderPattern:
    """A detected insider trading pattern"""
    type: str
    title: str
    severity: Severity
    details: Optional[str] = None
    evidence_url: Optional[str] = None


@dataclass(frozen=True)
class InsiderSummary:
    """Summary of insider trading activity"""
    net_activity: str  # "net_selling", "net_buying", "neutral"
    total_sold: int
    total_bought: int
    insiders_selling: int
    insiders_buying: int


@dataclass(frozen=True)
class AnalysisResult:
    """Result from risk analyzer"""
    red_flags: tuple[RedFlag, ...]
    insider_patterns: tuple[InsiderPattern, ...]
    insider_summary: InsiderSummary
    risk_score: int
    risk_level: RiskLevel
    reasoning: str
    explanation: Optional[str] = None


@dataclass(frozen=True)
class ScoringResult:
    """Result from risk scorer"""
    risk_score: int
    risk_level: RiskLevel
    base_score: int
    adjustments: int
    adjustment_reasons: tuple[str, ...]


@dataclass(frozen=True)
class RiskReport:
    """Complete risk report for a ticker"""
    ticker: str
    risk_score: int
    risk_level: RiskLevel
    red_flags: tuple[RedFlag, ...]
    red_flags_count: int
    insider_patterns: tuple[InsiderPattern, ...]
    insider_summary: InsiderSummary
    explanation: Optional[str]
    reasoning: str
    evidence_links: tuple[str, ...]
    filings_analyzed: dict
    scoring_details: dict
    analyzed_at: datetime
    lookback_days: int

    def exceeds_threshold(self, threshold: int) -> bool:
        """Check if risk score exceeds alert threshold"""
        return self.risk_score >= threshold
