"""Tests for oura_ingest.cli (task 41)."""

from unittest.mock import MagicMock, patch


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
