"""Ring, battery, and local profile dashboard."""

from datetime import date, timedelta

from components.charts import line_chart
from components.metrics import stat_card
from components.theme import GREEN, ORANGE
from data.providers import get_provider

import streamlit as st

st.set_page_config(page_title="Oura - Ring", layout="wide", page_icon=":material/circle:")

from components.sidebar import render_sidebar  # noqa: E402

render_sidebar()
st.title("Ring")

provider = get_provider()
start = st.session_state.get("start_date", date.today() - timedelta(days=30))
end = st.session_state.get("end_date", date.today())

summary = provider.ring_summary(start, end)
hardware_labels = {
    "gen1": "Oura Ring 1",
    "gen2": "Oura Ring 2",
    "gen2m": "Oura Ring 2",
    "gen3": "Oura Ring 3",
    "gen4": "Oura Ring 4",
    "or5": "Oura Ring 5",
}

c1, c2, c3, c4 = st.columns(4)
with c1:
    stat_card("Battery", summary.get("latest_level"), unit="%", color=GREEN)
with c2:
    stat_card("Range Minimum", summary.get("minimum_level"), unit="%", color=ORANGE)
with c3:
    st.metric("Hardware", hardware_labels.get(summary.get("hardware_type"), summary.get("hardware_type") or "N/A"))
with c4:
    st.metric("Firmware", summary.get("firmware_version") or "N/A")

battery = provider.battery_series(start, end)
if not battery.empty:
    fig = line_chart(battery, "timestamp", "level", colors=[GREEN], title="Battery Level", y_label="%", smooth=False)
    fig.update_yaxes(range=[0, 100])
    st.plotly_chart(fig, width="stretch")
else:
    st.info("No battery data available.")

left, right = st.columns(2)
with left:
    st.subheader("Ring Configurations")
    configs = provider.ring_configurations()
    if configs.empty:
        st.info("No ring configuration available.")
    else:
        if "hardware_type" in configs:
            configs["hardware_type"] = configs["hardware_type"].map(lambda value: hardware_labels.get(value, value))
        if "set_up_at" in configs:
            configs["set_up_at"] = configs["set_up_at"].astype(str).str.slice(0, 10)
        configs = configs.rename(
            columns={
                "color": "Color",
                "design": "Design",
                "firmware_version": "Firmware",
                "hardware_type": "Hardware",
                "set_up_at": "Set Up",
                "size": "Size",
            }
        )
        st.dataframe(configs, width="stretch", hide_index=True)

with right:
    st.subheader("Profile")
    profile = provider.personal_profile()
    if not profile:
        st.info("No profile data available.")
    else:
        p1, p2 = st.columns(2)
        p1.metric("Age", profile.get("age") or "N/A")
        height = profile.get("height")
        p2.metric("Height", f"{height * 100:.0f} cm" if height else "N/A")
        p1.metric("Weight", f"{profile['weight']:.1f} kg" if profile.get("weight") else "N/A")
        p2.metric("Biological Sex", str(profile.get("biological_sex") or "N/A").title())
