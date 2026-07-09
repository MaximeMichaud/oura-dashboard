"""Sessions, tags, and rest mode dashboard."""

from datetime import date, timedelta

from components.charts import bar_chart, pie_chart
from components.theme import BLUE, PURPLE
from data.providers import get_provider

import streamlit as st

st.set_page_config(page_title="Oura - Context", layout="wide", page_icon=":material/event_note:")

from components.sidebar import render_sidebar  # noqa: E402

render_sidebar()
st.title("Context")

provider = get_provider()
start = st.session_state.get("start_date", date.today() - timedelta(days=30))
end = st.session_state.get("end_date", date.today())

sessions = provider.sessions(start, end)
tags = provider.tags(start, end)
rest_modes = provider.rest_modes(start, end)

c1, c2, c3 = st.columns(3)
c1.metric("Sessions", len(sessions))
c2.metric("Tags", len(tags))
c3.metric("Rest Mode Periods", len(rest_modes))

tab_sessions, tab_tags, tab_rest = st.tabs(["Sessions", "Tags", "Rest Mode"])

with tab_sessions:
    if sessions.empty:
        st.info("No sessions in the selected range.")
    else:
        left, right = st.columns(2)
        by_type = sessions.groupby("type", dropna=False).size().reset_index(name="count")
        with left:
            st.plotly_chart(bar_chart(by_type, "type", "count", color=BLUE, title="Sessions by Type"), width="stretch")
        with right:
            mood = sessions.dropna(subset=["mood"]).groupby("mood").size().reset_index(name="count")
            if not mood.empty:
                st.plotly_chart(pie_chart(mood["mood"], mood["count"], title="Mood"), width="stretch")
        st.dataframe(sessions, width="stretch", hide_index=True)

with tab_tags:
    if tags.empty:
        st.info("No tags in the selected range.")
    else:
        by_kind = tags.groupby("kind").size().reset_index(name="count")
        st.plotly_chart(bar_chart(by_kind, "kind", "count", color=PURPLE, title="Tags by Format"), width="stretch")
        st.dataframe(tags, width="stretch", hide_index=True)

with tab_rest:
    if rest_modes.empty:
        st.info("No rest mode periods in the selected range.")
    else:
        st.dataframe(rest_modes, width="stretch", hide_index=True)
