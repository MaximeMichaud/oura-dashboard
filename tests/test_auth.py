import time

import pytest
from oura_ingest.auth import (
    EnvTokenProvider,
    OAuthError,
    _post_token,
    build_authorization_url,
    extract_authorization_code,
    find_env_file,
    update_env_file,
)
from oura_ingest.config import Config


class _JsonSession:
    """Fake requests session whose token endpoint returns a fixed JSON body."""

    def __init__(self, body):
        self._body = body
        self.posts = 0

    def post(self, url, data, timeout):
        self.posts += 1
        body = self._body

        class Response:
            ok = True
            status_code = 200

            def json(self):
                if isinstance(body, Exception):
                    raise body
                return body

        return Response()


def test_build_authorization_url():
    url = build_authorization_url("client-id", "http://localhost:8765/callback", "daily workout")
    assert "client_id=client-id" in url
    assert "response_type=code" in url
    assert "scope=daily+workout" in url


def test_extract_authorization_code_from_callback_url():
    code = extract_authorization_code("http://localhost:8765/callback?iss=x&code=abc123")
    assert code == "abc123"


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


def test_post_token_non_json_body_raises_oauth_error():
    session = _JsonSession(ValueError("not json"))
    with pytest.raises(OAuthError):
        _post_token({"grant_type": "refresh_token"}, session=session)


def test_post_token_non_dict_body_raises_oauth_error():
    session = _JsonSession(["unexpected"])
    with pytest.raises(OAuthError):
        _post_token({"grant_type": "refresh_token"}, session=session)


def test_build_authorization_url_includes_state():
    assert "state=xyz" in build_authorization_url("cid", "http://localhost:8765/callback", "daily", state="xyz")
    assert "state=" not in build_authorization_url("cid", "http://localhost:8765/callback", "daily")


def test_find_env_file_prefers_existing_env(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("OURA_TOKEN=x\n")
    assert find_env_file(tmp_path) == env_file


def test_update_env_file_sets_owner_only_permissions(tmp_path):
    env_file = tmp_path / ".env"
    update_env_file(env_file, {"OURA_CLIENT_ID": "cid", "OURA_CLIENT_SECRET": "sec"})
    assert oct(env_file.stat().st_mode & 0o777) == "0o600"
