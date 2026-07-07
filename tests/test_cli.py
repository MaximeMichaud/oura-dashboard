"""Tests for oura_ingest.cli (task 41)."""

import signal
from unittest.mock import MagicMock, patch

import pytest


class TestListEndpoints:
    def test_prints_endpoint_names(self, capsys):
        with patch("sys.argv", ["cli", "--list-endpoints"]):
            from oura_ingest.cli import main

            main()

        captured = capsys.readouterr()
        assert "daily_sleep" in captured.out
        assert "daily_activity" in captured.out
        assert "daily_readiness" in captured.out
        assert "sleep" in captured.out


class TestOAuthSetup:
    def test_oauth_setup_dispatches_to_helper(self):
        with (
            patch(
                "sys.argv",
                ["cli", "--oauth-setup", "--oauth-host", "0.0.0.0", "--oauth-port", "9999", "--env-file", ".env"],
            ),
            patch("oura_ingest.cli._run_oauth_setup", return_value=0) as mock_setup,
        ):
            from oura_ingest.cli import main

            with pytest.raises(SystemExit) as exc:
                main()

        assert exc.value.code == 0
        mock_setup.assert_called_once_with(".env", "0.0.0.0", 9999)


class TestOnceFlag:
    def test_exits_after_sync(self):
        mock_engine = MagicMock()
        mock_client = MagicMock()

        with (
            patch("sys.argv", ["cli", "--once"]),
            patch("oura_ingest.cli.wait_for_db", return_value=mock_engine),
            patch("oura_ingest.cli.OuraClient", return_value=mock_client),
            patch("oura_ingest.cli.sync_all") as mock_sync,
            patch("oura_ingest.cli.cfg") as mock_cfg,
        ):
            mock_cfg.validate = MagicMock()
            from oura_ingest.cli import main

            main()

        mock_sync.assert_called_once_with(mock_engine, mock_client, only_endpoint=None)

    def test_with_endpoint_filter(self):
        mock_engine = MagicMock()
        mock_client = MagicMock()

        with (
            patch("sys.argv", ["cli", "--once", "--endpoint", "daily_sleep"]),
            patch("oura_ingest.cli.wait_for_db", return_value=mock_engine),
            patch("oura_ingest.cli.OuraClient", return_value=mock_client),
            patch("oura_ingest.cli.sync_all") as mock_sync,
            patch("oura_ingest.cli.cfg") as mock_cfg,
        ):
            mock_cfg.validate = MagicMock()
            from oura_ingest.cli import main

            main()

        mock_sync.assert_called_once_with(mock_engine, mock_client, only_endpoint="daily_sleep")


class TestShutdown:
    def test_sets_stop_event(self):
        from oura_ingest.cli import _shutdown, _stop

        _stop.clear()
        try:
            _shutdown(signal.SIGTERM, None)
            assert _stop.is_set()
        finally:
            _stop.clear()


class TestInitialSyncTokenExpired:
    def test_returns_without_scheduling(self):
        from oura_ingest.cli import main
        from oura_ingest.ingest import TokenExpiredError

        with (
            patch("sys.argv", ["cli"]),
            patch("oura_ingest.cli.wait_for_db", return_value=MagicMock()),
            patch("oura_ingest.cli.OuraClient", return_value=MagicMock()),
            patch("oura_ingest.cli.sync_all", side_effect=TokenExpiredError("bad token")),
            patch("oura_ingest.cli.schedule") as mock_sched,
            patch("oura_ingest.cli.cfg") as mock_cfg,
            patch("signal.signal"),
        ):
            mock_cfg.validate = MagicMock()
            main()  # returns cleanly instead of raising

        # Token expiry on the initial sync must abort before scheduling anything.
        mock_sched.every.assert_not_called()


class TestScheduler:
    def test_sets_up_schedule_and_runs_loop(self):
        from oura_ingest.cli import main
        from oura_ingest.ingest import TokenExpiredError

        engine, client = MagicMock(), MagicMock()
        fake_stop = MagicMock()
        # Enter the loop body once, then exit on the second check.
        fake_stop.is_set.side_effect = [False, True]
        captured = []

        with (
            patch("sys.argv", ["cli"]),
            patch("oura_ingest.cli.wait_for_db", return_value=engine),
            patch("oura_ingest.cli.OuraClient", return_value=client),
            patch("oura_ingest.cli.sync_all") as mock_sync,
            patch("oura_ingest.cli.cfg") as mock_cfg,
            patch("oura_ingest.cli._stop", fake_stop),
            patch("oura_ingest.cli.schedule") as mock_sched,
            patch("signal.signal"),
        ):
            mock_cfg.validate = MagicMock()
            mock_cfg.SYNC_INTERVAL_MINUTES = 30
            mock_sched.every.return_value.minutes.do.side_effect = lambda fn: captured.append(fn)

            main()

            # Initial sync ran and the periodic job was wired with the configured interval.
            assert mock_sync.call_count == 1
            mock_sched.every.assert_called_once_with(30)
            mock_sched.run_pending.assert_called_once()
            fake_stop.wait.assert_called_once_with(timeout=10)

            # The scheduled job's happy path triggers another sync.
            assert captured, "scheduler callback was not registered"
            job = captured[0]
            job()
            assert mock_sync.call_count == 2

            # The scheduled job stops the scheduler when the token expires mid-run.
            mock_sync.side_effect = TokenExpiredError("expired mid-run")
            job()
            fake_stop.set.assert_called_once()
