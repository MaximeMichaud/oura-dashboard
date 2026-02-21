"""Data provider abstraction - auto-detects PostgreSQL, API, or demo mode."""
from __future__ import annotations

import os

import streamlit as st


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


def show_provider_sidebar():
    """Sidebar widget to show current mode and allow token input."""
    mode = st.session_state.get("provider_mode", "demo")

    with st.sidebar:
        if mode == "postgresql":
            st.caption("Connected to PostgreSQL")
        elif mode == "api":
            st.caption("Connected via Oura API")
        else:
            st.caption("Demo mode - sample data")
            with st.expander("Connect your Oura Ring"):
                token = st.text_input(
                    "Oura Personal Access Token",
                    type="password",
                    help="Get yours at https://cloud.ouraring.com/personal-access-tokens",
                )
                if token and token != st.session_state.get("oura_token"):
                    st.session_state["oura_token"] = token
                    reset_provider()
                    st.rerun()
