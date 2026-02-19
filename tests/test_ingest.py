"""Tests for oura_ingest.ingest (tasks 21, 23, 25, 27)."""

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

    def test_with_null_last_sync_date(self):
        """When sync_log row exists but last_sync_date is NULL, use HISTORY_START_DATE."""
        engine = MagicMock()
        conn = MagicMock()
        engine.connect.return_value.__enter__ = Mock(return_value=conn)
        engine.connect.return_value.__exit__ = Mock(return_value=False)
        conn.execute.return_value.fetchone.return_value = (None,)

        env_backup = os.environ.copy()
        os.environ["HISTORY_START_DATE"] = "2022-01-01"
        try:
            from oura_ingest.config import Config

            with patch("oura_ingest.ingest.cfg", Config()):
                from oura_ingest.ingest import _get_start_date

                result = _get_start_date(engine, "daily_sleep")
                assert result == "2022-01-01"
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


# --- Task 27: sync_log and sync_history tests ---


class TestUpdateSyncLog:
    def test_successful_sync_writes_sync_log(self):
        """_update_sync_log executes an UPSERT with correct params."""
        from oura_ingest.ingest import _update_sync_log

        engine = MagicMock()
        conn = MagicMock()
        engine.begin.return_value.__enter__ = Mock(return_value=conn)
        engine.begin.return_value.__exit__ = Mock(return_value=False)

        _update_sync_log(engine, "daily_sleep", 42)

        conn.execute.assert_called_once()
        params = conn.execute.call_args[0][1]
        assert params["ep"] == "daily_sleep"
        assert params["c"] == 42

    def test_sync_log_clears_error_fields(self):
        """The SQL should set last_error=NULL and consecutive_failures=0."""
        from oura_ingest.ingest import _update_sync_log

        engine = MagicMock()
        conn = MagicMock()
        engine.begin.return_value.__enter__ = Mock(return_value=conn)
        engine.begin.return_value.__exit__ = Mock(return_value=False)

        _update_sync_log(engine, "daily_sleep", 10)

        sql_str = str(conn.execute.call_args[0][0])
        assert "last_error" in sql_str
        assert "consecutive_failures" in sql_str


class TestRecordSyncFailure:
    def test_failure_records_error(self):
        """_record_sync_failure writes error message to sync_log."""
        from oura_ingest.ingest import _record_sync_failure

        engine = MagicMock()
        conn = MagicMock()
        engine.begin.return_value.__enter__ = Mock(return_value=conn)
        engine.begin.return_value.__exit__ = Mock(return_value=False)

        _record_sync_failure(engine, "daily_sleep", "Connection refused")

        conn.execute.assert_called_once()
        params = conn.execute.call_args[0][1]
        assert params["ep"] == "daily_sleep"
        assert params["err"] == "Connection refused"


class TestRecordSyncHistory:
    def test_history_row_created(self):
        """_record_sync_history inserts a new row with correct params."""
        from oura_ingest.ingest import _record_sync_history

        engine = MagicMock()
        conn = MagicMock()
        engine.begin.return_value.__enter__ = Mock(return_value=conn)
        engine.begin.return_value.__exit__ = Mock(return_value=False)

        _record_sync_history(engine, "daily_sleep", 50, 3.5, "success")

        conn.execute.assert_called_once()
        params = conn.execute.call_args[0][1]
        assert params["ep"] == "daily_sleep"
        assert params["cnt"] == 50
        assert params["dur"] == 3.5
        assert params["status"] == "success"
        assert params["err"] is None

    def test_history_with_error(self):
        """_record_sync_history stores error message when provided."""
        from oura_ingest.ingest import _record_sync_history

        engine = MagicMock()
        conn = MagicMock()
        engine.begin.return_value.__enter__ = Mock(return_value=conn)
        engine.begin.return_value.__exit__ = Mock(return_value=False)

        _record_sync_history(engine, "daily_sleep", 0, 1.0, "error", "timeout")

        params = conn.execute.call_args[0][1]
        assert params["status"] == "error"
        assert params["err"] == "timeout"


class TestSyncOverlapGuard:
    def test_skips_if_lock_held(self, caplog):
        """sync_all should skip if another sync is in progress."""
        from oura_ingest.ingest import _sync_lock, sync_all

        engine = MagicMock()
        client = MagicMock()

        # Acquire the lock to simulate an in-progress sync
        _sync_lock.acquire()
        try:
            with caplog.at_level("WARNING"):
                sync_all(engine, client)

            assert any("already in progress" in r.message for r in caplog.records)
        finally:
            _sync_lock.release()
