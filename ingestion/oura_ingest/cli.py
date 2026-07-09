import argparse
import getpass
import json
import logging
import os
import secrets
import signal
import sys
import threading
import time
from datetime import date, timedelta
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .auth import (
    EnvTokenProvider,
    OAuthError,
    build_authorization_url,
    exchange_authorization_code,
    find_env_file,
    update_env_file,
)
from .config import cfg

log = logging.getLogger(__name__)

OAUTH_TIMEOUT_SECONDS = 600

_stop = threading.Event()
OuraClient = None
wait_for_db = None
ALL_ENDPOINTS = None
TokenExpiredError = None
sync_all = None
schedule = None


def _load_ingestion_dependencies():
    global ALL_ENDPOINTS, OuraClient, TokenExpiredError, schedule, sync_all, wait_for_db

    if OuraClient is None:
        from .api_client import OuraClient as _OuraClient

        OuraClient = _OuraClient
    if wait_for_db is None:
        from .db import wait_for_db as _wait_for_db

        wait_for_db = _wait_for_db
    if ALL_ENDPOINTS is None:
        from .endpoints import ALL_ENDPOINTS as _ALL_ENDPOINTS

        ALL_ENDPOINTS = _ALL_ENDPOINTS
    if TokenExpiredError is None:
        from .ingest import TokenExpiredError as _TokenExpiredError

        TokenExpiredError = _TokenExpiredError
    if sync_all is None:
        from .ingest import sync_all as _sync_all

        sync_all = _sync_all
    if schedule is None:
        import schedule as _schedule

        schedule = _schedule


def _shutdown(signum, frame):
    log.info("Received signal %d, shutting down...", signum)
    _stop.set()


def _test_token(access_token: str) -> int:
    _load_ingestion_dependencies()
    start = (date.today() - timedelta(days=7)).isoformat()
    end = date.today().isoformat()
    return len(list(OuraClient(token=access_token).fetch_all("daily_sleep", start, end)))


def _run_oauth_setup(env_file: str | None, host: str, port: int) -> int:
    client_id = os.environ.get("OURA_CLIENT_ID") or input("Oura client ID: ").strip()
    client_secret = os.environ.get("OURA_CLIENT_SECRET") or getpass.getpass("Oura client secret: ").strip()
    # Honour a user-registered redirect URI; only fall back to the local default.
    redirect_uri = os.environ.get("OURA_REDIRECT_URI") or f"http://localhost:{port}/callback"
    bind_port = urlparse(redirect_uri).port or port
    scopes = os.environ.get("OURA_OAUTH_SCOPES", cfg.OURA_OAUTH_SCOPES)
    state = secrets.token_urlsafe(24)
    result: dict[str, object] = {}

    class OAuthCallbackHandler(BaseHTTPRequestHandler):
        def log_message(self, format, *args):
            return

        def do_GET(self):
            parsed = urlparse(self.path)
            if parsed.path != "/callback":
                self.send_response(404)
                self.end_headers()
                return

            params = parse_qs(parsed.query)
            code = (params.get("code") or [""])[0]
            error = (params.get("error") or [""])[0]
            returned_state = (params.get("state") or [""])[0]
            if error or not code:
                result.update({"ok": False, "error": error or "missing_code"})
                message = "Oura OAuth failed. You can close this tab."
            elif returned_state != state:
                result.update({"ok": False, "error": "state_mismatch"})
                message = "Oura OAuth failed (state mismatch). You can close this tab."
            else:
                try:
                    token = exchange_authorization_code(
                        client_id=client_id,
                        client_secret=client_secret,
                        code=code,
                        redirect_uri=redirect_uri,
                    )
                    env_path = find_env_file() if env_file is None else Path(env_file)
                    # Persist the freshly issued tokens BEFORE the API smoke test so a
                    # transient test failure never discards a valid, already-consumed grant.
                    update_env_file(
                        env_path,
                        {
                            "OURA_CLIENT_ID": client_id,
                            "OURA_CLIENT_SECRET": client_secret,
                            "OURA_REFRESH_TOKEN": token.refresh_token or "",
                            "OURA_ACCESS_TOKEN": token.access_token,
                            "OURA_ACCESS_TOKEN_EXPIRES_AT": str(token.expires_at or ""),
                            "OURA_REDIRECT_URI": redirect_uri,
                            "OURA_OAUTH_SCOPES": scopes,
                        },
                    )
                    result.update({"ok": True, "env_file": str(env_path)})
                    try:
                        result["daily_sleep_records"] = _test_token(token.access_token)
                    except Exception as exc:
                        result["warning"] = f"tokens saved but API test failed: {exc}"
                    message = "Oura OAuth succeeded. You can close this tab."
                except Exception as exc:
                    result.update({"ok": False, "error": str(exc)})
                    message = "Oura OAuth token exchange failed. You can close this tab."

            payload = f"<html><body><h1>{message}</h1></body></html>".encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

    auth_url = build_authorization_url(client_id, redirect_uri, scopes, state=state)
    print("Open this URL in your browser and approve access:")
    print(auth_url)
    print(f"Waiting for OAuth callback on {redirect_uri} ...")

    server = HTTPServer((host, bind_port), OAuthCallbackHandler)
    deadline = time.time() + OAUTH_TIMEOUT_SECONDS
    try:
        while not result:
            remaining = deadline - time.time()
            if remaining <= 0:
                break
            server.timeout = remaining
            server.handle_request()
    finally:
        server.server_close()

    if not result:
        print("ERROR: OAuth setup timed out.", file=sys.stderr)
        return 1
    if not result.get("ok"):
        print(f"ERROR: {result.get('error')}", file=sys.stderr)
        return 1

    print("OAuth setup completed.")
    print(json.dumps(result, sort_keys=True))
    return 0


