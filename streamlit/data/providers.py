"""Data provider abstraction - auto-detects PostgreSQL, API, or demo mode."""

from __future__ import annotations

import os
import time

import streamlit as st
from data.oauth import (
    DEFAULT_REDIRECT_URI,
    DEFAULT_SCOPES,
    OAuthError,
    build_authorization_url,
    exchange_authorization_code,
    extract_authorization_code,
    get_env_oauth_access_token,
)


def get_provider():
    """Auto-detect and return the appropriate data provider.

    Priority: PostgreSQL > API (token) > Demo.
    Cached per session so sidebar interactions don't re-create.
    """
    if "provider" in st.session_state:
        return st.session_state["provider"]

    # 1. Try PostgreSQL
    pg_host = os.environ.get("POSTGRES_HOST")
    if pg_host:
        try:
            from data.postgres_provider import PostgresProvider

            provider = PostgresProvider()
            provider.test_connection()
            st.session_state["provider"] = provider
            st.session_state["provider_mode"] = "postgresql"
            return provider
        except Exception:
            pass

    # 2. Check for API token in env or session
    token = os.environ.get("OURA_TOKEN") or st.session_state.get("oura_token")
    if not token:
        token = st.session_state.get("oura_access_token")
    if not token and not st.session_state.get("oauth_env_refresh_failed"):
        # A stale refresh token or a network blip must not crash the app; fall
        # back to demo mode and remember the failure so we don't re-hit it on
        # every rerun.
        try:
            # In database mode, ingestion owns refresh-token rotation and
            # persists replacements. Streamlit may reuse a valid access token,
            # but must not independently consume the single-use refresh token.
            token = get_env_oauth_access_token(allow_refresh=not bool(pg_host))
        except Exception:
            st.session_state["oauth_env_refresh_failed"] = True
            token = None
    if token:
        from data.api_provider import ApiProvider

        provider = ApiProvider(token)
        st.session_state["provider"] = provider
        st.session_state["provider_mode"] = "api"
        return provider

    # 3. Fallback to demo
    from data.demo_provider import DemoProvider

    provider = DemoProvider()
    st.session_state["provider"] = provider
    st.session_state["provider_mode"] = "demo"
    return provider


def reset_provider():
    """Force re-detection (e.g. after token input)."""
    st.session_state.pop("provider", None)
    st.session_state.pop("provider_mode", None)
    st.session_state.pop("oauth_env_refresh_failed", None)


def show_provider_sidebar():
    """Sidebar widget to show current mode and allow token input."""
    mode = st.session_state.get("provider_mode", "demo")

    with st.sidebar:
        if mode == "postgresql":
            st.caption("Connected to PostgreSQL")
        else:
            if mode == "api":
                st.caption("Connected via Oura API")
            else:
                st.caption("Demo mode - sample data")
            with st.expander("Connect your Oura Ring", expanded=(mode != "api")):
                token = st.text_input(
                    "Legacy Oura Token",
                    type="password",
                    help="Use this only if you already have an old Oura bearer token.",
                )
                if token and token != st.session_state.get("oura_token"):
                    st.session_state["oura_token"] = token
                    reset_provider()
                    st.rerun()

                st.divider()
                st.caption("OAuth")
                client_id = st.text_input("Client ID", value=os.environ.get("OURA_CLIENT_ID", ""))
                submitted_client_secret = st.text_input("Client Secret", type="password")
                redirect_uri = os.environ.get("OURA_REDIRECT_URI", DEFAULT_REDIRECT_URI)
                scopes = os.environ.get("OURA_OAUTH_SCOPES", DEFAULT_SCOPES)

                if client_id:
                    st.code(build_authorization_url(client_id, redirect_uri, scopes), language="text")

                callback_value = st.text_input("Callback URL or code")
                if st.button("Connect with OAuth"):
                    code = extract_authorization_code(callback_value)
                    client_secret = submitted_client_secret or os.environ.get("OURA_CLIENT_SECRET", "")
                    if not all((client_id, client_secret, code)):
                        st.error("Client ID, client secret, and callback code are required.")
                    else:
                        try:
                            oauth_token = exchange_authorization_code(
                                client_id=client_id,
                                client_secret=client_secret,
                                code=code,
                                redirect_uri=redirect_uri,
                            )
                        except OAuthError as exc:
                            st.error(str(exc))
                        else:
                            st.session_state["oura_access_token"] = oauth_token.access_token
                            if oauth_token.refresh_token:
                                st.session_state["oura_refresh_token"] = oauth_token.refresh_token
                            if oauth_token.expires_at:
                                st.session_state["oura_access_token_expires_at"] = oauth_token.expires_at
                                expires_in_days = max(0, int((oauth_token.expires_at - time.time()) / 86400))
                                st.success(f"Connected. Access token expires in about {expires_in_days} days.")
                            else:
                                st.success("Connected.")
                            reset_provider()
                            st.rerun()
