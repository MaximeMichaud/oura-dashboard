"""Tests for oura_ingest.ingest (tasks 21, 23, 25)."""

import os
from datetime import date, timedelta
from unittest.mock import MagicMock, Mock, patch

import pytest
from oura_ingest.ingest import _validate_ident

# --- Task 21: _validate_ident tests ---


class TestValidateIdent:
    def test_valid_simple(self):
        assert _validate_ident("daily_sleep") == "daily_sleep"

    def test_valid_with_numbers(self):
        assert _validate_ident("sleep2") == "sleep2"

    def test_valid_underscore_prefix(self):
        assert _validate_ident("_private") == "_private"

    def test_invalid_space(self):
        with pytest.raises(ValueError, match="Invalid SQL identifier"):
            _validate_ident("daily sleep")

    def test_invalid_semicolon(self):
        with pytest.raises(ValueError):
            _validate_ident("daily_sleep; DROP TABLE sleep;--")

    def test_invalid_dash(self):
        with pytest.raises(ValueError):
            _validate_ident("daily-sleep")

    def test_invalid_uppercase(self):
        with pytest.raises(ValueError):
            _validate_ident("Daily_Sleep")

    def test_sql_injection(self):
        with pytest.raises(ValueError):
            _validate_ident("'; DROP TABLE users; --")

    def test_empty_string(self):
        with pytest.raises(ValueError):
            _validate_ident("")

    def test_starts_with_number(self):
        with pytest.raises(ValueError):
            _validate_ident("2table")


# --- Task 23: _get_start_date tests ---


class TestGetStartDate:
    def test_no_sync_log_row(self):
        """When no sync_log entry exists, return HISTORY_START_DATE."""
        engine = MagicMock()
        conn = MagicMock()
        engine.connect.return_value.__enter__ = Mock(return_value=conn)
        engine.connect.return_value.__exit__ = Mock(return_value=False)
        conn.execute.return_value.fetchone.return_value = None

        env_backup = os.environ.copy()
        os.environ["HISTORY_START_DATE"] = "2021-06-01"
        try:
            from oura_ingest.config import Config

            with patch("oura_ingest.ingest.cfg", Config()):
                from oura_ingest.ingest import _get_start_date

                result = _get_start_date(engine, "daily_sleep")
                assert result == "2021-06-01"
        finally:
            os.environ.clear()
            os.environ.update(env_backup)

    def test_with_sync_log_row(self):
        """When sync_log has a row, return last_sync_date - OVERLAP_DAYS."""
        engine = MagicMock()
        conn = MagicMock()
        engine.connect.return_value.__enter__ = Mock(return_value=conn)
        engine.connect.return_value.__exit__ = Mock(return_value=False)
        last_sync = date(2025, 1, 15)
        conn.execute.return_value.fetchone.return_value = (last_sync,)

        env_backup = os.environ.copy()
        os.environ["OVERLAP_DAYS"] = "3"
        try:
            from oura_ingest.config import Config

            with patch("oura_ingest.ingest.cfg", Config()):
                from oura_ingest.ingest import _get_start_date

                result = _get_start_date(engine, "daily_sleep")
                expected = (last_sync - timedelta(days=3)).isoformat()
                assert result == expected
        finally:
            os.environ.clear()
            os.environ.update(env_backup)


# --- Task 25: sync_endpoint transform error handling ---


class TestSyncEndpointTransformErrors:
    def test_skips_bad_records(self, caplog):
        """One bad record should not abort sync - good records are still processed."""
        from oura_ingest.endpoint import Endpoint
        from oura_ingest.ingest import sync_endpoint

        call_count = 0

        def transform(rec):
            nonlocal call_count
            call_count += 1
            if rec.get("bad"):
                raise ValueError("bad record")
            return {"day": rec["day"], "score": rec.get("score", 0)}

        ep = Endpoint(
            name="test_ep",
            api_path="test_ep",
            table="test_ep",
            pk="day",
            transform=transform,
        )

        records = [
            {"day": "2025-01-01", "score": 85},
            {"day": "2025-01-02", "bad": True},
            {"day": "2025-01-03", "score": 90},
        ]

        mock_client = MagicMock()
        mock_client.fetch_all.return_value = iter(records)

        mock_engine = MagicMock()
        conn = MagicMock()
        mock_engine.connect.return_value.__enter__ = Mock(return_value=conn)
        mock_engine.connect.return_value.__exit__ = Mock(return_value=False)
        conn.execute.return_value.fetchone.return_value = None

        with (
            patch("oura_ingest.ingest._upsert_batch", return_value=2) as mock_upsert,
            patch("oura_ingest.ingest._update_sync_log"),
            patch("oura_ingest.ingest._record_sync_history"),
            caplog.at_level("WARNING"),
        ):
            sync_endpoint(mock_engine, mock_client, ep)

        # _upsert_batch called with 2 good records (bad one skipped)
        assert mock_upsert.call_count == 1
        upsert_rows = mock_upsert.call_args[0][3]
        assert len(upsert_rows) == 2
        assert upsert_rows[0]["day"] == "2025-01-01"
        assert upsert_rows[1]["day"] == "2025-01-03"

        # transform was called 3 times
        assert call_count == 3

        # Warning logged for bad record
        assert any("Transform error" in r.message for r in caplog.records)
