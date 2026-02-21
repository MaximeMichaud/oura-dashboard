"""Shared sidebar - time range picker + timezone + provider status."""
import os
import streamlit as st
from datetime import date, timedelta
from zoneinfo import ZoneInfo, available_timezones

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


def render_sidebar():
    """Render the shared sidebar on every page."""
    st.sidebar.title("Oura Dashboard")
    st.sidebar.markdown("---")

    # Time range picker
    presets = {
        "Last 7 days": 7,
        "Last 30 days": 30,
        "Last 90 days": 90,
        "Last 6 months": 180,
        "Last year": 365,
    }
    preset = st.sidebar.selectbox("Time Range", list(presets.keys()), index=1)
    end_date = date.today()
    start_date = end_date - timedelta(days=presets[preset])
    st.session_state["start_date"] = start_date
    st.session_state["end_date"] = end_date

    # Timezone picker
    all_zones = sorted(available_timezones())
    # Build list: common first, then all others
    other_zones = [z for z in all_zones if z not in _COMMON_TIMEZONES]
    tz_options = _COMMON_TIMEZONES + other_zones

    default_idx = 0
    if _DEFAULT_TZ in tz_options:
        default_idx = tz_options.index(_DEFAULT_TZ)

    selected_tz = st.sidebar.selectbox("Timezone", tz_options, index=default_idx)
    st.session_state["user_timezone"] = selected_tz

    st.sidebar.markdown("---")

    # Provider detection + status
    get_provider()
    show_provider_sidebar()
