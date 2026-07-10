"""Tests for oura_ingest.cli (task 41)."""

import json
import signal
import threading
from datetime import date
from http.client import HTTPConnection
from http.server import HTTPServer
from unittest.mock import MagicMock, patch

import pytest


def _callback_server(callback_paths):
    """Return an HTTPServer factory that drives callback requests over localhost."""
    interaction = {
        "bound_address": None,
        "errors": [],
        "responses": [],
        "server": None,
        "thread": None,
    }

    def factory(address, handler_class):
        interaction["bound_address"] = address
        server = HTTPServer(("127.0.0.1", 0), handler_class)
        interaction["server"] = server

        def send_callbacks():
            try:
                for path in callback_paths:
                    connection = HTTPConnection("127.0.0.1", server.server_port, timeout=3)
                    try:
                        connection.request("GET", path)
                        response = connection.getresponse()
                        interaction["responses"].append((response.status, response.read().decode()))
                    finally:
                        connection.close()
            except Exception as exc:
                interaction["errors"].append(exc)

        thread = threading.Thread(target=send_callbacks, daemon=True)
        interaction["thread"] = thread
        thread.start()
        return server

    return factory, interaction


def _assert_callback_completed(interaction):
    interaction["thread"].join(timeout=3)
    assert not interaction["thread"].is_alive()
    assert interaction["errors"] == []
    assert interaction["server"].socket.fileno() == -1


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

    def test_callback_exchanges_code_and_persists_tokens(self, tmp_path, monkeypatch, capsys):
        from oura_ingest import cli
        from oura_ingest.auth import OAuthToken

        env_file = tmp_path / ".env"
        env_file.write_text("POSTGRES_DB=oura\n")
        monkeypatch.delenv("OURA_CLIENT_ID", raising=False)
        monkeypatch.delenv("OURA_CLIENT_SECRET", raising=False)
        monkeypatch.setenv("OURA_REDIRECT_URI", "http://localhost:9123/callback")
        monkeypatch.setenv("OURA_OAUTH_SCOPES", "daily heartrate")

        input_prompt = MagicMock(return_value=" client-id ")
        secret_prompt = MagicMock(return_value=" client-secret ")
        find_env_file = MagicMock(return_value=env_file)
        exchange_code = MagicMock(
            return_value=OAuthToken(
                access_token="access-token",
                refresh_token="refresh-token",
                expires_at=1_700_000_000,
            )
        )
        smoke_test = MagicMock(return_value=4)
        server_factory, interaction = _callback_server(["/not-callback", "/callback?code=grant-code&state=test-state"])

        monkeypatch.setattr("builtins.input", input_prompt)
        monkeypatch.setattr(cli.getpass, "getpass", secret_prompt)
        monkeypatch.setattr(cli.secrets, "token_urlsafe", MagicMock(return_value="test-state"))
        monkeypatch.setattr(cli, "find_env_file", find_env_file)
        monkeypatch.setattr(cli, "exchange_authorization_code", exchange_code)
        monkeypatch.setattr(cli, "_test_token", smoke_test)
        monkeypatch.setattr(cli, "HTTPServer", server_factory)
        monkeypatch.setattr(cli, "OAUTH_TIMEOUT_SECONDS", 2)

        assert cli._run_oauth_setup(None, "127.0.0.1", 8765) == 0
        _assert_callback_completed(interaction)

        assert interaction["bound_address"] == ("127.0.0.1", 9123)
        assert interaction["responses"][0] == (404, "")
        assert interaction["responses"][1][0] == 200
        assert "Oura OAuth succeeded" in interaction["responses"][1][1]
        exchange_code.assert_called_once_with(
            client_id="client-id",
            client_secret="client-secret",
            code="grant-code",
            redirect_uri="http://localhost:9123/callback",
        )
        smoke_test.assert_called_once_with("access-token")
        find_env_file.assert_called_once_with()

        saved_lines = set(env_file.read_text().splitlines())
        assert {
            "POSTGRES_DB=oura",
            "OURA_CLIENT_ID=client-id",
            "OURA_CLIENT_SECRET=client-secret",
            "OURA_REFRESH_TOKEN=refresh-token",
            "OURA_ACCESS_TOKEN=access-token",
            "OURA_ACCESS_TOKEN_EXPIRES_AT=1700000000",
            "OURA_REDIRECT_URI=http://localhost:9123/callback",
            "OURA_OAUTH_SCOPES=daily heartrate",
        } <= saved_lines

        captured = capsys.readouterr()
        assert "state=test-state" in captured.out
        result = json.loads(captured.out.strip().splitlines()[-1])
        assert result == {
            "daily_sleep_records": 4,
            "env_file": str(env_file),
            "ok": True,
        }

    def test_callback_keeps_saved_tokens_when_smoke_test_fails(self, tmp_path, monkeypatch, capsys):
        from oura_ingest import cli
        from oura_ingest.auth import OAuthToken

        env_file = tmp_path / "oauth.env"
        monkeypatch.setenv("OURA_CLIENT_ID", "client-id")
        monkeypatch.setenv("OURA_CLIENT_SECRET", "client-secret")
        monkeypatch.delenv("OURA_REDIRECT_URI", raising=False)
        monkeypatch.setenv("OURA_OAUTH_SCOPES", "daily")
        monkeypatch.setattr(cli.secrets, "token_urlsafe", MagicMock(return_value="test-state"))
        monkeypatch.setattr(
            cli,
            "exchange_authorization_code",
            MagicMock(return_value=OAuthToken("saved-access", None, None)),
        )

        def failing_smoke_test(access_token):
            assert access_token == "saved-access"
            assert "OURA_ACCESS_TOKEN=saved-access" in env_file.read_text()
            raise RuntimeError("temporary API outage")

        server_factory, interaction = _callback_server(["/callback?code=grant-code&state=test-state"])
        monkeypatch.setattr(cli, "_test_token", failing_smoke_test)
        monkeypatch.setattr(cli, "HTTPServer", server_factory)
        monkeypatch.setattr(cli, "OAUTH_TIMEOUT_SECONDS", 2)

        assert cli._run_oauth_setup(str(env_file), "127.0.0.1", 8765) == 0
        _assert_callback_completed(interaction)

        saved_lines = set(env_file.read_text().splitlines())
        assert "OURA_ACCESS_TOKEN=saved-access" in saved_lines
        assert "OURA_REFRESH_TOKEN=" in saved_lines
        assert "OURA_ACCESS_TOKEN_EXPIRES_AT=" in saved_lines
        result = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
        assert result["warning"] == "tokens saved but API test failed: temporary API outage"
        assert "daily_sleep_records" not in result

    @pytest.mark.parametrize(
        ("callback_path", "expected_error", "browser_message"),
        [
            ("/callback?error=access_denied&state=test-state", "access_denied", "Oura OAuth failed."),
            ("/callback?state=test-state", "missing_code", "Oura OAuth failed."),
            (
                "/callback?code=grant-code&state=wrong-state",
                "state_mismatch",
                "Oura OAuth failed (state mismatch).",
            ),
        ],
    )
    def test_callback_rejects_oauth_errors(self, callback_path, expected_error, browser_message, monkeypatch, capsys):
        from oura_ingest import cli

        monkeypatch.setenv("OURA_CLIENT_ID", "client-id")
        monkeypatch.setenv("OURA_CLIENT_SECRET", "client-secret")
        monkeypatch.setenv("OURA_OAUTH_SCOPES", "daily")
        monkeypatch.delenv("OURA_REDIRECT_URI", raising=False)
        exchange_code = MagicMock()
        server_factory, interaction = _callback_server([callback_path])
        monkeypatch.setattr(cli.secrets, "token_urlsafe", MagicMock(return_value="test-state"))
        monkeypatch.setattr(cli, "exchange_authorization_code", exchange_code)
        monkeypatch.setattr(cli, "HTTPServer", server_factory)
        monkeypatch.setattr(cli, "OAUTH_TIMEOUT_SECONDS", 2)

        assert cli._run_oauth_setup("unused.env", "127.0.0.1", 8765) == 1
        _assert_callback_completed(interaction)

        exchange_code.assert_not_called()
        assert interaction["responses"][0][0] == 200
        assert browser_message in interaction["responses"][0][1]
        assert f"ERROR: {expected_error}" in capsys.readouterr().err

    def test_callback_reports_token_exchange_error(self, monkeypatch, capsys):
        from oura_ingest import cli
        from oura_ingest.auth import OAuthError

        monkeypatch.setenv("OURA_CLIENT_ID", "client-id")
        monkeypatch.setenv("OURA_CLIENT_SECRET", "client-secret")
        monkeypatch.setenv("OURA_OAUTH_SCOPES", "daily")
        monkeypatch.delenv("OURA_REDIRECT_URI", raising=False)
        update_env_file = MagicMock()
        server_factory, interaction = _callback_server(["/callback?code=used-code&state=test-state"])
        monkeypatch.setattr(cli.secrets, "token_urlsafe", MagicMock(return_value="test-state"))
        monkeypatch.setattr(
            cli,
            "exchange_authorization_code",
            MagicMock(side_effect=OAuthError("authorization code was rejected")),
        )
        monkeypatch.setattr(cli, "update_env_file", update_env_file)
        monkeypatch.setattr(cli, "HTTPServer", server_factory)
        monkeypatch.setattr(cli, "OAUTH_TIMEOUT_SECONDS", 2)

        assert cli._run_oauth_setup("unused.env", "127.0.0.1", 8765) == 1
        _assert_callback_completed(interaction)

        update_env_file.assert_not_called()
        assert interaction["responses"][0][0] == 200
        assert "Oura OAuth token exchange failed" in interaction["responses"][0][1]
        assert "ERROR: authorization code was rejected" in capsys.readouterr().err

    def test_oauth_setup_times_out_and_closes_server(self, monkeypatch, capsys):
        from oura_ingest import cli

        monkeypatch.setenv("OURA_CLIENT_ID", "client-id")
        monkeypatch.setenv("OURA_CLIENT_SECRET", "client-secret")
        monkeypatch.setenv("OURA_OAUTH_SCOPES", "daily")
        monkeypatch.delenv("OURA_REDIRECT_URI", raising=False)
        server = MagicMock()
        server_factory = MagicMock(return_value=server)
        monkeypatch.setattr(cli.secrets, "token_urlsafe", MagicMock(return_value="test-state"))
        monkeypatch.setattr(cli, "HTTPServer", server_factory)
        monkeypatch.setattr(cli.time, "time", MagicMock(side_effect=[100.0, 101.0, 701.0]))

        assert cli._run_oauth_setup("unused.env", "0.0.0.0", 8765) == 1

        bound_address, handler_class = server_factory.call_args.args
        assert bound_address == ("0.0.0.0", 8765)
        assert handler_class.__name__ == "OAuthCallbackHandler"
        assert server.timeout == 599.0
        server.handle_request.assert_called_once_with()
        server.server_close.assert_called_once_with()
        assert "ERROR: OAuth setup timed out." in capsys.readouterr().err


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