def main():
    parser = argparse.ArgumentParser(description="Oura ingestion service")
    parser.add_argument("--endpoint", help="Sync only this endpoint name")
    parser.add_argument("--once", action="store_true", help="Sync once and exit (no scheduler)")
    parser.add_argument("--list-endpoints", action="store_true", help="Print available endpoints and exit")
    parser.add_argument("--oauth-setup", action="store_true", help="Run local Oura OAuth setup and update .env")
    parser.add_argument("--oauth-host", default="127.0.0.1", help="Local OAuth callback bind host")
    parser.add_argument("--oauth-port", type=int, default=8765, help="Local OAuth callback port")
    parser.add_argument("--env-file", help="Path to .env file for --oauth-setup")
    args = parser.parse_args()

    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    )

    if args.list_endpoints:
        _load_ingestion_dependencies()
        for ep in ALL_ENDPOINTS:
            print(ep.name)
        return

    if args.oauth_setup:
        raise SystemExit(_run_oauth_setup(args.env_file, args.oauth_host, args.oauth_port))

    _load_ingestion_dependencies()

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    cfg.validate()

    log.info("Oura ingestion starting")
    engine = wait_for_db()
    token_store = None
    oauth_client = (cfg.OURA_CLIENT_ID, cfg.OURA_CLIENT_SECRET)
    if all(isinstance(value, str) and value for value in oauth_client):
        from .token_store import PostgresOAuthTokenStore

        token_store = PostgresOAuthTokenStore(engine, cfg.OURA_CLIENT_SECRET)
    try:
        client = OuraClient(token_provider=EnvTokenProvider(config=cfg, token_store=token_store))
    except OAuthError as exc:
        log.critical("Could not initialize persisted OAuth state: %s", exc)
        return

    # Initial sync
    log.info("Running initial sync...")
    try:
        sync_all(engine, client, only_endpoint=args.endpoint)
    except TokenExpiredError:
        log.critical("Exiting due to invalid Oura token. Refresh your OURA_TOKEN and restart.")
        return

    if args.once:
        log.info("--once flag set, exiting after initial sync")
        return

    # Schedule periodic sync
    interval = cfg.SYNC_INTERVAL_MINUTES
    log.info("Scheduling sync every %d minutes", interval)

    def _safe_sync():
        try:
            sync_all(engine, client, only_endpoint=args.endpoint)
        except TokenExpiredError:
            log.critical("Oura token expired during scheduled sync. Stopping scheduler.")
            _stop.set()

    schedule.every(interval).minutes.do(_safe_sync)

    while not _stop.is_set():
        schedule.run_pending()
        _stop.wait(timeout=10)

    log.info("Shutdown complete")


if __name__ == "__main__":
    main()
