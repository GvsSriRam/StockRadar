"""
Tests for LLM Analyzer - JSON parsing and fallback methods
"""

import pytest
from unittest.mock import MagicMock, patch

from src.core.models import (
    InsiderTransaction,
    RedFlag,
    Severity,
)


class TestParseJsonResponse:
    """Tests for _parse_json_response method"""

    @pytest.fixture
    def analyzer(self):
        """Create analyzer instance with mocked Groq client"""
        with patch("src.analyzers.llm_analyzer.Groq"):
            with patch("src.analyzers.llm_analyzer.get_settings") as mock_settings:
                mock_settings.return_value.llm.api_key = "test-key"
                mock_settings.return_value.llm.model = "test-model"
                mock_settings.return_value.llm.temperature = 0.1
                mock_settings.return_value.llm.max_tokens = 1000
                from src.analyzers.llm_analyzer import GroqLLMAnalyzer
                return GroqLLMAnalyzer(api_key="test-key")

    def test_direct_json(self, analyzer):
        """Valid JSON parses directly"""
        content = '{"red_flags": [], "risk_score": 25}'
        result = analyzer._parse_json_response(content)
        assert result == {"red_flags": [], "risk_score": 25}

    def test_json_in_markdown_block(self, analyzer):
        """JSON in ```json block extracts correctly"""
        content = '''Here is the analysis:
```json
{"red_flags": [{"type": "TEST", "title": "Test Flag"}]}
```
That's all.'''
        result = analyzer._parse_json_response(content)
        assert result == {"red_flags": [{"type": "TEST", "title": "Test Flag"}]}

    def test_json_in_plain_markdown_block(self, analyzer):
        """JSON in plain ``` block extracts correctly"""
        content = '''```
{"risk_score": 50}
```'''
        result = analyzer._parse_json_response(content)
        assert result == {"risk_score": 50}

    def test_json_object_in_text(self, analyzer):
        """JSON embedded in text extracts correctly"""
        content = 'Based on the analysis, here is my result: {"status": "ok", "score": 10} Hope this helps!'
        result = analyzer._parse_json_response(content)
        assert result == {"status": "ok", "score": 10}

    def test_nested_json_object(self, analyzer):
        """Nested JSON objects parse correctly"""
        content = '{"patterns": [{"type": "CLUSTER", "details": {"count": 3}}]}'
        result = analyzer._parse_json_response(content)
        assert result["patterns"][0]["details"]["count"] == 3

    def test_malformed_json_returns_none(self, analyzer):
        """Invalid JSON returns None"""
        content = '{"incomplete": '
        result = analyzer._parse_json_response(content)
        assert result is None

    def test_plain_text_returns_none(self, analyzer):
        """Plain text without JSON returns None"""
        content = "This is just a plain text response with no JSON."
        result = analyzer._parse_json_response(content)
        assert result is None

    def test_empty_string_returns_none(self, analyzer):
        """Empty string returns None"""
        result = analyzer._parse_json_response("")
        assert result is None


class TestComputeInsiderFallback:
    """Tests for _compute_insider_fallback method"""

    @pytest.fixture
    def analyzer(self):
        """Create analyzer instance with mocked Groq client"""
        with patch("src.analyzers.llm_analyzer.Groq"):
            with patch("src.analyzers.llm_analyzer.get_settings") as mock_settings:
                mock_settings.return_value.llm.api_key = "test-key"
                mock_settings.return_value.llm.model = "test-model"
                mock_settings.return_value.llm.temperature = 0.1
                mock_settings.return_value.llm.max_tokens = 1000
                from src.analyzers.llm_analyzer import GroqLLMAnalyzer
                return GroqLLMAnalyzer(api_key="test-key")

    def test_heavy_selling(self, analyzer):
        """Heavy selling is detected when sold > 2x bought"""
        transactions = (
            InsiderTransaction(
                date="2025-01-01",
                insider_name="CEO",
                insider_title="CEO",
                transaction_type="S",
                shares=10000,
                total_value=1000000,
            ),
        )
        result = analyzer._compute_insider_fallback(transactions)
        assert result["net_activity"] == "heavy_selling"
        assert result["total_sold"] == 1000000
        assert result["total_bought"] == 0
        assert result["insiders_selling"] == 1
        assert result["insiders_buying"] == 0

    def test_net_selling(self, analyzer):
        """Net selling detected when sold > bought but < 2x"""
        transactions = (
            InsiderTransaction(
                date="2025-01-01",
                insider_name="CEO",
                insider_title="CEO",
                transaction_type="S",
                shares=10000,
                total_value=100000,
            ),
            InsiderTransaction(
                date="2025-01-02",
                insider_name="CFO",
                insider_title="CFO",
                transaction_type="P",
                shares=5000,
                total_value=60000,
            ),
        )
        result = analyzer._compute_insider_fallback(transactions)
        assert result["net_activity"] == "net_selling"

    def test_heavy_buying(self, analyzer):
        """Heavy buying detected when bought > 2x sold"""
        transactions = (
            InsiderTransaction(
                date="2025-01-01",
                insider_name="CEO",
                insider_title="CEO",
                transaction_type="P",
                shares=10000,
                total_value=1000000,
            ),
        )
        result = analyzer._compute_insider_fallback(transactions)
        assert result["net_activity"] == "heavy_buying"

    def test_neutral_activity(self, analyzer):
        """Neutral when buying equals selling"""
        transactions = (
            InsiderTransaction(
                date="2025-01-01",
                insider_name="CEO",
                insider_title="CEO",
                transaction_type="S",
                shares=10000,
                total_value=100000,
            ),
            InsiderTransaction(
                date="2025-01-02",
                insider_name="CFO",
                insider_title="CFO",
                transaction_type="P",
                shares=10000,
                total_value=100000,
            ),
        )
        result = analyzer._compute_insider_fallback(transactions)
        assert result["net_activity"] == "neutral"

    def test_empty_transactions(self, analyzer):
        """Empty transactions return neutral with zeros"""
        result = analyzer._compute_insider_fallback(())
        assert result["net_activity"] == "neutral"
        assert result["total_sold"] == 0
        assert result["total_bought"] == 0


