import time

import pytest
from oura_ingest.auth import (
    EnvTokenProvider,
    OAuthError,
    StaticTokenProvider,
    _post_token,
    build_authorization_url,
    exchange_authorization_code,
    extract_authorization_code,
    find_env_file,
    refresh_access_token,
    update_env_file,
)
from oura_ingest.config import Config


class _JsonSession:
    """Fake requests session whose token endpoint returns a fixed JSON body."""

    def __init__(self, body, *, ok=True, status_code=200):
        self._body = body
        self._ok = ok
        self._status_code = status_code
        self.posts = 0
        self.requests = []

    def post(self, url, data, timeout):
        self.posts += 1
        self.requests.append({"url": url, "data": data, "timeout": timeout})
        body = self._body

        class Response:
            def json(self):
                if isinstance(body, Exception):
                    raise body
                return body

        response = Response()
        response.ok = self._ok
        response.status_code = self._status_code
        return response


class _TokenStore:
    def __init__(self, state=None, save_error=None, load_error=None):
        self.state = state
        self.save_error = save_error
        self.load_error = load_error
        self.saved = None
        self.save_calls = 0

    def load(self):
        if self.load_error:
            raise self.load_error
        return self.state

    def save(self, payload):
        self.save_calls += 1
        if self.save_error:
            raise self.save_error
        self.saved = payload


def test_build_authorization_url():
    url = build_authorization_url("client-id", "http://localhost:8765/callback", "daily workout")
    assert url.startswith("https://cloud.ouraring.com/oauth/authorize?")
    assert "client_id=client-id" in url
    assert "response_type=code" in url
    assert "scope=daily+workout" in url


def test_static_token_provider_returns_the_same_token_when_refresh_is_forced():
    provider = StaticTokenProvider("legacy-token")

    assert provider.can_refresh is False
    assert provider.get_token() == "legacy-token"
    assert provider.get_token(force_refresh=True) == "legacy-token"


def test_extract_authorization_code_from_callback_url():
    code = extract_authorization_code("http://localhost:8765/callback?iss=x&code=abc123")
    assert code == "abc123"


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("  ", ""),
        (" direct-code ", "direct-code"),
        ("https://localhost/callback?state=known", ""),
    ],
)
def test_extract_authorization_code_handles_manual_and_missing_values(value, expected):
    assert extract_authorization_code(value) == expected


def test_exchange_authorization_code_posts_expected_payload(monkeypatch):
    monkeypatch.setattr("oura_ingest.auth.time.time", lambda: 1_000)
    session = _JsonSession(
        {
            "access_token": "access-token",
            "refresh_token": "refresh-token",
            "expires_in": "600",
            "scope": "daily workout",
        }
    )

    token = exchange_authorization_code(
        client_id="client-id",
        client_secret="client-secret",
        code="authorization-code",
        redirect_uri="http://localhost:8765/callback",
        session=session,
    )

    assert token.access_token == "access-token"
    assert token.refresh_token == "refresh-token"
    assert token.expires_at == 1_600
    assert token.scope == "daily workout"
    assert session.requests == [
        {
            "url": "https://api.ouraring.com/oauth/token",
            "data": {
                "grant_type": "authorization_code",
                "code": "authorization-code",
                "client_id": "client-id",
                "client_secret": "client-secret",
                "redirect_uri": "http://localhost:8765/callback",
            },
            "timeout": 30,
        }
    ]


def test_refresh_access_token_posts_expected_payload_and_ignores_invalid_expiry():
    session = _JsonSession({"access_token": "access-token", "expires_in": "not-a-number"})

    token = refresh_access_token(
        client_id="client-id",
        client_secret="client-secret",
        refresh_token="refresh-token",
        session=session,
    )

    assert token.access_token == "access-token"
    assert token.refresh_token is None
    assert token.expires_at is None
    assert session.requests[0] == {
        "url": "https://api.ouraring.com/oauth/token",
        "data": {
            "grant_type": "refresh_token",
            "client_id": "client-id",
            "client_secret": "client-secret",
            "refresh_token": "refresh-token",
        },
        "timeout": 30,
    }


