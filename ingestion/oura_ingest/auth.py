from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import parse_qs, urlencode, urlparse

import requests

from .config import Config, cfg

AUTHORIZE_URL = "https://moi.ouraring.com/oauth/v2/ext/oauth-authorize"
TOKEN_URL = "https://moi.ouraring.com/oauth/v2/ext/oauth-token"

log = logging.getLogger(__name__)


class OAuthError(Exception):
    """Raised when an OAuth token exchange or refresh fails."""


class OAuthTokenStore(Protocol):
    def load(self) -> dict[str, Any] | None: ...

    def save(self, payload: dict[str, Any]) -> None: ...


@dataclass
class OAuthToken:
    access_token: str
    refresh_token: str | None
    expires_at: int | None
    scope: str | None = None


class StaticTokenProvider:
    def __init__(self, token: str):
        self.token = token

    @property
    def can_refresh(self) -> bool:
        return False

    def get_token(self, force_refresh: bool = False) -> str:
        return self.token


class EnvTokenProvider:
    """Returns either a legacy bearer token or an OAuth access token."""

    def __init__(
        self,
        config: Config | None = None,
        session: requests.Session | None = None,
        token_store: OAuthTokenStore | None = None,
    ):
        self.config = config or cfg
        self.session = session or requests.Session()
        self.token_store = token_store
        self._legacy_token_rejected = False
        if self.token_store is not None:
            self._restore_persisted_token()

    @property
    def can_refresh(self) -> bool:
        return self.config.has_oauth_refresh

    def get_token(self, force_refresh: bool = False) -> str:
        # A forced refresh means the token we last handed out was rejected (401).
        # When a legacy token is configured it is always served first, so it is
        # the one that just failed; demote it (only when OAuth can take over) so
        # we converge onto the OAuth access token instead of re-sending the dead
        # legacy token on every subsequent request.
        if force_refresh and self.config.has_legacy_token and self.config.has_oauth_refresh:
            self._legacy_token_rejected = True

        if self.config.has_legacy_token and not self._legacy_token_rejected and not force_refresh:
            return self.config.OURA_TOKEN

        if not force_refresh and self._cached_access_token_is_valid():
            return self.config.OURA_ACCESS_TOKEN

        if not self.config.has_oauth_refresh:
            if self.config.has_legacy_token and not self._legacy_token_rejected:
                return self.config.OURA_TOKEN
            raise OAuthError("OAuth refresh token is not configured")

        token = refresh_access_token(
            client_id=self.config.OURA_CLIENT_ID,
            client_secret=self.config.OURA_CLIENT_SECRET,
            refresh_token=self.config.OURA_REFRESH_TOKEN,
            session=self.session,
        )
        if self.token_store is not None:
            if not token.refresh_token:
                raise OAuthError("OAuth refresh response did not include a replacement refresh token")
            try:
                self.token_store.save(
                    {
                        "access_token": token.access_token,
                        "refresh_token": token.refresh_token,
                        "expires_at": token.expires_at,
                        "scope": token.scope,
                    }
                )
            except Exception as exc:
                raise OAuthError("Could not persist the rotated OAuth token") from exc
        self._store_in_process(token)
        return token.access_token

    def _cached_access_token_is_valid(self) -> bool:
        return self.config.has_valid_access_token

    def _restore_persisted_token(self) -> None:
        try:
            state = self.token_store.load()
        except Exception as exc:
            log.warning("Could not decrypt persisted OAuth state; using configured OAuth bootstrap", exc_info=exc)
            return
        if not state:
            return

        try:
            configured_expires_at = int(self.config.OURA_ACCESS_TOKEN_EXPIRES_AT)
        except (TypeError, ValueError):
            configured_expires_at = 0
        try:
            persisted_expires_at = int(state.get("expires_at") or 0)
        except (TypeError, ValueError):
            persisted_expires_at = 0
        if self.config.OURA_ACCESS_TOKEN and configured_expires_at > persisted_expires_at:
            return

        access_token = state.get("access_token")
        refresh_token = state.get("refresh_token")
        if not access_token or not refresh_token:
            log.warning("Persisted OAuth token state is incomplete; using configured OAuth bootstrap")
            return

        self.config.OURA_ACCESS_TOKEN = str(access_token)
        self.config.OURA_REFRESH_TOKEN = str(refresh_token)
        os.environ["OURA_ACCESS_TOKEN"] = str(access_token)
        os.environ["OURA_REFRESH_TOKEN"] = str(refresh_token)
        expires_at = state.get("expires_at")
        if expires_at:
            self.config.OURA_ACCESS_TOKEN_EXPIRES_AT = str(expires_at)
            os.environ["OURA_ACCESS_TOKEN_EXPIRES_AT"] = str(expires_at)

    def _store_in_process(self, token: OAuthToken) -> None:
        self.config.OURA_ACCESS_TOKEN = token.access_token
        os.environ["OURA_ACCESS_TOKEN"] = token.access_token
        if token.refresh_token:
            self.config.OURA_REFRESH_TOKEN = token.refresh_token
            os.environ["OURA_REFRESH_TOKEN"] = token.refresh_token
        if token.expires_at:
            self.config.OURA_ACCESS_TOKEN_EXPIRES_AT = str(token.expires_at)
            os.environ["OURA_ACCESS_TOKEN_EXPIRES_AT"] = str(token.expires_at)


