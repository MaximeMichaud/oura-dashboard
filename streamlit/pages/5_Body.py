"""Body dashboard - SpO2, stress, resilience, cardiovascular age, VO2 Max."""

from datetime import date, timedelta

import pandas as pd
from components.charts import horizontal_bar, line_chart, stacked_area, state_timeline
from components.metrics import gauge_chart, stat_card, stat_card_mapped
from components.theme import (
    BREATHING_THRESHOLDS,
    CARDIO_AGE_THRESHOLDS,
    CYAN,
    GREEN,
    ORANGE,
    PURPLE,
    RED,
    RESILIENCE_MAP,
    RESILIENCE_TIMELINE_COLORS,
    SPO2_THRESHOLDS,
    STRESS_MAP,
    VO2_THRESHOLDS,
)
from data.providers import get_provider

import streamlit as st

st.set_page_config(page_title="Oura - Body", layout="wide", page_icon=":ring:")

from components.sidebar import render_sidebar  # noqa: E402

render_sidebar()

st.title("Body")

provider = get_provider()
start = st.session_state.get("start_date", date.today() - timedelta(days=30))
end = st.session_state.get("end_date", date.today())

# ======== SpO2 Section ========
st.subheader("SpO2")
spo2_data = provider.spo2_latest(end)
scores = provider.latest_scores(end)

c1, c2, c3 = st.columns([1, 1, 3])
with c1:
    stat_card("SpO2 Average", spo2_data.get("spo2"), unit="%", thresholds=SPO2_THRESHOLDS)
with c2:
    stat_card(
        "Breathing Disturbance", spo2_data.get("bdi"), unit=" events/hr", thresholds=BREATHING_THRESHOLDS, fmt=".1f"
    )
with c3:
    spo2_df = provider.spo2_trend(start, end)
    if not spo2_df.empty:
        fig = line_chart(spo2_df, "day", "spo2", colors=[CYAN], title="SpO2 Trend", y_label="%", fill=True)
        st.plotly_chart(fig, width="stretch")

st.markdown("---")

# ======== Stress Section ========
st.subheader("Stress")
stress_data = provider.stress_latest(end)

c1, c2, c3 = st.columns([1, 1, 3])
with c1:
    stat_card_mapped("Stress Summary", stress_data.get("day_summary"), STRESS_MAP)
with c2:
    stress_min = (stress_data.get("stress_high") or 0) / 60.0
    stat_card("Stress Duration", stress_min, unit=" min", color=RED, fmt=".0f")

with c3:
    # Stress vs Recovery bargauge
    stress_h = (stress_data.get("stress_high") or 0) / 3600.0
    recovery_h = (stress_data.get("recovery_high") or 0) / 3600.0
    fig = horizontal_bar(
        ["Stress", "Recovery"],
        [round(stress_h, 1), round(recovery_h, 1)],
        fixed_color=None,
        max_val=16,
        title="Stress vs Recovery (hours)",
    )
    if fig:
        # Override colors manually
        fig.data[0].marker.color = [RED, GREEN]
        st.plotly_chart(fig, width="stretch")

# Stress/Recovery trend
stress_trend_df = provider.stress_trend(start, end)
if not stress_trend_df.empty:
    fig = stacked_area(
        stress_trend_df,
        "day",
        y_cols=["stress_h", "recovery_h"],
        colors=[RED, GREEN],
        title="Stress vs Recovery Trend (hours)",
    )
    st.plotly_chart(fig, width="stretch")

st.markdown("---")

# ======== Resilience Section ========
st.subheader("Resilience")
res_data = provider.resilience_latest(end)

c1, c2 = st.columns([1, 2])
with c1:
    stat_card_mapped("Resilience Level", res_data.get("level"), RESILIENCE_MAP)
    contrib_keys = ["Sleep Recovery", "Daytime Recovery", "Stress"]
    names = [k for k in contrib_keys if k in res_data and res_data[k] is not None]
    vals = [round(res_data[k], 1) for k in names]
    if names:
        fig = horizontal_bar(names, vals, fixed_color=PURPLE, max_val=100, title="Resilience Contributors")
        st.plotly_chart(fig, width="stretch")

with c2:
    # Resilience level timeline
    res_timeline_df = provider.resilience_timeline(start, end)
    if not res_timeline_df.empty:
        # Convert to segments
        segments = []
        current_level = None
        seg_start = None
        for _, row in res_timeline_df.iterrows():
            day = pd.Timestamp(row["day"])
            level = row["level"]
            if level != current_level:
                if current_level is not None:
                    segments.append({"start": seg_start, "end": day, "state": current_level})
                current_level = level
                seg_start = day
        if current_level is not None:
            segments.append(
                {
                    "start": seg_start,
                    "end": day + pd.Timedelta(days=1),
                    "state": current_level,
                }
            )
        if segments:
            seg_df = pd.DataFrame(segments)
            fig = state_timeline(seg_df, RESILIENCE_TIMELINE_COLORS, title="Resilience Level Timeline")
            if fig:
                st.plotly_chart(fig, width="stretch")

st.markdown("---")

# ======== Cardiovascular Age Section ========
st.subheader("Cardiovascular Age")
c1, c2 = st.columns([1, 3])

with c1:
    gauge_chart(
        scores.get("cardio_age"),
        min_val=15,
        max_val=80,
        title="Cardiovascular Age",
        thresholds=CARDIO_AGE_THRESHOLDS,
        unit=" yrs",
    )

with c2:
    cardio_df = provider.cardio_age_trend(start, end)
    if not cardio_df.empty:
        fig = line_chart(cardio_df, "day", "vascular_age", colors=[PURPLE], title="Cardiovascular Age Trend", fill=True)
        st.plotly_chart(fig, width="stretch")

st.markdown("---")

# ======== VO2 Max Section ========
st.subheader("VO2 Max")
c1, c2, c3 = st.columns([1, 1, 3])

with c1:
    stat_card("VO2 Max", scores.get("vo2_max"), thresholds=VO2_THRESHOLDS, fmt=".1f")
with c2:
    stat_card("Personal Best", scores.get("vo2_max_pb"), color=ORANGE, fmt=".1f")
with c3:
    vo2_df = provider.vo2_max_trend(start, end)
    if not vo2_df.empty:
        fig = line_chart(vo2_df, "day", "vo2_max", title="VO2 Max Trend", fill=True)
        st.plotly_chart(fig, width="stretch")