def test_update_env_file_preserves_legacy_token(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("OURA_TOKEN=legacy-token\nPOSTGRES_DB=oura\n")

    update_env_file(env_file, {"OURA_CLIENT_ID": "client-id", "OURA_REFRESH_TOKEN": "refresh-token"})

    content = env_file.read_text()
    assert "OURA_TOKEN=legacy-token" in content
    assert "POSTGRES_DB=oura" in content
    assert "OURA_CLIENT_ID=client-id" in content
    assert "OURA_REFRESH_TOKEN=refresh-token" in content


def test_env_token_provider_prefers_legacy_token(monkeypatch):
    monkeypatch.setenv("OURA_TOKEN", "legacy-token")
    monkeypatch.setenv("OURA_CLIENT_ID", "client-id")
    monkeypatch.setenv("OURA_CLIENT_SECRET", "client-secret")
    monkeypatch.setenv("OURA_REFRESH_TOKEN", "refresh-token")

    provider = EnvTokenProvider(config=Config())

    assert provider.get_token() == "legacy-token"
    assert provider.can_refresh is True


def test_env_token_provider_keeps_legacy_token_when_oauth_refresh_is_unavailable(monkeypatch):
    monkeypatch.setenv("OURA_TOKEN", "legacy-token")
    monkeypatch.delenv("OURA_CLIENT_ID", raising=False)
    monkeypatch.delenv("OURA_CLIENT_SECRET", raising=False)
    monkeypatch.delenv("OURA_REFRESH_TOKEN", raising=False)
    monkeypatch.delenv("OURA_ACCESS_TOKEN", raising=False)

    provider = EnvTokenProvider(config=Config())

    assert provider.can_refresh is False
    assert provider.get_token(force_refresh=True) == "legacy-token"


def test_env_token_provider_rejects_missing_authentication(monkeypatch):
    for key in (
        "OURA_TOKEN",
        "OURA_CLIENT_ID",
        "OURA_CLIENT_SECRET",
        "OURA_REFRESH_TOKEN",
        "OURA_ACCESS_TOKEN",
        "OURA_ACCESS_TOKEN_EXPIRES_AT",
    ):
        monkeypatch.delenv(key, raising=False)

    provider = EnvTokenProvider(config=Config())

    with pytest.raises(OAuthError, match="refresh token is not configured"):
        provider.get_token()


def test_env_token_provider_uses_cached_oauth_token(monkeypatch):
    monkeypatch.delenv("OURA_TOKEN", raising=False)
    monkeypatch.setenv("OURA_CLIENT_ID", "client-id")
    monkeypatch.setenv("OURA_CLIENT_SECRET", "client-secret")
    monkeypatch.setenv("OURA_REFRESH_TOKEN", "refresh-token")
    monkeypatch.setenv("OURA_ACCESS_TOKEN", "access-token")
    monkeypatch.setenv("OURA_ACCESS_TOKEN_EXPIRES_AT", str(int(time.time()) + 3600))

    provider = EnvTokenProvider(config=Config())

    assert provider.get_token() == "access-token"
    assert provider.can_refresh is True


def test_env_token_provider_refreshes_expired_oauth_token(monkeypatch):
    monkeypatch.delenv("OURA_TOKEN", raising=False)
    monkeypatch.setenv("OURA_CLIENT_ID", "client-id")
    monkeypatch.setenv("OURA_CLIENT_SECRET", "client-secret")
    monkeypatch.setenv("OURA_REFRESH_TOKEN", "refresh-token")
    monkeypatch.setenv("OURA_ACCESS_TOKEN", "old-token")
    monkeypatch.setenv("OURA_ACCESS_TOKEN_EXPIRES_AT", "1")

    class Session:
        def post(self, url, data, timeout):
            class Response:
                ok = True

                def json(self):
                    return {
                        "access_token": "new-token",
                        "refresh_token": "new-refresh-token",
                        "expires_in": 3600,
                    }

            return Response()

    provider = EnvTokenProvider(config=Config(), session=Session())

    assert provider.get_token() == "new-token"
    assert provider.config.OURA_REFRESH_TOKEN == "new-refresh-token"


def test_env_token_provider_restores_persisted_oauth_state(monkeypatch):
    monkeypatch.delenv("OURA_TOKEN", raising=False)
    monkeypatch.setenv("OURA_CLIENT_ID", "client-id")
    monkeypatch.setenv("OURA_CLIENT_SECRET", "client-secret")
    monkeypatch.setenv("OURA_REFRESH_TOKEN", "stale-refresh")
    store = _TokenStore(
        {
            "access_token": "persisted-access",
            "refresh_token": "persisted-refresh",
            "expires_at": int(time.time()) + 3600,
            "scope": "daily",
        }
    )

    provider = EnvTokenProvider(config=Config(), token_store=store)

    assert provider.get_token() == "persisted-access"
    assert provider.config.OURA_REFRESH_TOKEN == "persisted-refresh"


def test_env_token_provider_keeps_newer_oauth_bootstrap(monkeypatch):
    monkeypatch.delenv("OURA_TOKEN", raising=False)
    monkeypatch.setenv("OURA_CLIENT_ID", "client-id")
    monkeypatch.setenv("OURA_CLIENT_SECRET", "client-secret")
    monkeypatch.setenv("OURA_REFRESH_TOKEN", "new-bootstrap-refresh")
    monkeypatch.setenv("OURA_ACCESS_TOKEN", "new-bootstrap-access")
    monkeypatch.setenv("OURA_ACCESS_TOKEN_EXPIRES_AT", str(int(time.time()) + 7200))
    store = _TokenStore(
        {
            "access_token": "old-persisted-access",
            "refresh_token": "old-persisted-refresh",
            "expires_at": int(time.time()) + 3600,
        }
    )

    provider = EnvTokenProvider(config=Config(), token_store=store)

    assert provider.get_token() == "new-bootstrap-access"
    assert provider.config.OURA_REFRESH_TOKEN == "new-bootstrap-refresh"


def test_env_token_provider_falls_back_when_state_cannot_be_decrypted(monkeypatch):
    monkeypatch.delenv("OURA_TOKEN", raising=False)
    monkeypatch.setenv("OURA_CLIENT_ID", "client-id")
    monkeypatch.setenv("OURA_CLIENT_SECRET", "new-client-secret")
    monkeypatch.setenv("OURA_REFRESH_TOKEN", "new-bootstrap-refresh")
    monkeypatch.setenv("OURA_ACCESS_TOKEN", "new-bootstrap-access")
    monkeypatch.setenv("OURA_ACCESS_TOKEN_EXPIRES_AT", str(int(time.time()) + 3600))
    store = _TokenStore(load_error=ValueError("wrong encryption key"))

    provider = EnvTokenProvider(config=Config(), token_store=store)

    assert provider.get_token() == "new-bootstrap-access"


def test_env_token_provider_falls_back_when_persisted_state_is_incomplete(monkeypatch):
    monkeypatch.delenv("OURA_TOKEN", raising=False)
    monkeypatch.setenv("OURA_CLIENT_ID", "client-id")
    monkeypatch.setenv("OURA_CLIENT_SECRET", "new-client-secret")
    monkeypatch.setenv("OURA_REFRESH_TOKEN", "new-bootstrap-refresh")
    monkeypatch.setenv("OURA_ACCESS_TOKEN", "new-bootstrap-access")
    monkeypatch.setenv("OURA_ACCESS_TOKEN_EXPIRES_AT", str(int(time.time()) + 3600))
    store = _TokenStore({"expires_at": int(time.time()) + 7200})

    provider = EnvTokenProvider(config=Config(), token_store=store)

    assert provider.get_token() == "new-bootstrap-access"


def test_env_token_provider_restores_tokens_with_malformed_persisted_expiry(monkeypatch):
    monkeypatch.delenv("OURA_TOKEN", raising=False)
    monkeypatch.setenv("OURA_CLIENT_ID", "client-id")
    monkeypatch.setenv("OURA_CLIENT_SECRET", "client-secret")
    monkeypatch.setenv("OURA_REFRESH_TOKEN", "bootstrap-refresh")
    monkeypatch.delenv("OURA_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("OURA_ACCESS_TOKEN_EXPIRES_AT", raising=False)
    store = _TokenStore(
        {
            "access_token": "persisted-access",
            "refresh_token": "persisted-refresh",
            "expires_at": "not-a-timestamp",
        }
    )

    provider = EnvTokenProvider(config=Config(), token_store=store)

    assert provider.config.OURA_ACCESS_TOKEN == "persisted-access"
    assert provider.config.OURA_REFRESH_TOKEN == "persisted-refresh"
    assert provider.config.OURA_ACCESS_TOKEN_EXPIRES_AT == "not-a-timestamp"


def test_env_token_provider_persists_rotated_refresh_token(monkeypatch):
    monkeypatch.delenv("OURA_TOKEN", raising=False)
    monkeypatch.setenv("OURA_CLIENT_ID", "client-id")
    monkeypatch.setenv("OURA_CLIENT_SECRET", "client-secret")
    monkeypatch.setenv("OURA_REFRESH_TOKEN", "single-use-refresh")
    monkeypatch.setenv("OURA_ACCESS_TOKEN_EXPIRES_AT", "1")
    store = _TokenStore()
    session = _JsonSession({"access_token": "new-access", "refresh_token": "replacement-refresh", "expires_in": 3600})

    provider = EnvTokenProvider(config=Config(), session=session, token_store=store)

    assert provider.get_token() == "new-access"
    assert store.saved["refresh_token"] == "replacement-refresh"
    assert store.saved["access_token"] == "new-access"


def test_env_token_provider_retries_rotated_token_persistence(monkeypatch):
    monkeypatch.delenv("OURA_TOKEN", raising=False)
    monkeypatch.setenv("OURA_CLIENT_ID", "client-id")
    monkeypatch.setenv("OURA_CLIENT_SECRET", "client-secret")
    monkeypatch.setenv("OURA_REFRESH_TOKEN", "single-use-refresh")
    monkeypatch.setenv("OURA_ACCESS_TOKEN_EXPIRES_AT", "1")
    delays = []
    monkeypatch.setattr("oura_ingest.auth.time.sleep", delays.append)

    class FlakyTokenStore(_TokenStore):
        def save(self, payload):
            self.save_calls += 1
            if self.save_calls < 3:
                raise RuntimeError("database unavailable")
            self.saved = payload

    store = FlakyTokenStore()
    session = _JsonSession({"access_token": "new-access", "refresh_token": "replacement-refresh", "expires_in": 3600})
    provider = EnvTokenProvider(config=Config(), session=session, token_store=store)

    assert provider.get_token() == "new-access"
    assert store.save_calls == 3
    assert store.saved["refresh_token"] == "replacement-refresh"
    assert session.posts == 1
    assert delays == [0.25, 0.5]


def test_env_token_provider_stops_if_rotated_token_cannot_be_persisted(monkeypatch):
    monkeypatch.delenv("OURA_TOKEN", raising=False)
    monkeypatch.setenv("OURA_CLIENT_ID", "client-id")
    monkeypatch.setenv("OURA_CLIENT_SECRET", "client-secret")
    monkeypatch.setenv("OURA_REFRESH_TOKEN", "single-use-refresh")
    monkeypatch.setenv("OURA_ACCESS_TOKEN_EXPIRES_AT", "1")
    store = _TokenStore(save_error=RuntimeError("database unavailable"))
    session = _JsonSession({"access_token": "new-access", "refresh_token": "replacement-refresh", "expires_in": 3600})
    monkeypatch.setattr("oura_ingest.auth.time.sleep", lambda _: None)

    provider = EnvTokenProvider(config=Config(), session=session, token_store=store)

    with pytest.raises(OAuthError, match="persist"):
        provider.get_token()
    assert store.save_calls == 3


def test_env_token_provider_requires_rotated_refresh_token_when_persisting(monkeypatch):
    monkeypatch.delenv("OURA_TOKEN", raising=False)
    monkeypatch.setenv("OURA_CLIENT_ID", "client-id")
    monkeypatch.setenv("OURA_CLIENT_SECRET", "client-secret")
    monkeypatch.setenv("OURA_REFRESH_TOKEN", "single-use-refresh")
    monkeypatch.setenv("OURA_ACCESS_TOKEN_EXPIRES_AT", "1")
    store = _TokenStore()
    session = _JsonSession({"access_token": "new-access", "expires_in": 3600})

    provider = EnvTokenProvider(config=Config(), session=session, token_store=store)

    with pytest.raises(OAuthError, match="replacement refresh token"):
        provider.get_token()
    assert store.saved is None


def test_env_token_provider_demotes_dead_legacy_token(monkeypatch):
    # Legacy token is set but rejected by Oura, while OAuth is configured.
    monkeypatch.setenv("OURA_TOKEN", "dead-legacy")
    monkeypatch.setenv("OURA_CLIENT_ID", "client-id")
    monkeypatch.setenv("OURA_CLIENT_SECRET", "client-secret")
    monkeypatch.setenv("OURA_REFRESH_TOKEN", "refresh-token")

    session = _JsonSession({"access_token": "oauth-access", "refresh_token": "r2", "expires_in": 3600})
    provider = EnvTokenProvider(config=Config(), session=session)

    assert provider.get_token() == "dead-legacy"  # legacy served first
    assert provider.get_token(force_refresh=True) == "oauth-access"  # 401 -> refresh
    posts_after_refresh = session.posts
    # Subsequent calls must converge on the cached OAuth token, not re-serve the
    # dead legacy token, and must not fire another refresh.
    assert provider.get_token() == "oauth-access"
    assert provider.get_token() == "oauth-access"
    assert session.posts == posts_after_refresh


def test_env_token_provider_accepts_refresh_response_without_rotation_when_not_persisting(monkeypatch):
    monkeypatch.delenv("OURA_TOKEN", raising=False)
    monkeypatch.setenv("OURA_CLIENT_ID", "client-id")
    monkeypatch.setenv("OURA_CLIENT_SECRET", "client-secret")
    monkeypatch.setenv("OURA_REFRESH_TOKEN", "existing-refresh")
    monkeypatch.setenv("OURA_ACCESS_TOKEN_EXPIRES_AT", "1")
    session = _JsonSession({"access_token": "new-access"})
    provider = EnvTokenProvider(config=Config(), session=session)

    assert provider.get_token() == "new-access"
    assert provider.config.OURA_REFRESH_TOKEN == "existing-refresh"
    assert provider.config.OURA_ACCESS_TOKEN_EXPIRES_AT == "1"


def test_post_token_non_json_body_raises_oauth_error():
    session = _JsonSession(ValueError("not json"))
    with pytest.raises(OAuthError):
        _post_token({"grant_type": "refresh_token"}, session=session)


def test_post_token_non_dict_body_raises_oauth_error():
    session = _JsonSession(["unexpected"])
    with pytest.raises(OAuthError):
        _post_token({"grant_type": "refresh_token"}, session=session)


def test_post_token_requires_access_token():
    session = _JsonSession({"refresh_token": "refresh-token", "expires_in": 3600})

    with pytest.raises(OAuthError, match="did not include an access token"):
        _post_token({"grant_type": "refresh_token"}, session=session)


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        (
            {"error": "invalid_grant", "error_description": "Authorization code expired"},
            "OAuth token request failed with HTTP 400: Authorization code expired",
        ),
        (ValueError("not json"), "OAuth token request failed with HTTP 502"),
        (["unexpected"], "OAuth token request failed with HTTP 503"),
    ],
)
def test_post_token_formats_http_errors(body, expected):
    status_code = 400 if isinstance(body, dict) else 502 if isinstance(body, ValueError) else 503
    session = _JsonSession(body, ok=False, status_code=status_code)

    with pytest.raises(OAuthError, match=f"^{expected}$"):
        _post_token({"grant_type": "refresh_token"}, session=session)