def build_authorization_url(client_id: str, redirect_uri: str, scopes: str, state: str | None = None) -> str:
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": scopes,
    }
    if state:
        params["state"] = state
    return f"{AUTHORIZE_URL}?{urlencode(params)}"


def extract_authorization_code(value: str) -> str:
    value = value.strip()
    if not value:
        return ""
    if value.startswith("http://") or value.startswith("https://"):
        query = parse_qs(urlparse(value).query)
        return (query.get("code") or [""])[0]
    return value


def exchange_authorization_code(
    *,
    client_id: str,
    client_secret: str,
    code: str,
    redirect_uri: str,
    session: requests.Session | None = None,
) -> OAuthToken:
    return _post_token(
        {
            "grant_type": "authorization_code",
            "code": code,
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": redirect_uri,
        },
        session=session,
    )


def refresh_access_token(
    *,
    client_id: str,
    client_secret: str,
    refresh_token: str,
    session: requests.Session | None = None,
) -> OAuthToken:
    return _post_token(
        {
            "grant_type": "refresh_token",
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": refresh_token,
        },
        session=session,
    )


def _post_token(data: dict[str, str], session: requests.Session | None = None) -> OAuthToken:
    http = session or requests.Session()
    resp = http.post(TOKEN_URL, data=data, timeout=30)
    if not resp.ok:
        raise OAuthError(_format_oauth_error(resp))

    try:
        body = resp.json()
    except ValueError as exc:
        raise OAuthError(f"OAuth token endpoint returned a non-JSON response (HTTP {resp.status_code})") from exc
    if not isinstance(body, dict):
        raise OAuthError(f"OAuth token endpoint returned an unexpected response (HTTP {resp.status_code})")

    access_token = body.get("access_token")
    if not access_token:
        raise OAuthError("OAuth response did not include an access token")

    expires_at = None
    expires_in = body.get("expires_in")
    if expires_in is not None:
        try:
            expires_at = int(time.time()) + int(expires_in)
        except (TypeError, ValueError):
            expires_at = None

    return OAuthToken(
        access_token=access_token,
        refresh_token=body.get("refresh_token"),
        expires_at=expires_at,
        scope=body.get("scope"),
    )


def _format_oauth_error(resp: requests.Response) -> str:
    try:
        body: Any = resp.json()
    except ValueError:
        return f"OAuth token request failed with HTTP {resp.status_code}"
    if isinstance(body, dict):
        detail = body.get("error_description") or body.get("detail") or body.get("error") or body.get("title")
        if detail:
            return f"OAuth token request failed with HTTP {resp.status_code}: {detail}"
    return f"OAuth token request failed with HTTP {resp.status_code}"


def find_env_file(start: Path | None = None) -> Path:
    current = (start or Path.cwd()).resolve()
    for parent in (current, *current.parents):
        env_file = parent / ".env"
        if env_file.exists():
            return env_file
        if (parent / ".env.example").exists():
            return env_file
    return current / ".env"


def update_env_file(path: Path, updates: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = path.read_text().splitlines() if path.exists() else []
    remaining = dict(updates)
    output: list[str] = []

    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in line:
            key = line.split("=", 1)[0].strip()
            if key in remaining:
                output.append(f"{key}={remaining.pop(key)}")
                continue
        output.append(line)

    if remaining:
        if output and output[-1] != "":
            output.append("")
        output.append("# Oura OAuth")
        for key, value in remaining.items():
            output.append(f"{key}={value}")

    path.write_text("\n".join(output) + "\n")
    # The file now holds OAuth secrets; keep it readable only by the owner.
    try:
        path.chmod(0o600)
    except OSError:
        pass
