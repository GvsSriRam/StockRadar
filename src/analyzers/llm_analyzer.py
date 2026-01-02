"""
Groq LLM Analyzer

Implements risk analysis using Groq's Llama 3.3 model.
Provides intelligent red flag detection, pattern analysis, and explanations.
"""

import hashlib
import json
import logging
import re
import time
from typing import Optional

from groq import Groq
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)

logger = logging.getLogger(__name__)

from ..config import Settings, get_settings
from ..core.interfaces import BaseAnalyzer
from ..core.models import (
    SECFilingData,
    AnalysisResult,
    RedFlag,
    InsiderPattern,
    InsiderSummary,
    RiskLevel,
    Severity,
)
from ..core.exceptions import AnalyzerError, LLMRateLimitError
from .prompts import AnalysisPrompts


class GroqLLMAnalyzer(BaseAnalyzer):
    """
    LLM-powered risk analyzer using Groq.

    Features:
    - Zero-shot red flag detection
    - Insider pattern analysis
    - Risk severity scoring
    - Plain-English explanations
    - Response caching with 24-hour TTL
    """

    SYSTEM_PROMPT = (
        "You are a financial analyst specializing in SEC filing risk detection. "
        "Analyze the provided data and return ONLY valid JSON. "
        "Do not include any explanation or markdown formatting outside the JSON."
    )

    # Cache TTL in seconds (24 hours)
    CACHE_TTL_SECONDS = 24 * 60 * 60

    def __init__(self, settings: Optional[Settings] = None, api_key: Optional[str] = None):
        """
        Initialize Groq LLM Analyzer.

        Args:
            settings: Application settings
            api_key: Override API key (uses settings if not provided)

        Raises:
            ConfigurationError: If no API key is available
        """
        self._settings = settings or get_settings()

        key = api_key or self._settings.llm.api_key
        if not key:
            raise AnalyzerError("GROQ_API_KEY is required for LLM analysis")

        self._client = Groq(api_key=key)
        # Cache stores (result, timestamp) tuples for TTL support
        self._cache: dict[str, tuple[dict, float]] = {}

    def _is_cache_valid(self, cache_key: str) -> bool:
        """Check if cached entry exists and is not expired"""
        if cache_key not in self._cache:
            return False
        _, timestamp = self._cache[cache_key]
        return (time.time() - timestamp) < self.CACHE_TTL_SECONDS

    def _get_from_cache(self, cache_key: str) -> Optional[dict]:
        """Get value from cache if valid, None otherwise"""
        if self._is_cache_valid(cache_key):
            return self._cache[cache_key][0]
        # Remove expired entry
        if cache_key in self._cache:
            del self._cache[cache_key]
        return None

    def _set_cache(self, cache_key: str, value: dict) -> None:
        """Store value in cache with current timestamp"""
        self._cache[cache_key] = (value, time.time())

    def get_provider_name(self) -> str:
        return f"Groq ({self._settings.llm.model})"

    async def analyze(
        self,
        data: SECFilingData,
        include_explanation: bool = True
    ) -> AnalysisResult:
        """
        Analyze SEC data for risk signals.

        Args:
            data: SEC filing data to analyze
            include_explanation: Whether to generate plain-English explanation

        Returns:
            AnalysisResult with detected signals and scores
        """
        ticker = data.ticker

        # Detect red flags in 8-K filings
        red_flags = await self._detect_red_flags(data.filings_8k)

        # Analyze insider patterns
        insider_data = await self._analyze_insiders(ticker, data.filings_form4)
        insider_patterns = insider_data.get("patterns", [])
        insider_summary = InsiderSummary(
            net_activity=insider_data.get("net_activity", "neutral"),
            total_sold=insider_data.get("total_sold", 0),
            total_bought=insider_data.get("total_bought", 0),
            insiders_selling=insider_data.get("insiders_selling", 0),
            insiders_buying=insider_data.get("insiders_buying", 0),
        )

        # Score severity
        scoring = await self._score_severity(ticker, red_flags, insider_data)

        # Generate explanation
        explanation = None
        if include_explanation:
            explanation = await self._generate_explanation(
                ticker,
                scoring.get("risk_score", 0),
                scoring.get("risk_level", "low"),
                red_flags,
                insider_summary,
            )

        return AnalysisResult(
            red_flags=tuple(red_flags),
            insider_patterns=tuple(insider_patterns),
            insider_summary=insider_summary,
            risk_score=scoring.get("risk_score", 0),
            risk_level=RiskLevel(scoring.get("risk_level", "low")),
            reasoning=scoring.get("reasoning", ""),
            explanation=explanation,
        )

    async def _detect_red_flags(self, filings_8k: tuple) -> list[RedFlag]:
        """Detect red flags in 8-K filings"""
        all_flags = []

        for filing in filings_8k:
            content = filing.content_snippet or ""
            items = filing.items or []

            if not content and not items:
                continue

            prompt = AnalysisPrompts.RED_FLAG_DETECTION.format(
                filing_content=content[:3000] if content else "No content available",
                items="\n".join(items) if items else "No items detected",
            )

            cache_key = self._cache_key(prompt)
            result = await self._call_llm(prompt, cache_key)

            if result and "red_flags" in result:
                for flag_data in result["red_flags"]:
                    flag = RedFlag(
                        type=flag_data.get("type", "UNKNOWN"),
                        title=flag_data.get("title", "Unknown"),
                        severity=Severity(flag_data.get("severity", "medium")),
                        details=flag_data.get("details"),
                        evidence_url=filing.url,
                        filing_date=filing.date,
                    )
                    all_flags.append(flag)

        return all_flags

    async def _analyze_insiders(
        self,
        ticker: str,
        transactions: tuple
    ) -> dict:
        """Analyze insider transaction patterns"""
        if not transactions:
            return {
                "patterns": [],
                "net_activity": "neutral",
                "total_sold": 0,
                "total_bought": 0,
                "insiders_selling": 0,
                "insiders_buying": 0,
                "risk_assessment": "No insider transactions in the lookback period",
            }

        # Format transactions for LLM
        txn_text = []
        for t in transactions[:20]:
            price_str = f"${t.price:.2f}" if t.price else "N/A"
            value_str = f"${t.total_value:,}" if t.total_value else "N/A"
            txn_text.append(
                f"- {t.date}: {t.insider_name} ({t.insider_title or 'Unknown'}) "
                f"{t.transaction_description} {t.shares:,} shares @ {price_str} ({value_str})"
            )

        prompt = AnalysisPrompts.INSIDER_PATTERN_ANALYSIS.format(
            ticker=ticker,
            transactions="\n".join(txn_text),
        )

        cache_key = self._cache_key(prompt)
        result = await self._call_llm(prompt, cache_key)

        if result:
            # Convert patterns to InsiderPattern objects
            patterns = []
            for p in result.get("patterns", []):
                pattern = InsiderPattern(
                    type=p.get("type", "UNKNOWN"),
                    title=p.get("title", "Unknown"),
                    severity=Severity(p.get("severity", "medium")),
                    details=p.get("details"),
                    evidence_url=transactions[0].url if transactions else None,
                )
                patterns.append(pattern)

            return {
                "patterns": patterns,
                "net_activity": result.get("net_activity", "neutral"),
                "total_sold": result.get("total_sold", 0),
                "total_bought": result.get("total_bought", 0),
                "insiders_selling": result.get("insiders_selling", 0),
                "insiders_buying": result.get("insiders_buying", 0),
                "risk_assessment": result.get("risk_assessment", ""),
            }

        # Fallback: compute basic stats from raw transactions
        logger.warning(f"LLM insider analysis failed for {ticker}, using fallback calculation")
        return self._compute_insider_fallback(transactions)

    async def _score_severity(
        self,
        ticker: str,
        red_flags: list[RedFlag],
        insider_data: dict
    ) -> dict:
        """Calculate risk score"""
        if not red_flags and not insider_data.get("patterns"):
            return {
                "risk_score": 10,
                "risk_level": "low",
                "reasoning": "No significant red flags or concerning insider patterns detected.",
            }

        flags_json = [
            {"type": f.type, "title": f.title, "severity": f.severity.value}
            for f in red_flags
        ]

        prompt = AnalysisPrompts.RISK_SCORING.format(
            ticker=ticker,
            red_flags=json.dumps(flags_json, indent=2) if flags_json else "None detected",
            insider_patterns=json.dumps(insider_data, indent=2, default=str),
        )

        cache_key = self._cache_key(prompt)
        result = await self._call_llm(prompt, cache_key)

        if result:
            return result

        # Fallback: compute basic score from flags and insider data
        logger.warning(f"LLM scoring failed for {ticker}, using fallback calculation")
        return self._compute_score_fallback(red_flags, insider_data)

    async def _generate_explanation(
        self,
        ticker: str,
        risk_score: int,
        risk_level: str,
        red_flags: list[RedFlag],
        insider_summary: InsiderSummary,
    ) -> str:
        """Generate plain-English explanation with validation and post-processing"""
        fallback = f"{ticker} shows {risk_level} risk (score: {risk_score}/100). Detailed explanation unavailable."

        flags_text = []
        for flag in red_flags[:5]:
            flags_text.append(f"- {flag.title}: {flag.details or ''}")

        prompt = AnalysisPrompts.EXPLANATION_GENERATION.format(
            ticker=ticker,
            risk_score=risk_score,
            risk_level=risk_level,
            red_flags="\n".join(flags_text) if flags_text else "None",
            insider_summary=f"Net: {insider_summary.net_activity}, Sold: ${insider_summary.total_sold:,}, Bought: ${insider_summary.total_bought:,}",
        )

        try:
            response = self._client.chat.completions.create(
                model=self._settings.llm.model,
                messages=[
                    {"role": "system", "content": "You are a financial analyst. Write clear, concise risk summaries for investors."},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.3,
                max_tokens=300,
            )
            raw_explanation = response.choices[0].message.content.strip()

            # Post-process the explanation
            processed = self._post_process_explanation(raw_explanation)

            # Validate the explanation
            if self._validate_explanation(processed, ticker):
                return processed
            else:
                logger.warning(f"LLM explanation for {ticker} failed validation, using fallback")
                return fallback

        except Exception as e:
            logger.warning(f"LLM explanation failed for {ticker}: {e}")
            return fallback

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type(LLMRateLimitError),
        reraise=True,
    )
    async def _call_llm(self, prompt: str, cache_key: str) -> Optional[dict]:
        """Call LLM and parse JSON response with caching and retry"""
        # Check cache with TTL
        cached = self._get_from_cache(cache_key)
        if cached is not None:
            return cached

        try:
            response = self._client.chat.completions.create(
                model=self._settings.llm.model,
                messages=[
                    {"role": "system", "content": self.SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                temperature=self._settings.llm.temperature,
                max_tokens=self._settings.llm.max_tokens,
            )

            content = response.choices[0].message.content.strip()
            result = self._parse_json_response(content)

            if result:
                self._set_cache(cache_key, result)

            return result

        except Exception as e:
            if "rate_limit" in str(e).lower():
                raise LLMRateLimitError(provider="Groq")
            logger.warning(f"LLM call failed: {e}")
            return None

    def _parse_json_response(self, content: str) -> Optional[dict]:
        """Parse JSON from LLM response"""
        # Try direct parse
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            pass

        # Try extracting from markdown code block
        if "```" in content:
            json_match = re.search(r"```(?:json)?\s*([\s\S]*?)```", content)
            if json_match:
                try:
                    return json.loads(json_match.group(1))
                except json.JSONDecodeError:
                    pass

        # Try finding JSON object in text
        json_match = re.search(r"\{[\s\S]*\}", content)
        if json_match:
            try:
                return json.loads(json_match.group(0))
            except json.JSONDecodeError:
                pass

        return None

    def _cache_key(self, content: str) -> str:
        """Generate cache key from content"""
        return hashlib.md5(content.encode()).hexdigest()[:16]

    def _validate_explanation(self, explanation: str, ticker: str) -> bool:
        """
        Validate LLM-generated explanation.

        Checks:
        - Length is between 50 and 500 characters
        - Does not contain financial advice phrases
        - Contains the ticker symbol (substance check)
        """
        # Length check
        if len(explanation) < 50 or len(explanation) > 500:
            return False

        # No financial advice check
        advice_phrases = [
            "you should buy",
            "you should sell",
            "i recommend buying",
            "i recommend selling",
            "financial advice",
            "investment advice",
            "not financial advice",
        ]
        explanation_lower = explanation.lower()
        if any(phrase in explanation_lower for phrase in advice_phrases):
            return False

        # Substance check - must contain ticker
        if ticker.upper() not in explanation.upper():
            return False

        return True

    def _post_process_explanation(self, explanation: str, max_length: int = 500) -> str:
        """
        Post-process LLM-generated explanation.

        - Removes markdown formatting
        - Ensures ends with period
        - Truncates if too long
        """
        # Remove markdown formatting
        processed = explanation
        # Remove bold/italic markers
        processed = re.sub(r'\*{1,2}([^*]+)\*{1,2}', r'\1', processed)
        # Remove inline code markers
        processed = re.sub(r'`([^`]+)`', r'\1', processed)
        # Remove headers
        processed = re.sub(r'^#{1,6}\s+', '', processed, flags=re.MULTILINE)
        # Clean up extra whitespace
        processed = ' '.join(processed.split())

        # Truncate if too long
        if len(processed) > max_length:
            # Try to truncate at a sentence boundary
            truncated = processed[:max_length]
            last_period = truncated.rfind('.')
            if last_period > max_length // 2:
                processed = truncated[:last_period + 1]
            else:
                processed = truncated.rstrip() + "..."

        # Ensure ends with period
        if processed and not processed.endswith(('.', '!', '?', '...')):
            processed = processed.rstrip() + '.'

        return processed

    def _compute_insider_fallback(self, transactions: tuple) -> dict:
        """Fallback insider analysis when LLM fails"""
        total_sold = 0
        total_bought = 0
        sellers = set()
        buyers = set()

        for t in transactions:
            value = t.total_value or 0
            # S = Sale, P = Purchase
            if t.transaction_type == "S":
                total_sold += value
                sellers.add(t.insider_name)
            elif t.transaction_type == "P":
                total_bought += value
                buyers.add(t.insider_name)

        if total_sold > total_bought * 2:
            net_activity = "heavy_selling"
        elif total_sold > total_bought:
            net_activity = "net_selling"
        elif total_bought > total_sold * 2:
            net_activity = "heavy_buying"
        elif total_bought > total_sold:
            net_activity = "net_buying"
        else:
            net_activity = "neutral"

        return {
            "patterns": [],
            "net_activity": net_activity,
            "total_sold": total_sold,
            "total_bought": total_bought,
            "insiders_selling": len(sellers),
            "insiders_buying": len(buyers),
            "risk_assessment": "Fallback calculation - LLM unavailable",
        }

    def _compute_score_fallback(self, red_flags: list[RedFlag], insider_data: dict) -> dict:
        """Fallback risk scoring when LLM fails"""
        score = 20  # Base score

        # Add points for red flags
        severity_weights = {"high": 20, "medium": 10, "low": 5}
        for flag in red_flags:
            score += severity_weights.get(flag.severity.value, 10)

        # Add points for concerning insider activity
        if insider_data.get("net_activity") == "heavy_selling":
            score += 15
        elif insider_data.get("net_activity") == "net_selling":
            score += 8

        # Cap at 100
        score = min(score, 100)

        # Determine level (aligned with RiskLevel enum)
        if score >= 70:
            risk_level = "high"
        elif score >= 50:
            risk_level = "elevated"
        elif score >= 30:
            risk_level = "moderate"
        else:
            risk_level = "low"

        return {
            "risk_score": score,
            "risk_level": risk_level,
            "reasoning": "Fallback calculation - LLM unavailable",
        }
