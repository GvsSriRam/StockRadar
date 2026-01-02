"""
Core interfaces for SEC Filing Risk Scanner.

Defines abstract base classes that implementations must follow.
"""

from abc import ABC, abstractmethod

from .models import SECFilingData, AnalysisResult, ScoringResult, RiskReport


class DataCollector(ABC):
    """Abstract base class for data collectors"""

    @abstractmethod
    async def collect(self, ticker: str, lookback_days: int = 30) -> SECFilingData:
        """Collect data for a ticker"""
        pass


class BaseAnalyzer(ABC):
    """Abstract base class for risk analyzers"""

    @abstractmethod
    async def analyze(
        self,
        data: SECFilingData,
        include_explanation: bool = True
    ) -> AnalysisResult:
        """Analyze data for risk signals"""
        pass

    @abstractmethod
    def get_provider_name(self) -> str:
        """Return the name of the analysis provider"""
        pass


class BaseScorer(ABC):
    """Abstract base class for risk scorers"""

    @abstractmethod
    def score(
        self,
        analysis: AnalysisResult,
        data: SECFilingData | None = None
    ) -> ScoringResult:
        """Calculate risk score"""
        pass

    @abstractmethod
    def get_scoring_method(self) -> str:
        """Return the name of the scoring method"""
        pass


class BaseFormatter(ABC):
    """Abstract base class for output formatters"""

    @abstractmethod
    def format(
        self,
        ticker: str,
        data: SECFilingData,
        analysis: AnalysisResult,
        scoring: ScoringResult,
    ) -> RiskReport:
        """Format results into a risk report"""
        pass

    @abstractmethod
    def get_format_type(self) -> str:
        """Return the output format type"""
        pass