class TestComputeScoreFallback:
    """Tests for _compute_score_fallback method"""

    @pytest.fixture
    def analyzer(self):
        """Create analyzer instance with mocked Groq client"""
        with patch("src.analyzers.llm_analyzer.Groq"):
            with patch("src.analyzers.llm_analyzer.get_settings") as mock_settings:
                mock_settings.return_value.llm.api_key = "test-key"
                mock_settings.return_value.llm.model = "test-model"
                mock_settings.return_value.llm.temperature = 0.1
                mock_settings.return_value.llm.max_tokens = 1000
                from src.analyzers.llm_analyzer import GroqLLMAnalyzer
                return GroqLLMAnalyzer(api_key="test-key")

    def test_no_flags_low_risk(self, analyzer):
        """No flags results in low risk"""
        result = analyzer._compute_score_fallback([], {})
        assert result["risk_level"] == "low"
        assert result["risk_score"] == 20

    def test_high_severity_flag_elevated(self, analyzer):
        """High severity flag increases score"""
        flags = [
            RedFlag(
                type="TEST",
                title="Test",
                severity=Severity.HIGH,
            )
        ]
        result = analyzer._compute_score_fallback(flags, {})
        assert result["risk_score"] == 40  # 20 base + 20 for high

    def test_multiple_flags_stack(self, analyzer):
        """Multiple flags add up"""
        flags = [
            RedFlag(type="TEST1", title="Test1", severity=Severity.HIGH),
            RedFlag(type="TEST2", title="Test2", severity=Severity.MEDIUM),
            RedFlag(type="TEST3", title="Test3", severity=Severity.LOW),
        ]
        result = analyzer._compute_score_fallback(flags, {})
        # 20 base + 20 high + 10 medium + 5 low = 55
        assert result["risk_score"] == 55
        assert result["risk_level"] == "elevated"

    def test_heavy_selling_adds_points(self, analyzer):
        """Heavy selling adds 15 points"""
        insider_data = {"net_activity": "heavy_selling"}
        result = analyzer._compute_score_fallback([], insider_data)
        assert result["risk_score"] == 35  # 20 base + 15 heavy selling
        assert result["risk_level"] == "moderate"

    def test_net_selling_adds_points(self, analyzer):
        """Net selling adds 8 points"""
        insider_data = {"net_activity": "net_selling"}
        result = analyzer._compute_score_fallback([], insider_data)
        assert result["risk_score"] == 28  # 20 base + 8 net selling
        assert result["risk_level"] == "low"

    def test_score_capped_at_100(self, analyzer):
        """Score is capped at 100"""
        flags = [
            RedFlag(type=f"TEST{i}", title=f"Test{i}", severity=Severity.HIGH)
            for i in range(10)  # 10 * 20 = 200 points
        ]
        result = analyzer._compute_score_fallback(flags, {})
        assert result["risk_score"] == 100
        assert result["risk_level"] == "high"  # Aligned with RiskLevel enum

    def test_high_threshold(self, analyzer):
        """Score >= 70 is high risk"""
        flags = [
            RedFlag(type="TEST1", title="Test1", severity=Severity.HIGH),
            RedFlag(type="TEST2", title="Test2", severity=Severity.HIGH),
            RedFlag(type="TEST3", title="Test3", severity=Severity.MEDIUM),
        ]
        result = analyzer._compute_score_fallback(flags, {})
        # 20 + 20 + 20 + 10 = 70
        assert result["risk_score"] == 70
        assert result["risk_level"] == "high"  # Aligned with RiskLevel enum
