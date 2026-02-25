"""Overview dashboard - scores, steps, stress, resilience, weekly trends."""

from datetime import date, timedelta

from components.charts import bar_chart, dual_axis_chart, horizontal_bar, line_chart, stacked_area
from components.metrics import gauge_chart, stat_card, stat_card_mapped
from components.theme import (
    BLUE,
    CARDIO_AGE_THRESHOLDS,
    CYAN,
    GREEN,
    ORANGE,
    PURPLE,
    RED,
    RESILIENCE_MAP,
    SCORE_THRESHOLDS,
    SPO2_THRESHOLDS,
    STRESS_MAP,
)
from data.providers import get_provider

import streamlit as st

st.set_page_config(page_title="Oura - Overview", layout="wide", page_icon=":ring:")

from components.sidebar import render_sidebar  # noqa: E402

render_sidebar()

st.title("Overview")

provider = get_provider()
start = st.session_state.get("start_date", date.today() - timedelta(days=30))
end = st.session_state.get("end_date", date.today())

# -- Row 1: Stat cards --
scores = provider.latest_scores(end)

c1, c2, c3, c4, c5, c6 = st.columns(6)
with c1:
    stat_card("Sleep Score", scores.get("sleep_score"), thresholds=SCORE_THRESHOLDS)
with c2:
    stat_card("Readiness", scores.get("readiness_score"), thresholds=SCORE_THRESHOLDS)
with c3:
    stat_card("Active Cal", scores.get("active_cal"), unit=" kcal", color=ORANGE)
with c4:
    stat_card("Steps", scores.get("steps"), color=ORANGE)
with c5:
    stat_card_mapped("Stress", scores.get("stress_summary"), STRESS_MAP)
with c6:
    stat_card_mapped("Resilience", scores.get("resilience_level"), RESILIENCE_MAP)

st.markdown("---")

# -- Row 2: Scores & Steps Trend + Sleep Duration Breakdown --
col_left, col_right = st.columns(2)

with col_left:
    trend_df = provider.scores_trend(start, end)
    if not trend_df.empty:
        fig = dual_axis_chart(
            trend_df,
            "day",
            left_cols=["sleep_score", "readiness_score"],
            right_cols=["steps"],
            left_colors=[BLUE, GREEN],
            right_colors=[ORANGE],
            bar_cols=["steps"],
            left_label="Score",
            right_label="Steps",
            title="Scores & Steps Trend",
        )
        st.plotly_chart(fig, width="stretch")

with col_right:
    breakdown_df = provider.sleep_duration_breakdown(start, end)
    if not breakdown_df.empty:
        fig = stacked_area(
            breakdown_df,
            "day",
            y_cols=["deep", "light", "rem", "awake"],
            colors=[BLUE, "#7EB2DD", PURPLE, RED],
            title="Sleep Duration Breakdown (hours)",
        )
        st.plotly_chart(fig, width="stretch")

# -- Row 3: Sleep Contributors + Steps 30d + SpO2/Cardio --
c1, c2, c3 = st.columns(3)

with c1:
    contrib_df = provider.sleep_contributors_latest(end)
    if not contrib_df.empty:
        row = contrib_df.iloc[0]
        names = list(row.index)
        values = [row[n] for n in names]
        fig = horizontal_bar(names, values, thresholds=SCORE_THRESHOLDS, title="Sleep Contributors")
        st.plotly_chart(fig, width="stretch")

with c2:
    steps_df = provider.steps_30d(end)
    if not steps_df.empty:
        fig = bar_chart(steps_df, "day", "steps", color=ORANGE, title="Steps (30d)")
        st.plotly_chart(fig, width="stretch")

with c3:
    stat_card("SpO2", scores.get("spo2"), unit="%", thresholds=SPO2_THRESHOLDS)
    gauge_chart(
        scores.get("cardio_age"),
        min_val=15,
        max_val=80,
        title="Cardiovascular Age",
        thresholds=CARDIO_AGE_THRESHOLDS,
        unit=" yrs",
    )

# -- Row 4: SpO2 Trend + HRV vs Readiness --
col_left, col_right = st.columns(2)

with col_left:
    spo2_df = provider.spo2_trend(start, end)
    if not spo2_df.empty:
        fig = line_chart(spo2_df, "day", "spo2", colors=[CYAN], title="SpO2 Trend", y_label="%", fill=True)
        st.plotly_chart(fig, width="stretch")

with col_right:
    hrv_read_df = provider.hrv_vs_readiness(start, end)
    if not hrv_read_df.empty:
        fig = dual_axis_chart(
            hrv_read_df,
            "day",
            left_cols=["hrv"],
            right_cols=["readiness"],
            left_colors=[BLUE],
            right_colors=[GREEN],
            left_label="HRV (ms)",
            right_label="Readiness Score",
            title="HRV vs Next-Day Readiness",
        )
        st.plotly_chart(fig, width="stretch")

# -- Row 5: Sync Status --
sync_df = provider.sync_status()
if not sync_df.empty and "endpoint" in sync_df.columns:
    with st.expander("Sync Status"):
        st.dataframe(sync_df, width="stretch", hide_index=True)

# -- Row 6: Weekly Trends --
st.subheader("Weekly Trends")
weekly = provider.weekly_trends(start, end)

w1, w2, w3, w4 = st.columns(4)
for col, key, color, title in [
    (w1, "sleep", BLUE, "Avg Sleep Score"),
    (w2, "readiness", GREEN, "Avg Readiness"),
    (w3, "steps", ORANGE, "Avg Steps"),
    (w4, "hrv", PURPLE, "Avg HRV"),
]:
    with col:
        df = weekly.get(key)
        if df is not None and not df.empty:
            fig = bar_chart(df, "week", "value", color=color, title=title)
            st.plotly_chart(fig, width="stretch")
