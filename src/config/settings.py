"""
Application settings and configuration management.

Provides centralized configuration with environment variable support
and sensible defaults. Uses a singleton pattern for efficiency.
"""

import os
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Optional


@dataclass(frozen=True)
class SECSettings:
    """SEC EDGAR API settings"""
    base_url: str = "https://www.sec.gov"
    company_tickers_url: str = "https://www.sec.gov/files/company_tickers.json"
    user_agent: str = "SEC-Filing-Risk-Scanner/1.0 (contact@example.com)"
    request_delay: float = 0.15  # 10 requests/second max
    timeout: int = 30
    max_retries: int = 3


@dataclass(frozen=True)
class LLMSettings:
    """LLM provider settings"""
    provider: str = "groq"
    model: str = "llama-3.3-70b-versatile"
    api_key: Optional[str] = None
    temperature: float = 0.1
    max_tokens: int = 1000
    timeout: int = 30
    max_retries: int = 2

    @property
    def is_configured(self) -> bool:
        """Check if LLM is properly configured"""
        return bool(self.api_key)


@dataclass(frozen=True)
class ScoringSettings:
    """Scoring engine settings"""
    # Base thresholds
    low_threshold: int = 30
    moderate_threshold: int = 50
    elevated_threshold: int = 70

    # Rule-based adjustments
    auditor_change_penalty: int = 15
    financial_restatement_penalty: int = 20
    multiple_flags_penalty: int = 10
    multiple_flags_threshold: int = 3
    insider_combo_penalty: int = 5
    high_severity_pattern_penalty: int = 10
    high_severity_pattern_threshold: int = 2


@dataclass(frozen=True)
class WebhookSettings:
    """Webhook notification settings"""
    timeout: int = 10
    max_retries: int = 2
    default_threshold: int = 70


@dataclass(frozen=True)
class ActorSettings:
    """Apify Actor settings"""
    max_tickers: int = 20
    default_lookback_days: int = 30
    min_lookback_days: int = 7
    max_lookback_days: int = 90
    default_batch_size: int = 50
    min_batch_size: int = 10
    max_batch_size: int = 100


@dataclass(frozen=True)
class StockUniverseSettings:
    """Stock universe (S&P 500, NASDAQ 100) settings"""
    sp500_url: str = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
    nasdaq100_url: str = "https://en.wikipedia.org/wiki/Nasdaq-100"
    user_agent: str = "StockRadar/1.0 (stock-risk-scanner@apify.com)"
    request_delay: float = 0.5  # Wikipedia is less strict than SEC
    timeout: int = 30
    cache_ttl_hours: int = 24  # Cache ticker lists for 24 hours


@dataclass
class Settings:
    """
    Main application settings container.

    Aggregates all component settings and provides
    environment variable overrides.
    """
    sec: SECSettings = field(default_factory=SECSettings)
    llm: LLMSettings = field(default_factory=LLMSettings)
    scoring: ScoringSettings = field(default_factory=ScoringSettings)
    webhook: WebhookSettings = field(default_factory=WebhookSettings)
    actor: ActorSettings = field(default_factory=ActorSettings)
    stock_universe: StockUniverseSettings = field(default_factory=StockUniverseSettings)

    # Runtime flags
    debug: bool = False

    @classmethod
    def from_environment(cls) -> "Settings":
        """
        Create settings from environment variables.

        Environment variables:
            GROQ_API_KEY: LLM API key
            SEC_USER_AGENT: Custom SEC user agent
            DEBUG: Enable debug mode
        """
        groq_api_key = os.environ.get("GROQ_API_KEY")
        sec_user_agent = os.environ.get(
            "SEC_USER_AGENT",
            SECSettings.user_agent
        )
        debug = os.environ.get("DEBUG", "").lower() in ("true", "1", "yes")

        return cls(
            sec=SECSettings(user_agent=sec_user_agent),
            llm=LLMSettings(api_key=groq_api_key),
            scoring=ScoringSettings(),
            webhook=WebhookSettings(),
            actor=ActorSettings(),
            stock_universe=StockUniverseSettings(),
            debug=debug,
        )

    def with_llm_key(self, api_key: str) -> "Settings":
        """Create new settings with updated LLM API key"""
        return Settings(
            sec=self.sec,
            llm=LLMSettings(
                provider=self.llm.provider,
                model=self.llm.model,
                api_key=api_key,
                temperature=self.llm.temperature,
                max_tokens=self.llm.max_tokens,
                timeout=self.llm.timeout,
                max_retries=self.llm.max_retries,
            ),
            scoring=self.scoring,
            webhook=self.webhook,
            actor=self.actor,
            stock_universe=self.stock_universe,
            debug=self.debug,
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """
    Get application settings (singleton).

    Returns cached settings instance loaded from environment.
    """
    return Settings.from_environment()


def reset_settings() -> None:
    """Clear cached settings (useful for testing)"""
    get_settings.cache_clear()