class TestOAuthStartup:
    def test_uses_postgres_store_for_persisted_oauth_state(self):
        from oura_ingest import cli

        engine = MagicMock()
        token_store = MagicMock()
        token_provider = MagicMock()
        client = MagicMock()
        mock_cfg = MagicMock()
        mock_cfg.OURA_CLIENT_ID = "client-id"
        mock_cfg.OURA_CLIENT_SECRET = "client-secret"

        with (
            patch("sys.argv", ["cli", "--once"]),
            patch.object(cli, "_load_ingestion_dependencies"),
            patch.object(cli, "wait_for_db", return_value=engine),
            patch.object(cli, "cfg", mock_cfg),
            patch.object(cli, "EnvTokenProvider", return_value=token_provider) as provider_factory,
            patch.object(cli, "OuraClient", return_value=client) as client_factory,
            patch.object(cli, "sync_all") as mock_sync,
            patch("oura_ingest.token_store.PostgresOAuthTokenStore", return_value=token_store) as store_factory,
            patch.object(cli.signal, "signal"),
        ):
            cli.main()

        mock_cfg.validate.assert_called_once_with()
        store_factory.assert_called_once_with(engine, "client-secret")
        provider_factory.assert_called_once_with(config=mock_cfg, token_store=token_store)
        client_factory.assert_called_once_with(token_provider=token_provider)
        mock_sync.assert_called_once_with(engine, client, only_endpoint=None)

    def test_returns_when_persisted_oauth_state_cannot_initialize(self):
        from oura_ingest import cli
        from oura_ingest.auth import OAuthError

        engine = MagicMock()
        error = OAuthError("persisted token is unreadable")
        mock_cfg = MagicMock()
        mock_cfg.OURA_CLIENT_ID = ""
        mock_cfg.OURA_CLIENT_SECRET = ""
        logger = MagicMock()

        with (
            patch("sys.argv", ["cli", "--once"]),
            patch.object(cli, "_load_ingestion_dependencies"),
            patch.object(cli, "wait_for_db", return_value=engine),
            patch.object(cli, "cfg", mock_cfg),
            patch.object(cli, "EnvTokenProvider", side_effect=error) as provider_factory,
            patch.object(cli, "OuraClient") as client_factory,
            patch.object(cli, "sync_all") as mock_sync,
            patch.object(cli, "log", logger),
            patch.object(cli.signal, "signal"),
        ):
            cli.main()

        provider_factory.assert_called_once_with(config=mock_cfg, token_store=None)
        client_factory.assert_not_called()
        mock_sync.assert_not_called()
        logger.critical.assert_called_once_with("Could not initialize persisted OAuth state: %s", error)


class TestShutdown:
    def test_sets_stop_event(self):
        from oura_ingest.cli import _shutdown, _stop

        _stop.clear()
        try:
            _shutdown(signal.SIGTERM, None)
            assert _stop.is_set()
        finally:
            _stop.clear()


def test_token_smoke_test_uses_local_date():
    from oura_ingest import cli

    client = MagicMock()
    client.fetch_all.return_value = iter(())
    with (
        patch.object(cli, "_load_ingestion_dependencies"),
        patch.object(cli, "OuraClient", return_value=client),
        patch.object(cli, "cfg") as mock_cfg,
    ):
        mock_cfg.local_date.return_value = date(2025, 1, 8)

        assert cli._test_token("access-token") == 0

    client.fetch_all.assert_called_once_with("daily_sleep", "2025-01-01", "2025-01-08")


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
