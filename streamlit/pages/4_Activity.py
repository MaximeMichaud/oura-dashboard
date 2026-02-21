"""Activity dashboard - steps, calories, MET, workouts."""
import streamlit as st
import pandas as pd
from datetime import date, timedelta

from data.providers import get_provider
from components.metrics import stat_card, gauge_chart
from components.charts import line_chart, bar_chart, pie_chart, horizontal_bar
from components.theme import (SCORE_THRESHOLDS, ORANGE, RED,
                               LIGHT_BLUE)

st.set_page_config(page_title="Oura - Activity", layout="wide", page_icon=":ring:")

from components.sidebar import render_sidebar
render_sidebar()

st.title("Activity")

provider = get_provider()
start = st.session_state.get("start_date", date.today() - timedelta(days=30))
end = st.session_state.get("end_date", date.today())

latest = provider.activity_latest(end)

# -- Row 1: Stats --
c1, c2, c3, c4 = st.columns(4)
with c1:
    gauge_chart(latest.get("active_calories"), min_val=0, max_val=1500,
                title="Active Calories", unit=" kcal")
with c2:
    stat_card("Steps", latest.get("steps"), color=ORANGE)
with c3:
    stat_card("Total Calories", latest.get("total_calories"), unit=" kcal", color=RED)
with c4:
    stat_card("Distance", latest.get("distance_km"), unit=" km", color=ORANGE, fmt=".1f")

st.markdown("---")

# -- Row 2: Steps 30d + Activity Breakdown + MET Trend --
c1, c2, c3 = st.columns(3)

with c1:
    steps_df = provider.steps_30d(end)
    if not steps_df.empty:
        fig = bar_chart(steps_df, "day", "steps", color=ORANGE, title="Steps (30d)")
        st.plotly_chart(fig, width="stretch")

with c2:
    labels = ["High", "Medium", "Low", "Sedentary", "Rest"]
    values = [latest.get(k, 0) or 0 for k in ["high_h", "medium_h", "low_h", "sedentary_h", "resting_h"]]
    if any(v > 0 for v in values):
        fig = pie_chart(labels, values,
                        colors=[RED, ORANGE, "#FFBB78", "#AEC7E8", LIGHT_BLUE],
                        title="Activity Breakdown (hours)")
        st.plotly_chart(fig, width="stretch")

with c3:
    trend_df = provider.activity_trend(start, end)
    if not trend_df.empty:
        fig = line_chart(trend_df, "day", "met", colors=[ORANGE],
                         title="Avg MET Trend", y_label="MET", fill=True)
        st.plotly_chart(fig, width="stretch")

# -- Row 3: Activity Contributors + Activity Score --
c1, c2, c3 = st.columns([2, 1, 2])

with c1:
    contrib_keys = ["Daily Targets", "Move Hourly", "Recovery Time",
                    "Stay Active", "Training Freq", "Training Volume"]
    names = [k for k in contrib_keys if k in latest and latest[k] is not None]
    vals = [latest[k] for k in names]
    if names:
        fig = horizontal_bar(names, vals, thresholds=SCORE_THRESHOLDS,
                             title="Activity Contributors")
        st.plotly_chart(fig, width="stretch")

with c2:
    gauge_chart(latest.get("score"), min_val=0, max_val=100,
                title="Activity Score", thresholds=SCORE_THRESHOLDS)

with c3:
    if not trend_df.empty:
        fig = line_chart(trend_df, "day", "score", colors=[ORANGE],
                         title="Activity Score Trend")
        st.plotly_chart(fig, width="stretch")

st.markdown("---")

# -- Row 4: Calories + Distance Trends --
c1, c2 = st.columns(2)

with c1:
    if not trend_df.empty:
        fig = line_chart(trend_df, "day", ["total_calories", "active_calories"],
                         colors=[RED, ORANGE],
                         title="Calories Trend", y_label="kcal")
        st.plotly_chart(fig, width="stretch")

with c2:
    if not trend_df.empty:
        fig = line_chart(trend_df, "day", "distance_km", colors=[ORANGE],
                         title="Walking Distance", y_label="km")
        st.plotly_chart(fig, width="stretch")

# -- Row 5: Calories vs Target + Steps vs Target --
c1, c2 = st.columns(2)

with c1:
    if not trend_df.empty and "target_calories" in trend_df.columns:
        fig = line_chart(trend_df, "day", ["active_calories", "target_calories"],
                         colors=[ORANGE, "#AAAAAA"],
                         dashed=["target_calories"],
                         title="Calories vs Target", y_label="kcal")
        st.plotly_chart(fig, width="stretch")

with c2:
    if not trend_df.empty and "steps" in trend_df.columns:
        fig = line_chart(trend_df, "day", "steps", colors=[ORANGE],
                         title="Steps Trend", y_label="steps")
        st.plotly_chart(fig, width="stretch")

# -- Row 6: Workouts --
st.subheader("Workouts")
workout_df = provider.workouts(start, end)

if not workout_df.empty:
    # Workout table
    display_df = workout_df.copy()
    if "activity" in display_df.columns:
        display_df["activity"] = display_df["activity"].str.replace("_", " ").str.title()
    if "distance" in display_df.columns:
        display_df["distance"] = (display_df["distance"].fillna(0) / 1000).round(1)
        display_df = display_df.rename(columns={"distance": "distance_km"})
    st.dataframe(display_df, width="stretch", hide_index=True)

    # Workout charts
    c1, c2, c3 = st.columns(3)

    with c1:
        if "calories" in workout_df.columns:
            cal_by_day = workout_df.groupby("day")["calories"].sum().reset_index()
            cal_by_day.columns = ["day", "calories"]
            fig = bar_chart(cal_by_day, "day", "calories", color=ORANGE,
                            title="Workout Calories")
            st.plotly_chart(fig, width="stretch")

    with c2:
        if "activity" in workout_df.columns:
            type_counts = workout_df["activity"].str.replace("_", " ").str.title().value_counts()
            fig = pie_chart(type_counts.index.tolist(), type_counts.values.tolist(),
                            title="Workout Types")
            st.plotly_chart(fig, width="stretch")

    with c3:
        if "start_datetime" in workout_df.columns and "end_datetime" in workout_df.columns:
            wk = workout_df.copy()
            wk["duration_min"] = (pd.to_datetime(wk["end_datetime"]) -
                                  pd.to_datetime(wk["start_datetime"])).dt.total_seconds() / 60
            dur_by_day = wk.groupby("day")["duration_min"].sum().reset_index()
            fig = bar_chart(dur_by_day, "day", "duration_min", color=ORANGE,
                            title="Workout Duration (min)")
            st.plotly_chart(fig, width="stretch")
else:
    st.info("No workout data available for this period.")
