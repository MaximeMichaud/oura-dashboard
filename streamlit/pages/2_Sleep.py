"""Sleep dashboard - phases, intra-night HR/HRV, trends, bedtime."""
import streamlit as st
import pandas as pd
from datetime import date, timedelta

from data.providers import get_provider
from components.metrics import stat_card
from components.charts import (line_chart, pie_chart, stacked_area, bar_chart,
                                state_timeline, intranight_chart)
from components.theme import (EFFICIENCY_THRESHOLDS,
                               SLEEP_PHASE_COLORS, BLUE, GREEN, RED, PURPLE,
                               CYAN, PINK)


def _to_local(ts: pd.Timestamp) -> pd.Timestamp:
    """Convert a timezone-aware timestamp to the user's local time (naive)."""
    if ts.tzinfo is not None:
        tz = st.session_state.get("user_timezone", "UTC")
        return ts.tz_convert(tz).tz_localize(None)
    return ts

st.set_page_config(page_title="Oura - Sleep", layout="wide", page_icon=":ring:")

from components.sidebar import render_sidebar
render_sidebar()

st.title("Sleep")

provider = get_provider()
start = st.session_state.get("start_date", date.today() - timedelta(days=30))
end = st.session_state.get("end_date", date.today())

# -- Night selector in sidebar --
nights = provider.available_nights(start, end)
if not nights:
    st.warning("No sleep data available for this time range.")
    st.stop()

selected_night = st.sidebar.selectbox(
    "Night",
    nights,
    format_func=lambda d: str(d),
)

session = provider.sleep_session(selected_night)
if not session:
    st.warning("No sleep data for this night.")
    st.stop()

# -- Row 1: Stats for selected night --
c1, c2, c3, c4, c5, c6 = st.columns(6)

total_h = (session.get("total_sleep") or 0) / 3600.0
with c1:
    stat_card("Total Sleep", total_h, unit="h", color=BLUE, fmt=".1f")
with c2:
    stat_card("Efficiency", session.get("efficiency"), unit="%",
              thresholds=EFFICIENCY_THRESHOLDS)
with c3:
    stat_card("Avg HRV", session.get("average_hrv"), unit=" ms",
              color=PURPLE, fmt=".0f")
with c4:
    stat_card("Lowest HR", session.get("lowest_heart_rate"), unit=" bpm",
              color=RED, fmt=".0f")
with c5:
    latency_min = (session.get("latency") or 0) / 60.0
    stat_card("Latency", latency_min, unit=" min", color="#7EB2DD", fmt=".0f")
with c6:
    stat_card("Avg Breathing", session.get("average_breath"), unit=" br/min",
              color=CYAN, fmt=".1f")

st.markdown("---")

# -- Row 2: Phases donut + Phases stacked % --
c1, c2 = st.columns([1, 2])

with c1:
    phases = provider.sleep_phases_pie(selected_night)
    if phases:
        labels = ["Deep", "Light", "REM", "Awake"]
        values = [phases.get(k.lower(), 0) for k in labels]
        colors = [SLEEP_PHASE_COLORS[k] for k in labels]
        fig = pie_chart(labels, values, colors=colors,
                        title="Sleep Phases (minutes)")
        st.plotly_chart(fig, width="stretch")

with c2:
    stacked_df = provider.sleep_phases_stacked(start, end)
    if not stacked_df.empty:
        fig = stacked_area(
            stacked_df, "day",
            y_cols=["deep", "light", "rem", "awake"],
            colors=[BLUE, "#7EB2DD", PURPLE, RED],
            title="Sleep Phases Stacked (%)",
            percent=True,
        )
        st.plotly_chart(fig, width="stretch")

# -- Row 3: Sleep Phase Timeline --
phase_str = session.get("sleep_phase_5_min") or ""
bedtime_raw = session.get("bedtime_start")
if phase_str and bedtime_raw:
    bedtime = _to_local(pd.Timestamp(bedtime_raw))
    PHASE_MAP = {"1": "Deep", "2": "Light", "3": "REM", "4": "Awake"}

    # Find bounds (first/last non-awake)
    sleep_indices = [i for i, ch in enumerate(phase_str) if ch in ("1", "2", "3")]
    if sleep_indices:
        lo, hi = sleep_indices[0], sleep_indices[-1]

        # Build segments
        segments = []
        current_phase = None
        seg_start = None
        for i in range(lo, hi + 1):
            phase = PHASE_MAP.get(phase_str[i], "Unknown")
            t = bedtime + pd.Timedelta(minutes=5 * i)
            if phase != current_phase:
                if current_phase is not None:
                    segments.append({"start": seg_start, "end": t, "state": current_phase})
                current_phase = phase
                seg_start = t
        if current_phase is not None:
            t_end = bedtime + pd.Timedelta(minutes=5 * (hi + 1))
            segments.append({"start": seg_start, "end": t_end, "state": current_phase})

        if segments:
            seg_df = pd.DataFrame(segments)
            fig = state_timeline(seg_df, SLEEP_PHASE_COLORS,
                                 title="Sleep Phase Timeline")
            if fig:
                st.plotly_chart(fig, width="stretch")

# -- Row 4: Intra-night HR + HRV --
c1, c2 = st.columns(2)

# Decode HR items
hr_data = session.get("heart_rate", {})
hrv_data = session.get("hrv", {})

# Find bounds from sleep phases
sleep_indices = [i for i, ch in enumerate(phase_str) if ch in ("1", "2", "3")] if phase_str else []

