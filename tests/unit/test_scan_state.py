"""
Tests for Scan State Storage
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from datetime import datetime, timezone, timedelta

from src.storage.scan_state import TickerScanState, ScanStats, ScanStateStore


class TestTickerScanState:
    """Tests for TickerScanState dataclass"""

    def test_to_dict_all_fields(self):
        """Converts all fields to dict"""
        state = TickerScanState(
            last_scan_time="2024-01-15T10:00:00+00:00",
            last_8k_date="2024-01-10",
            last_form4_date="2024-01-12",
            last_risk_score=75,
        )
        result = state.to_dict()

        assert result["last_scan_time"] == "2024-01-15T10:00:00+00:00"
        assert result["last_8k_date"] == "2024-01-10"
        assert result["last_form4_date"] == "2024-01-12"
        assert result["last_risk_score"] == 75

    def test_to_dict_with_none_dates(self):
        """Handles None dates correctly"""
        state = TickerScanState(
            last_scan_time="2024-01-15T10:00:00+00:00",
            last_8k_date=None,
            last_form4_date=None,
            last_risk_score=50,
        )
        result = state.to_dict()

        assert result["last_8k_date"] is None
        assert result["last_form4_date"] is None

    def test_from_dict_all_fields(self):
        """Creates state from dict with all fields"""
        data = {
            "last_scan_time": "2024-01-15T10:00:00+00:00",
            "last_8k_date": "2024-01-10",
            "last_form4_date": "2024-01-12",
            "last_risk_score": 75,
        }
        state = TickerScanState.from_dict(data)

        assert state.last_scan_time == "2024-01-15T10:00:00+00:00"
        assert state.last_8k_date == "2024-01-10"
        assert state.last_form4_date == "2024-01-12"
        assert state.last_risk_score == 75

    def test_from_dict_missing_optional_fields(self):
        """Handles missing optional fields with defaults"""
        data = {
            "last_scan_time": "2024-01-15T10:00:00+00:00",
        }
        state = TickerScanState.from_dict(data)

        assert state.last_8k_date is None
        assert state.last_form4_date is None
        assert state.last_risk_score == 0

    def test_is_stale_when_old(self):
        """Returns True when state is older than lookback"""
        old_time = (datetime.now(timezone.utc) - timedelta(days=35)).isoformat()
        state = TickerScanState(
            last_scan_time=old_time,
            last_8k_date=None,
            last_form4_date=None,
            last_risk_score=50,
        )

        assert state.is_stale(30) is True

    def test_is_stale_when_recent(self):
        """Returns False when state is within lookback"""
        recent_time = (datetime.now(timezone.utc) - timedelta(days=5)).isoformat()
        state = TickerScanState(
            last_scan_time=recent_time,
            last_8k_date=None,
            last_form4_date=None,
            last_risk_score=50,
        )

        assert state.is_stale(30) is False


class TestScanStats:
    """Tests for ScanStats dataclass"""

    def test_str_representation(self):
        """String representation shows key counts"""
        stats = ScanStats(total=100, scanned=30, skipped=70, reasons={"unchanged": 70})
        result = str(stats)

        assert "30" in result
        assert "100" in result
        assert "70" in result


class TestScanStateStore:
    """Tests for ScanStateStore"""

    @pytest.fixture
    def store(self):
        """Create store instance"""
        return ScanStateStore()

    def test_get_state_not_found(self, store):
        """Returns None for unknown ticker"""
        result = store.get_state("UNKNOWN")
        assert result is None

    def test_update_state_new_ticker(self, store):
        """Creates new state for new ticker"""
        store.update_state("AAPL", risk_score=75, last_8k_date="2024-01-10")

        state = store.get_state("AAPL")
        assert state is not None
        assert state.last_risk_score == 75
        assert state.last_8k_date == "2024-01-10"

    def test_update_state_preserves_dates(self, store):
        """Preserves existing dates when not provided"""
        store.update_state("AAPL", risk_score=75, last_8k_date="2024-01-10", last_form4_date="2024-01-12")
        store.update_state("AAPL", risk_score=80)  # Update without dates

        state = store.get_state("AAPL")
        assert state.last_8k_date == "2024-01-10"
        assert state.last_form4_date == "2024-01-12"
        assert state.last_risk_score == 80

    def test_update_state_normalizes_ticker(self, store):
        """Normalizes ticker to uppercase"""
        store.update_state("aapl", risk_score=75)
        state = store.get_state("AAPL")
        assert state is not None

    def test_needs_rescan_never_scanned(self, store):
        """Returns True for never-scanned ticker"""
        should_scan, reason = store.needs_rescan("UNKNOWN", lookback_days=30)

        assert should_scan is True
        assert reason == "never_scanned"

    def test_needs_rescan_stale(self, store):
        """Returns True for stale ticker"""
        old_time = (datetime.now(timezone.utc) - timedelta(days=35)).isoformat()
        store._state["AAPL"] = TickerScanState(
            last_scan_time=old_time,
            last_8k_date=None,
            last_form4_date=None,
            last_risk_score=50,
        )

        should_scan, reason = store.needs_rescan("AAPL", lookback_days=30)

        assert should_scan is True
        assert reason == "stale"

    def test_needs_rescan_check_filings(self, store):
        """Returns False with check_filings reason for recent scan"""
        recent_time = (datetime.now(timezone.utc) - timedelta(days=5)).isoformat()
        store._state["AAPL"] = TickerScanState(
            last_scan_time=recent_time,
            last_8k_date="2024-01-10",
            last_form4_date="2024-01-12",
            last_risk_score=50,
        )

        should_scan, reason = store.needs_rescan("AAPL", lookback_days=30)

        assert should_scan is False
        assert reason == "check_filings"

    def test_clear(self, store):
        """Clears all state"""
        store.update_state("AAPL", risk_score=75)
        store.update_state("MSFT", risk_score=50)

        store.clear()

        assert store.get_state("AAPL") is None
        assert store.get_state("MSFT") is None

    @pytest.mark.asyncio
    async def test_load_empty_store(self, store):
        """Loads empty state from new store"""
        mock_store = AsyncMock()
        mock_store.get_value.return_value = None

        with patch.object(store, "_get_store", return_value=mock_store):
            result = await store.load()

        assert result == {}
        assert store._state == {}

    @pytest.mark.asyncio
    async def test_load_existing_state(self, store):
        """Loads existing state from store"""
        mock_store = AsyncMock()
        mock_store.get_value.return_value = {
            "AAPL": {
                "last_scan_time": "2024-01-15T10:00:00+00:00",
                "last_8k_date": "2024-01-10",
                "last_form4_date": "2024-01-12",
                "last_risk_score": 75,
            }
        }

        with patch.object(store, "_get_store", return_value=mock_store):
            result = await store.load()

        assert "AAPL" in result
        assert result["AAPL"].last_risk_score == 75

    @pytest.mark.asyncio
    async def test_load_handles_corrupt_data(self, store):
        """Handles corrupt data gracefully"""
        mock_store = AsyncMock()
        mock_store.get_value.return_value = {"AAPL": "invalid_data"}

        with patch.object(store, "_get_store", return_value=mock_store):
            result = await store.load()

        assert result == {}

    @pytest.mark.asyncio
    async def test_save(self, store):
        """Saves state to store"""
        store.update_state("AAPL", risk_score=75)

        mock_store = AsyncMock()
        with patch.object(store, "_get_store", return_value=mock_store):
            await store.save()

        mock_store.set_value.assert_called_once()
        call_args = mock_store.set_value.call_args
        assert call_args[0][0] == "ticker_states"
        assert "AAPL" in call_args[0][1]
