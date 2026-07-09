"""Tests for oura_ingest.ingest (tasks 21, 23, 25, 27)."""

import os
from datetime import date, timedelta
from unittest.mock import MagicMock, Mock, patch

import pytest
import requests
from oura_ingest.ingest import _validate_ident


def _engine_with_begin():
    """A MagicMock engine whose .begin() acts as a context manager yielding a conn."""
    engine = MagicMock()
    conn = MagicMock()
    engine.begin.return_value.__enter__ = Mock(return_value=conn)
    engine.begin.return_value.__exit__ = Mock(return_value=False)
    return engine, conn


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

    def test_always_full_sync_ignores_sync_log(self):
        engine = MagicMock()

        from oura_ingest.ingest import _get_start_date

        result = _get_start_date(engine, "rest_mode_period", always_full_sync=True)

        assert result == "2020-01-01"
        engine.connect.assert_not_called()


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


def test_full_sync_does_not_report_an_incremental_gap(caplog):
    from oura_ingest.endpoint import Endpoint
    from oura_ingest.ingest import sync_endpoint

    ep = Endpoint(
        name="full_sync",
        api_path="full_sync",
        table="full_sync",
        pk="id",
        transform=lambda record: record,
        always_full_sync=True,
    )
    engine = MagicMock()
    client = MagicMock()
    client.fetch_all.return_value = iter(())

    with (
        patch("oura_ingest.ingest._upsert_batch"),
        patch("oura_ingest.ingest._update_sync_log"),
        patch("oura_ingest.ingest._record_sync_history"),
    ):
        sync_endpoint(engine, client, ep)

    assert "Sync gap" not in caplog.text


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


# --- _upsert_batch: SQL generation and row normalisation ---


class TestUpsertBatch:
    def test_empty_rows_returns_zero(self):
        from oura_ingest.ingest import _upsert_batch

        engine, conn = _engine_with_begin()
        assert _upsert_batch(engine, "daily_sleep", "day", []) == 0
        conn.execute.assert_not_called()

    def test_only_pk_column_is_a_noop(self):
        # Nothing to UPDATE if every column is the PK -> no SQL executed.
        from oura_ingest.ingest import _upsert_batch

        engine, conn = _engine_with_begin()
        assert _upsert_batch(engine, "daily_sleep", "day", [{"day": "2025-01-01"}]) == 0
        conn.execute.assert_not_called()

    def test_builds_upsert_sql_and_returns_count(self):
        from oura_ingest.ingest import _upsert_batch

        engine, conn = _engine_with_begin()
        rows = [{"day": "2025-01-01", "score": 85}, {"day": "2025-01-02", "score": 90}]
        assert _upsert_batch(engine, "daily_sleep", "day", rows) == 2

        conn.execute.assert_called_once()
        sql = str(conn.execute.call_args[0][0])
        assert "INSERT INTO daily_sleep (day, score)" in sql
        assert "ON CONFLICT (day) DO UPDATE SET" in sql
        assert "score = EXCLUDED.score" in sql
        assert "updated_at = now()" in sql
        # The PK must never appear in the UPDATE SET clause.
        assert "day = EXCLUDED.day" not in sql

    def test_normalizes_missing_keys_across_rows(self):
        from oura_ingest.ingest import _upsert_batch

        engine, conn = _engine_with_begin()
        rows = [{"day": "d1", "score": 85}, {"day": "d2", "rmssd": 40}]
        _upsert_batch(engine, "t", "day", rows)

        passed = conn.execute.call_args[0][1]
        # Every row carries the full column union; absent values are filled with None.
        assert all(set(r) == {"day", "score", "rmssd"} for r in passed)
        assert passed[0]["rmssd"] is None
        assert passed[1]["score"] is None

    def test_columns_sorted_deterministically(self):
        from oura_ingest.ingest import _upsert_batch

        engine, conn = _engine_with_begin()
        _upsert_batch(engine, "t", "day", [{"day": "d", "zeta": 1, "alpha": 2}])
        sql = str(conn.execute.call_args[0][0])
        assert sql.index("alpha") < sql.index("day") < sql.index("zeta")

    def test_invalid_table_identifier_raises(self):
        from oura_ingest.ingest import _upsert_batch

        engine, _ = _engine_with_begin()
        with pytest.raises(ValueError, match="Invalid SQL identifier"):
            _upsert_batch(engine, "bad table", "day", [{"day": "d", "x": 1}])

    def test_invalid_column_identifier_raises(self):
        from oura_ingest.ingest import _upsert_batch

        engine, _ = _engine_with_begin()
        with pytest.raises(ValueError, match="Invalid SQL identifier"):
            _upsert_batch(engine, "t", "day", [{"day": "d", "evil; DROP": 1}])


