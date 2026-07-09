"""Heart rate dashboard."""

from datetime import date, timedelta

from components.charts import line_chart, pie_chart
from components.metrics import stat_card
from components.theme import BLUE, GREEN, ORANGE, PURPLE, RED
from data.providers import get_provider

import streamlit as st

st.set_page_config(page_title="Oura - Heart Rate", layout="wide", page_icon=":heart:")

from components.sidebar import render_sidebar  # noqa: E402

render_sidebar()
st.title("Heart Rate")

provider = get_provider()
start = st.session_state.get("start_date", date.today() - timedelta(days=30))
end = st.session_state.get("end_date", date.today())

summary = provider.heart_rate_summary(start, end)
c1, c2, c3, c4 = st.columns(4)
with c1:
    stat_card("Latest", summary.get("latest"), unit=" bpm", color=RED)
with c2:
    stat_card("Average", summary.get("average"), unit=" bpm", color=BLUE, fmt=".1f")
with c3:
    stat_card("Minimum", summary.get("minimum"), unit=" bpm", color=GREEN)
with c4:
    stat_card("Maximum", summary.get("maximum"), unit=" bpm", color=ORANGE)

series = provider.heart_rate_series(start, end)
sources = provider.heart_rate_sources(start, end)
left, right = st.columns([2, 1])
with left:
    if not series.empty:
        pivot = series.pivot_table(index="timestamp", columns="source", values="bpm", aggfunc="mean").reset_index()
        cols = [c for c in pivot.columns if c != "timestamp"]
        fig = line_chart(
            pivot,
            "timestamp",
            cols,
            colors=[BLUE, ORANGE, GREEN, RED, PURPLE][: len(cols)],
            title="Heart Rate by Source",
            y_label="bpm",
            smooth=False,
        )
        st.plotly_chart(fig, width="stretch")
    else:
        st.info("No heart rate data available.")
with right:
    if not sources.empty:
        fig = pie_chart(sources["source"], sources["count"], title="Samples by Source")
        st.plotly_chart(fig, width="stretch")
    else:
        st.info("No source data available.")

daily = provider.heart_rate_daily(start, end)
if not daily.empty:
    fig = line_chart(
        daily,
        "day",
        ["minimum", "average", "maximum"],
        colors=[GREEN, BLUE, RED],
        title="Daily Range",
        y_label="bpm",
        smooth=False,
    )
    st.plotly_chart(fig, width="stretch")
