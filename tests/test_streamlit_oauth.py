import time
from unittest.mock import patch

from data.oauth import build_authorization_url, get_env_oauth_access_token


def test_authorization_url_uses_public_oura_endpoint():
    url = build_authorization_url("client-id", "http://localhost:8765/callback", "daily")

    assert url.startswith("https://cloud.ouraring.com/oauth/authorize?")


def test_valid_cached_access_token_does_not_require_refresh(monkeypatch):
    monkeypatch.setenv("OURA_ACCESS_TOKEN", "cached-access")
    monkeypatch.setenv("OURA_ACCESS_TOKEN_EXPIRES_AT", str(int(time.time()) + 3600))

    with patch("data.oauth.refresh_access_token") as refresh:
        assert get_env_oauth_access_token(allow_refresh=False) == "cached-access"

    refresh.assert_not_called()


def test_refresh_can_be_disabled_for_database_mode(monkeypatch):
    monkeypatch.setenv("OURA_CLIENT_ID", "client-id")
    monkeypatch.setenv("OURA_CLIENT_SECRET", "client-secret")
    monkeypatch.setenv("OURA_REFRESH_TOKEN", "single-use-refresh")
    monkeypatch.setenv("OURA_ACCESS_TOKEN_EXPIRES_AT", "1")

    with patch("data.oauth.refresh_access_token") as refresh:
        assert get_env_oauth_access_token(allow_refresh=False) is None

    refresh.assert_not_called()