def test_build_authorization_url_includes_state():
    assert "state=xyz" in build_authorization_url("cid", "http://localhost:8765/callback", "daily", state="xyz")
    assert "state=" not in build_authorization_url("cid", "http://localhost:8765/callback", "daily")


def test_find_env_file_prefers_existing_env(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("OURA_TOKEN=x\n")
    assert find_env_file(tmp_path) == env_file


def test_find_env_file_uses_nearest_parent_env_template(tmp_path):
    project = tmp_path / "project"
    nested = project / "var" / "run"
    nested.mkdir(parents=True)
    (project / ".env.example").write_text("OURA_TOKEN=\n")

    assert find_env_file(nested) == project / ".env"


def test_find_env_file_falls_back_to_start_directory(tmp_path, monkeypatch):
    start = tmp_path / "isolated"
    start.mkdir()
    monkeypatch.setattr(type(start), "exists", lambda self: False)

    assert find_env_file(start) == start / ".env"


def test_update_env_file_sets_owner_only_permissions(tmp_path):
    env_file = tmp_path / ".env"
    update_env_file(env_file, {"OURA_CLIENT_ID": "cid", "OURA_CLIENT_SECRET": "sec"})
    assert oct(env_file.stat().st_mode & 0o777) == "0o600"


def test_update_env_file_replaces_existing_secret_without_duplication(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("# Existing settings\nOURA_CLIENT_SECRET = old-secret\nPOSTGRES_DB=oura\n")

    update_env_file(env_file, {"OURA_CLIENT_SECRET": "new-secret"})

    assert env_file.read_text() == "# Existing settings\nOURA_CLIENT_SECRET=new-secret\nPOSTGRES_DB=oura\n"


def test_update_env_file_keeps_written_state_when_permissions_cannot_be_changed(tmp_path, monkeypatch):
    env_file = tmp_path / "nested" / ".env"

    def reject_chmod(self, mode):
        raise OSError("operation not supported")

    monkeypatch.setattr(type(env_file), "chmod", reject_chmod)

    update_env_file(env_file, {"OURA_CLIENT_ID": "client-id"})

    assert env_file.read_text() == "# Oura OAuth\nOURA_CLIENT_ID=client-id\n"
