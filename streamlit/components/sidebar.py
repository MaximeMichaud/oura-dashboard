"""Shared sidebar - time range picker + timezone + provider status."""
import os
import streamlit as st
from datetime import date, timedelta
from zoneinfo import available_timezones

from data.providers import get_provider, show_provider_sidebar

_DEFAULT_TZ = os.environ.get("USER_TIMEZONE", "America/Toronto")

# Common timezones (covers most users without a 400-item dropdown)
_COMMON_TIMEZONES = [
    "America/Toronto", "America/New_York", "America/Chicago",
    "America/Denver", "America/Los_Angeles", "America/Vancouver",
    "America/Montreal", "America/Halifax", "America/Sao_Paulo",
    "America/Mexico_City", "Europe/London", "Europe/Paris",
    "Europe/Berlin", "Europe/Amsterdam", "Europe/Rome",
    "Europe/Madrid", "Europe/Zurich", "Europe/Brussels",
    "Europe/Stockholm", "Europe/Helsinki", "Europe/Moscow",
    "Asia/Tokyo", "Asia/Shanghai", "Asia/Hong_Kong",
    "Asia/Seoul", "Asia/Kolkata", "Asia/Dubai",
    "Asia/Singapore", "Australia/Sydney", "Australia/Melbourne",
    "Pacific/Auckland", "Pacific/Honolulu", "UTC",
]

# Build full timezone list once (common first, then all others)
_ALL_ZONES = sorted(available_timezones())
_TZ_OPTIONS = _COMMON_TIMEZONES + [z for z in _ALL_ZONES if z not in _COMMON_TIMEZONES]


def render_sidebar():
    """Render the shared sidebar on every page."""
    st.sidebar.title("Oura Dashboard")
    st.sidebar.markdown("---")

    # Time range picker - use key for cross-page persistence
    presets = {
        "Last 7 days": 7,
        "Last 30 days": 30,
        "Last 90 days": 90,
        "Last 6 months": 180,
        "Last year": 365,
    }
    preset_keys = list(presets.keys())

    if "time_range" not in st.session_state:
        st.session_state["time_range"] = preset_keys[1]  # "Last 30 days"

    preset = st.sidebar.selectbox("Time Range", preset_keys, key="time_range")
    end_date = date.today()
    start_date = end_date - timedelta(days=presets[preset])
    st.session_state["start_date"] = start_date
    st.session_state["end_date"] = end_date

    # Timezone picker - restore from query_params on F5, persist via key
    params = st.query_params
    if "user_timezone" not in st.session_state:
        initial_tz = params.get("tz", _DEFAULT_TZ)
        st.session_state["user_timezone"] = (
            initial_tz if initial_tz in _TZ_OPTIONS else _DEFAULT_TZ
        )

    st.sidebar.selectbox("Timezone", _TZ_OPTIONS, key="user_timezone")

    # Persist timezone to URL so it survives F5
    if st.session_state["user_timezone"] != _DEFAULT_TZ:
        params["tz"] = st.session_state["user_timezone"]
    elif "tz" in params:
        del params["tz"]

    st.sidebar.markdown("---")

    # Provider detection + status
    get_provider()
    show_provider_sidebar()