# --- _upsert: batch splitting ---


class TestUpsertBatching:
    """_upsert is not currently wired into sync_endpoint (which calls _upsert_batch
    directly), but its BATCH_SIZE splitting contract is covered here."""

    def test_empty_returns_zero(self):
        from oura_ingest.ingest import _upsert

        assert _upsert(MagicMock(), "t", "day", []) == 0

    def test_splits_into_batches_of_batch_size(self):
        from oura_ingest import ingest

        rows = [{"day": f"d{i}", "score": i} for i in range(ingest.BATCH_SIZE + 1)]
        with patch.object(ingest, "_upsert_batch", side_effect=lambda e, t, p, b: len(b)) as mock_batch:
            total = ingest._upsert(MagicMock(), "t", "day", rows)

        assert total == ingest.BATCH_SIZE + 1
        # BATCH_SIZE + 1 rows split into a full batch plus a remainder of one.
        sizes = [len(call.args[3]) for call in mock_batch.call_args_list]
        assert sizes == [ingest.BATCH_SIZE, 1]


# --- sync_all: orchestration, error handling, post-sync steps ---


class TestSyncAll:
    @staticmethod
    def _endpoint(name="ep_a"):
        from oura_ingest.endpoint import simple_endpoint

        return simple_endpoint(name, "day", lambda r: r)

    def test_unknown_endpoint_logs_and_returns(self, caplog):
        from oura_ingest import ingest

        engine, client = MagicMock(), MagicMock()
        with (
            patch.object(ingest, "ALL_ENDPOINTS", [self._endpoint("ep_a")]),
            patch.object(ingest, "sync_endpoint") as mock_sync,
            patch.object(ingest, "_SENTINEL_PATH"),
            caplog.at_level("ERROR"),
        ):
            ingest.sync_all(engine, client, only_endpoint="does_not_exist")

        mock_sync.assert_not_called()
        assert any("Unknown endpoint" in r.message for r in caplog.records)

    def test_happy_path_filters_endpoint_refreshes_view_and_touches_sentinel(self):
        from oura_ingest import ingest

        engine, client = MagicMock(), MagicMock()
        ep_a, ep_b = self._endpoint("ep_a"), self._endpoint("ep_b")
        with (
            patch.object(ingest, "ALL_ENDPOINTS", [ep_a, ep_b]),
            patch.object(ingest, "sync_endpoint", return_value=7) as mock_sync,
            patch.object(ingest, "_SENTINEL_PATH") as sentinel,
        ):
            ingest.sync_all(engine, client, only_endpoint="ep_b")

        # Only the filtered endpoint is synced.
        mock_sync.assert_called_once()
        assert mock_sync.call_args[0][2] is ep_b

        # The materialized view is refreshed concurrently after the sync.
        refresh_conn = engine.connect.return_value.execution_options.return_value.__enter__.return_value
        sql_texts = [str(c.args[0]) for c in refresh_conn.execute.call_args_list]
        assert any("REFRESH MATERIALIZED VIEW CONCURRENTLY sleep_primary" in s for s in sql_texts)

        # The healthcheck sentinel is written.
        sentinel.touch.assert_called_once()

    def test_token_expired_on_401_raises_token_expired_error(self):
        from oura_ingest import ingest
        from oura_ingest.ingest import TokenExpiredError

        engine, client = MagicMock(), MagicMock()
        http_401 = requests.HTTPError(response=Mock(status_code=401))
        with (
            patch.object(ingest, "ALL_ENDPOINTS", [self._endpoint("ep_a")]),
            patch.object(ingest, "sync_endpoint", side_effect=http_401),
            patch.object(ingest, "_SENTINEL_PATH"),
        ):
            with pytest.raises(TokenExpiredError):
                ingest.sync_all(engine, client)

    def test_oauth_error_raises_token_expired_error(self):
        """A failed OAuth refresh must stop syncing the same way an expired legacy token does."""
        from oura_ingest import ingest
        from oura_ingest.auth import OAuthError
        from oura_ingest.ingest import TokenExpiredError

        engine, client = MagicMock(), MagicMock()
        with (
            patch.object(ingest, "ALL_ENDPOINTS", [self._endpoint("ep_a")]),
            patch.object(ingest, "sync_endpoint", side_effect=OAuthError("invalid_grant")),
            patch.object(ingest, "_SENTINEL_PATH"),
        ):
            with pytest.raises(TokenExpiredError):
                ingest.sync_all(engine, client)

    def test_non_401_http_error_records_failure_then_continues_to_next_endpoint(self):
        from oura_ingest import ingest

        engine, client = MagicMock(), MagicMock()
        ep_a, ep_b = self._endpoint("ep_a"), self._endpoint("ep_b")
        http_500 = requests.HTTPError(response=Mock(status_code=500))
        with (
            patch.object(ingest, "ALL_ENDPOINTS", [ep_a, ep_b]),
            patch.object(ingest, "sync_endpoint", side_effect=[http_500, 3]) as mock_sync,
            patch.object(ingest, "_record_sync_failure") as mock_fail,
            patch.object(ingest, "_record_sync_history") as mock_hist,
            patch.object(ingest, "_SENTINEL_PATH"),
        ):
            ingest.sync_all(engine, client)

        # This guards the production `except requests.HTTPError` branch specifically (distinct
        # from the generic `except Exception` branch): a non-401 API error on one endpoint, after
        # retries are exhausted, must not short-circuit the remaining endpoints.
        assert [c.args[2] for c in mock_sync.call_args_list] == [ep_a, ep_b]
        mock_fail.assert_called_once()
        assert mock_fail.call_args[0][1] == "ep_a"
        assert mock_hist.call_args_list[0].args[4] == "error"

    def test_http_error_without_response_is_not_token_expiry(self):
        from oura_ingest import ingest

        engine, client = MagicMock(), MagicMock()
        http_none = requests.HTTPError(response=None)
        with (
            patch.object(ingest, "ALL_ENDPOINTS", [self._endpoint("ep_a")]),
            patch.object(ingest, "sync_endpoint", side_effect=http_none),
            patch.object(ingest, "_record_sync_failure") as mock_fail,
            patch.object(ingest, "_record_sync_history"),
            patch.object(ingest, "_SENTINEL_PATH"),
        ):
            ingest.sync_all(engine, client)  # must NOT raise TokenExpiredError

        mock_fail.assert_called_once()

    def test_generic_exception_records_failure_then_continues_to_next_endpoint(self):
        from oura_ingest import ingest

        engine, client = MagicMock(), MagicMock()
        ep_a, ep_b = self._endpoint("ep_a"), self._endpoint("ep_b")
        with (
            patch.object(ingest, "ALL_ENDPOINTS", [ep_a, ep_b]),
            patch.object(ingest, "sync_endpoint", side_effect=[RuntimeError("boom"), 3]) as mock_sync,
            patch.object(ingest, "_record_sync_failure") as mock_fail,
            patch.object(ingest, "_record_sync_history") as mock_hist,
            patch.object(ingest, "_SENTINEL_PATH") as sentinel,
        ):
            ingest.sync_all(engine, client)

        # A failure on the first endpoint must not skip the rest: both are attempted, in order.
        assert [c.args[2] for c in mock_sync.call_args_list] == [ep_a, ep_b]
        # Exactly one failure recorded, for the endpoint that raised.
        mock_fail.assert_called_once()
        assert mock_fail.call_args[0][1] == "ep_a"
        assert mock_hist.call_args_list[0].args[4] == "error"
        # Current policy (documented, not necessarily ideal): the healthcheck sentinel is
        # still refreshed after a partial failure.
        sentinel.touch.assert_called_once()

    def test_view_refresh_failure_is_swallowed(self, caplog):
        from oura_ingest import ingest

        engine, client = MagicMock(), MagicMock()
        engine.connect.return_value.execution_options.side_effect = Exception("db gone")
        with (
            patch.object(ingest, "ALL_ENDPOINTS", [self._endpoint("ep_a")]),
            patch.object(ingest, "sync_endpoint", return_value=1),
            patch.object(ingest, "_SENTINEL_PATH") as sentinel,
            caplog.at_level("WARNING"),
        ):
            ingest.sync_all(engine, client)

        assert any("Could not refresh" in r.message for r in caplog.records)
        # The sentinel is still written despite the view-refresh failure.
        sentinel.touch.assert_called_once()

    def test_sentinel_write_failure_is_swallowed(self):
        from oura_ingest import ingest

        engine, client = MagicMock(), MagicMock()
        with (
            patch.object(ingest, "ALL_ENDPOINTS", [self._endpoint("ep_a")]),
            patch.object(ingest, "sync_endpoint", return_value=1),
            patch.object(ingest, "_SENTINEL_PATH") as sentinel,
        ):
            sentinel.touch.side_effect = OSError("read-only fs")
            ingest.sync_all(engine, client)  # must not raise
