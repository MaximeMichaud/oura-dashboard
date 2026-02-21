"""Oura Dashboard - Streamlit app entrypoint."""
import streamlit as st

st.set_page_config(
    page_title="Oura Dashboard",
    page_icon=":ring:",
    layout="wide",
    initial_sidebar_state="expanded",
)

from components.sidebar import render_sidebar
render_sidebar()

# -- Main page content --
st.title("Oura Dashboard")
st.markdown("Select a page from the sidebar to explore your health data.")

mode = st.session_state.get("provider_mode", "demo")
if mode == "demo":
    st.info("Running in demo mode with sample data. Enter your Oura token in the sidebar to see your real data.")
elif mode == "api":
    st.success("Connected to Oura API. Your data is being fetched live.")
elif mode == "postgresql":
    st.success("Connected to PostgreSQL database.")

st.markdown("""
### Pages

- **Overview** - Scores, steps, stress, resilience, weekly trends
- **Sleep** - Phases, intra-night HR/HRV, optimal bedtime, 90-day trends
- **Readiness** - Score, temperature, all contributors
- **Activity** - Steps, calories, MET, workouts, targets
- **Body** - SpO2, stress vs recovery, resilience, cardiovascular age, VO2 Max
""")
