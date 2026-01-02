"""
Tests for core models
"""

import pytest
from datetime import datetime, timezone

from src.core.models import (
    RiskLevel,
    Severity,
    Filing8K,
    InsiderTransaction,
    SECFilingData,
    RiskReport,
    InsiderSummary,
)


class TestRiskLevel:
    """Tests for RiskLevel enum"""

    def test_from_score_low(self):
        """Score < 30 should be LOW"""
        assert RiskLevel.from_score(0) == RiskLevel.LOW
        assert RiskLevel.from_score(29) == RiskLevel.LOW

    def test_from_score_moderate(self):
        """Score 30-49 should be MODERATE"""
        assert RiskLevel.from_score(30) == RiskLevel.MODERATE
        assert RiskLevel.from_score(49) == RiskLevel.MODERATE

    def test_from_score_elevated(self):
        """Score 50-69 should be ELEVATED"""
        assert RiskLevel.from_score(50) == RiskLevel.ELEVATED
        assert RiskLevel.from_score(69) == RiskLevel.ELEVATED

    def test_from_score_high(self):
        """Score >= 70 should be HIGH"""
        assert RiskLevel.from_score(70) == RiskLevel.HIGH
        assert RiskLevel.from_score(100) == RiskLevel.HIGH


class TestFiling8K:
    """Tests for Filing8K model"""

    def test_has_critical_item_true(self):
        """Should detect critical items"""
        filing = Filing8K(
            date="2025-01-15",
            form_type="8-K",
            title="Test",
            items=("4.01 - Changes in Registrant's Certifying Accountant",),
        )
        assert filing.has_critical_item() is True

    def test_has_critical_item_false(self):
        """Should return False for non-critical items"""
        filing = Filing8K(
            date="2025-01-15",
            form_type="8-K",
            title="Test",
            items=("7.01 - Regulation FD Disclosure",),
        )
        assert filing.has_critical_item() is False

    def test_frozen(self):
        """Filing8K should be immutable"""
        filing = Filing8K(
            date="2025-01-15",
            form_type="8-K",
            title="Test",
        )
        with pytest.raises(AttributeError):
            filing.date = "2025-01-16"


class TestInsiderTransaction:
    """Tests for InsiderTransaction model"""

    def test_is_sale(self, sample_insider_transaction):
        """Should identify sales"""
        assert sample_insider_transaction.is_sale is True
        assert sample_insider_transaction.is_purchase is False

    def test_is_purchase(self):
        """Should identify purchases"""
        txn = InsiderTransaction(
            date="2025-01-14",
            insider_name="Test",
            insider_title="CEO",
            transaction_type="P",
            shares=1000,
        )
        assert txn.is_purchase is True
        assert txn.is_sale is False

    def test_transaction_description(self, sample_insider_transaction):
        """Should return human-readable description"""
        assert sample_insider_transaction.transaction_description == "Sale"


class TestSECFilingData:
    """Tests for SECFilingData model"""

    def test_has_data_true(self, sample_sec_data):
        """Should return True when filings exist"""
        assert sample_sec_data.has_data is True

    def test_has_data_false(self, empty_sec_data):
        """Should return False when no filings"""
        assert empty_sec_data.has_data is False

    def test_total_filings(self, sample_sec_data):
        """Should count all filings"""
        assert sample_sec_data.total_filings == 3  # 1 8-K + 2 Form 4


class TestRiskReport:
    """Tests for RiskReport model"""

    def test_exceeds_threshold_true(self, sample_risk_report):
        """Should return True when score exceeds threshold"""
        assert sample_risk_report.exceeds_threshold(70) is True
        assert sample_risk_report.exceeds_threshold(69) is True

    def test_exceeds_threshold_false(self, sample_risk_report):
        """Should return False when score below threshold"""
        assert sample_risk_report.exceeds_threshold(71) is False
        assert sample_risk_report.exceeds_threshold(100) is False