with c1:
    hr_items = hr_data.get("items", []) if isinstance(hr_data, dict) else []
    if hr_items and bedtime_raw and sleep_indices:
        lo, hi = sleep_indices[0], sleep_indices[-1]
        bt = _to_local(pd.Timestamp(bedtime_raw))
        records = []
        for i in range(lo, min(hi + 1, len(hr_items))):
            val = hr_items[i]
            if val is not None:
                records.append({
                    "time": bt + pd.Timedelta(minutes=5 * i),
                    "value": float(val),
                })
        if records:
            hr_df = pd.DataFrame(records)
            fig = intranight_chart(hr_df, RED, title="Heart Rate During Sleep",
                                   unit="bpm")
            if fig:
                st.plotly_chart(fig, width="stretch")

with c2:
    hrv_items = hrv_data.get("items", []) if isinstance(hrv_data, dict) else []
    if hrv_items and bedtime_raw and sleep_indices:
        lo, hi = sleep_indices[0], sleep_indices[-1]
        bt = _to_local(pd.Timestamp(bedtime_raw))
        records = []
        for i in range(lo, min(hi + 1, len(hrv_items))):
            val = hrv_items[i]
            if val is not None:
                records.append({
                    "time": bt + pd.Timedelta(minutes=5 * i),
                    "value": float(val),
                })
        if records:
            hrv_df = pd.DataFrame(records)
            fig = intranight_chart(hrv_df, PURPLE, title="HRV During Sleep",
                                   unit="ms")
            if fig:
                st.plotly_chart(fig, width="stretch")

st.markdown("---")

# -- Row 5: HRV Trend + Resting HR Trend + Efficiency Trend --
c1, c2, c3 = st.columns(3)

with c1:
    hrv_trend_df = provider.sleep_hrv_trend(start, end)
    if not hrv_trend_df.empty:
        hrv_trend_df["7d_avg"] = hrv_trend_df["hrv"].rolling(7, min_periods=1).mean()
        fig = line_chart(hrv_trend_df, "day", ["hrv", "7d_avg"],
                         colors=[PURPLE, PINK],
                         title="HRV Trend", y_label="ms")
        st.plotly_chart(fig, width="stretch")

with c2:
    hr_trend_df = provider.sleep_resting_hr_trend(start, end)
    if not hr_trend_df.empty:
        fig = line_chart(hr_trend_df, "day", "hr", colors=[RED],
                         title="Resting HR Trend", y_label="bpm")
        st.plotly_chart(fig, width="stretch")

with c3:
    eff_df = provider.sleep_efficiency_trend(start, end)
    if not eff_df.empty:
        fig = line_chart(eff_df, "day", "efficiency", colors=[GREEN],
                         title="Efficiency Trend", y_label="%")
        st.plotly_chart(fig, width="stretch")

# -- Row 6: Sleep Contributors Table --
st.subheader("Sleep Contributors")
contrib_table = provider.sleep_contributors_table(start, end)
if not contrib_table.empty:
    st.dataframe(
        contrib_table.style.background_gradient(
            cmap="RdYlGn", subset=[c for c in contrib_table.columns if c != "Date"],
            vmin=0, vmax=100,
        ),
        width="stretch", hide_index=True,
    )

# -- Row 7: Latency + Breathing trends --
c1, c2 = st.columns(2)

with c1:
    lat_df = provider.sleep_latency_trend(start, end)
    if not lat_df.empty:
        lat_df["7d_avg"] = lat_df["latency_min"].rolling(7, min_periods=1).mean()
        fig = line_chart(lat_df, "day", ["latency_min", "7d_avg"],
                         colors=["#7EB2DD", BLUE],
                         title="Sleep Latency Trend", y_label="min")
        st.plotly_chart(fig, width="stretch")

with c2:
    breath_df = provider.sleep_breathing_trend(start, end)
    if not breath_df.empty:
        fig = line_chart(breath_df, "day", "breath", colors=[CYAN],
                         title="Breathing Rate Trend", y_label="br/min", fill=True)
        st.plotly_chart(fig, width="stretch")

# -- Row 8: Optimal Bedtime + Nap Frequency --
c1, c2, c3 = st.columns(3)

with c1:
    bedtime_data = provider.optimal_bedtime(end)
    if bedtime_data:
        bt_start = bedtime_data.get("optimal_bedtime_start")
        bt_end = bedtime_data.get("optimal_bedtime_end")
        if bt_start is not None and bt_end is not None:
            # Convert seconds offset to HH:MM
            def secs_to_time(s):
                if s is None:
                    return "N/A"
                # Handle negative (before midnight) and positive (after midnight)
                total_secs = 86400 + s if s < 0 else s
                hours = (total_secs // 3600) % 24
                minutes = (total_secs % 3600) // 60
                return f"{hours:02d}:{minutes:02d}"
            display = f"{secs_to_time(bt_start)} - {secs_to_time(bt_end)}"
            stat_card("Optimal Bedtime", display, color=BLUE)
        else:
            rec = bedtime_data.get("recommendation", "")
            stat_card("Bedtime", rec.replace("_", " ").title() if rec else "N/A",
                      color=BLUE)

with c2:
    rec = bedtime_data.get("recommendation", "") if bedtime_data else ""
    stat_card("Recommendation", rec.replace("_", " ").title() if rec else "N/A",
              color=PURPLE)

with c3:
    nap_df = provider.nap_frequency(start, end)
    if not nap_df.empty:
        fig = bar_chart(nap_df, "day", "naps", color="#7EB2DD",
                        title="Nap Frequency")
        st.plotly_chart(fig, width="stretch")
    else:
        st.info("No naps recorded in this period.")
