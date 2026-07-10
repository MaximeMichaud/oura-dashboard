"""Small Oura OAuth helpers for Streamlit direct API mode."""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from urllib.parse import parse_qs, urlencode, urlparse

import requests

AUTHORIZE_URL = "https://cloud.ouraring.com/oauth/authorize"
TOKEN_URL = "https://api.ouraring.com/oauth/token"
DEFAULT_REDIRECT_URI = "http://localhost:8765/callback"
DEFAULT_SCOPES = "personal daily heartrate tag workout session spo2 ring_configuration stress heart_health"
TOKEN_REFRESH_MARGIN_SECONDS = 300


@dataclass
class OAuthToken:
    access_token: str
    refresh_token: str | None
    expires_at: int | None
    scope: str | None = None


class OAuthError(Exception):
    """Raised when Oura OAuth fails."""


def build_authorization_url(client_id: str, redirect_uri: str, scopes: str) -> str:
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": scopes,
    }
    return f"{AUTHORIZE_URL}?{urlencode(params)}"


def extract_authorization_code(value: str) -> str:
    value = value.strip()
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
) -> OAuthToken:
    return _post_token(
        {
            "grant_type": "authorization_code",
            "client_id": client_id,
            "client_secret": client_secret,
            "code": code,
            "redirect_uri": redirect_uri,
        }
    )


def refresh_access_token(*, client_id: str, client_secret: str, refresh_token: str) -> OAuthToken:
    return _post_token(
        {
            "grant_type": "refresh_token",
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": refresh_token,
        }
    )


def get_env_oauth_access_token(*, allow_refresh: bool = True) -> str | None:
    client_id = os.environ.get("OURA_CLIENT_ID", "")
    client_secret = os.environ.get("OURA_CLIENT_SECRET", "")
    refresh_token = os.environ.get("OURA_REFRESH_TOKEN", "")
    access_token = os.environ.get("OURA_ACCESS_TOKEN", "")
    expires_at_raw = os.environ.get("OURA_ACCESS_TOKEN_EXPIRES_AT", "")

    try:
        expires_at = int(expires_at_raw)
    except (TypeError, ValueError):
        expires_at = 0

    if access_token and expires_at > int(time.time()) + TOKEN_REFRESH_MARGIN_SECONDS:
        return access_token

    if not allow_refresh:
        return None

    if not all((client_id, client_secret, refresh_token)):
        return None

    token = refresh_access_token(client_id=client_id, client_secret=client_secret, refresh_token=refresh_token)
    os.environ["OURA_ACCESS_TOKEN"] = token.access_token
    if token.refresh_token:
        os.environ["OURA_REFRESH_TOKEN"] = token.refresh_token
    if token.expires_at:
        os.environ["OURA_ACCESS_TOKEN_EXPIRES_AT"] = str(token.expires_at)
    return token.access_token


def _post_token(data: dict[str, str]) -> OAuthToken:
    resp = requests.post(TOKEN_URL, data=data, timeout=30)
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
        body = resp.json()
    except ValueError:
        return f"OAuth token request failed with HTTP {resp.status_code}"
    if isinstance(body, dict):
        detail = body.get("error_description") or body.get("detail") or body.get("error") or body.get("title")
        if detail:
            return f"OAuth token request failed with HTTP {resp.status_code}: {detail}"
    return f"OAuth token request failed with HTTP {resp.status_code}"
