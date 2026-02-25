"""Readiness dashboard - score, temperature, contributors."""

from datetime import date, timedelta

from components.charts import horizontal_bar, line_chart
from components.metrics import gauge_chart, stat_card
from components.theme import BLUE, CYAN, DARK_GREEN, GREEN, ORANGE, SCORE_THRESHOLDS
from data.providers import get_provider

import streamlit as st

st.set_page_config(page_title="Oura - Readiness", layout="wide", page_icon=":ring:")

from components.sidebar import render_sidebar  # noqa: E402

render_sidebar()

st.title("Readiness")

provider = get_provider()
start = st.session_state.get("start_date", date.today() - timedelta(days=30))
end = st.session_state.get("end_date", date.today())

latest = provider.readiness_latest(end)

# -- Row 1: Score + Temp + 7d Trend --
c1, c2, c3 = st.columns([1, 1, 2])

with c1:
    gauge_chart(latest.get("score"), min_val=0, max_val=100, title="Readiness Score", thresholds=SCORE_THRESHOLDS)

with c2:
    stat_card("Temperature Deviation", latest.get("temperature_deviation"), unit=" \u00b0C", color=ORANGE, fmt=".2f")

with c3:
    # Fixed 7-day window
    trend_7d = provider.readiness_trend(end - timedelta(days=7), end)
    if not trend_7d.empty:
        fig = line_chart(trend_7d, "day", "score", colors=[GREEN], title="Score Trend (7d)", fill=True)
        st.plotly_chart(fig, width="stretch")

st.markdown("---")

# -- Row 2: Contributors bar + Contributors trends --
c1, c2 = st.columns([2, 3])

with c1:
    contributor_keys = [
        "Activity Balance",
        "Body Temp",
        "HRV Balance",
        "Prev Day Activity",
        "Previous Night",
        "Recovery Index",
        "Resting HR",
        "Sleep Balance",
        "Sleep Regularity",
    ]
    names = [k for k in contributor_keys if k in latest and latest[k] is not None]
    values = [latest[k] for k in names]
    if names:
        fig = horizontal_bar(names, values, thresholds=SCORE_THRESHOLDS, title="Contributors")
        st.plotly_chart(fig, width="stretch")

with c2:
    contrib_trend = provider.readiness_contributors_trend(start, end)
    if not contrib_trend.empty:
        cols = [c for c in contrib_trend.columns if c != "day"]
        fig = line_chart(
            contrib_trend,
            "day",
            cols,
            colors=[GREEN, CYAN, BLUE, "#78C9A4", ORANGE],
            title="Readiness Contributors Trends",
        )
        st.plotly_chart(fig, width="stretch")

# -- Row 3: Score Trend with MA + Temperature Trend --
c1, c2 = st.columns(2)

with c1:
    trend_df = provider.readiness_trend(start, end)
    if not trend_df.empty:
        trend_df["7d_avg"] = trend_df["score"].rolling(7, min_periods=1).mean()
        fig = line_chart(
            trend_df, "day", ["score", "7d_avg"], colors=[GREEN, DARK_GREEN], title="Readiness Score Trend"
        )
        st.plotly_chart(fig, width="stretch")

with c2:
    temp_df = provider.readiness_temp_trend(start, end)
    if not temp_df.empty:
        temp_df["baseline"] = 0.0
        fig = line_chart(
            temp_df,
            "day",
            ["temp", "baseline"],
            colors=[ORANGE, "#AAAAAA"],
            dashed=["baseline"],
            title="Temperature Trend",
            y_label="\u00b0C",
        )
        st.plotly_chart(fig, width="stretch")
