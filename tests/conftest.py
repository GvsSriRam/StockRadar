"""
Pytest fixtures for SEC Filing Risk Scanner tests
"""

import pytest
from datetime import datetime, timezone

from src.core.models import (
    Filing8K,
    InsiderTransaction,
    SECFilingData,
    RedFlag,
    InsiderPattern,
    InsiderSummary,
    AnalysisResult,
    ScoringResult,
    RiskReport,
    RiskLevel,
    Severity,
)


@pytest.fixture
def sample_filing_8k():
    """Sample 8-K filing"""
    return Filing8K(
        date="2025-01-15",
        form_type="8-K",
        title="Current Report",
        url="https://sec.gov/test/8k",
        content_snippet="The company announced executive changes...",
        items=("5.02 - Departure/Appointment of Directors or Officers",),
    )


@pytest.fixture
def sample_insider_transaction():
    """Sample insider transaction"""
    return InsiderTransaction(
        date="2025-01-14",
        insider_name="John Smith",
        insider_title="CFO",
        is_director=False,
        is_officer=True,
        transaction_type="S",
        shares=50000,
        price=150.00,
        total_value=7500000,
        url="https://sec.gov/test/form4",
    )


@pytest.fixture
def sample_sec_data(sample_filing_8k, sample_insider_transaction):
    """Sample SEC filing data"""
    return SECFilingData(
        ticker="TEST",
        cik="0001234567",
        filings_8k=(sample_filing_8k,),
        filings_form4=(
            sample_insider_transaction,
            InsiderTransaction(
                date="2025-01-13",
                insider_name="Jane Doe",
                insider_title="CEO",
                is_director=True,
                is_officer=True,
                transaction_type="S",
                shares=30000,
                price=148.00,
                total_value=4440000,
                url="https://sec.gov/test/form4-2",
            ),
        ),
        collected_at=datetime.now(timezone.utc),
        lookback_days=30,
        error=None,
    )


@pytest.fixture
def sample_red_flag():
    """Sample red flag"""
    return RedFlag(
        type="EXECUTIVE_CHANGE",
        title="CFO Departure",
        severity=Severity.HIGH,
        details="CFO resigned effective immediately",
        evidence_url="https://sec.gov/test/8k",
        filing_date="2025-01-15",
    )


@pytest.fixture
def sample_insider_pattern():
    """Sample insider pattern"""
    return InsiderPattern(
        type="CLUSTER_SELLING",
        title="2 Executives Sold $11.9M",
        severity=Severity.HIGH,
        details="CFO and CEO sold within 2 days",
        evidence_url="https://sec.gov/test/form4",
    )


@pytest.fixture
def sample_insider_summary():
    """Sample insider summary"""
    return InsiderSummary(
        net_activity="net_selling",
        total_sold=11940000,
        total_bought=0,
        insiders_selling=2,
        insiders_buying=0,
    )


@pytest.fixture
def sample_analysis_result(sample_red_flag, sample_insider_pattern, sample_insider_summary):
    """Sample analysis result"""
    return AnalysisResult(
        red_flags=(sample_red_flag,),
        insider_patterns=(sample_insider_pattern,),
        insider_summary=sample_insider_summary,
        risk_score=65,
        risk_level=RiskLevel.ELEVATED,
        reasoning="Multiple concerning signals detected.",
        explanation="TEST shows elevated risk due to executive departure and coordinated insider selling.",
    )


@pytest.fixture
def sample_scoring_result():
    """Sample scoring result"""
    return ScoringResult(
        risk_score=70,
        risk_level=RiskLevel.HIGH,
        base_score=65,
        adjustments=5,
        adjustment_reasons=("+5 for red flags + insider selling combination",),
    )


@pytest.fixture
def sample_risk_report(sample_analysis_result, sample_scoring_result, sample_insider_summary):
    """Sample risk report"""
    return RiskReport(
        ticker="TEST",
        risk_score=70,
        risk_level=RiskLevel.HIGH,
        red_flags=sample_analysis_result.red_flags,
        red_flags_count=1,
        insider_patterns=sample_analysis_result.insider_patterns,
        insider_summary=sample_insider_summary,
        explanation=sample_analysis_result.explanation,
        reasoning=sample_analysis_result.reasoning,
        evidence_links=("https://sec.gov/test/8k", "https://sec.gov/test/form4"),
        filings_analyzed={"8k_count": 1, "form4_count": 2},
        scoring_details={
            "base_score": 65,
            "adjustments": 5,
            "adjustment_reasons": ["+5 for combo"],
        },
        analyzed_at=datetime.now(timezone.utc),
        lookback_days=30,
    )


@pytest.fixture
def empty_sec_data():
    """Empty SEC data (no filings found)"""
    return SECFilingData(
        ticker="EMPTY",
        cik="0009999999",
        filings_8k=tuple(),
        filings_form4=tuple(),
        collected_at=datetime.now(timezone.utc),
        lookback_days=30,
        error=None,
    )


@pytest.fixture
def empty_analysis_result():
    """Analysis result with no red flags"""
    return AnalysisResult(
        red_flags=tuple(),
        insider_patterns=tuple(),
        insider_summary=InsiderSummary(
            net_activity="neutral",
            total_sold=0,
            total_bought=0,
            insiders_selling=0,
            insiders_buying=0,
        ),
        risk_score=10,
        risk_level=RiskLevel.LOW,
        reasoning="No significant signals detected.",
        explanation="No concerning signals found in the lookback period.",
    )


@pytest.fixture
def auditor_change_analysis():
    """Analysis result with auditor change"""
    return AnalysisResult(
        red_flags=(
            RedFlag(
                type="AUDITOR_CHANGE",
                title="Auditor Resignation",
                severity=Severity.HIGH,
                details="Independent auditor resigned",
            ),
        ),
        insider_patterns=tuple(),
        insider_summary=InsiderSummary(
            net_activity="neutral",
            total_sold=0,
            total_bought=0,
            insiders_selling=0,
            insiders_buying=0,
        ),
        risk_score=50,
        risk_level=RiskLevel.MODERATE,
        reasoning="Auditor change detected.",
        explanation=None,
    )
