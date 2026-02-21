"""Stat cards and gauge components matching Grafana panels."""
import streamlit as st
import plotly.graph_objects as go

from components.theme import get_threshold_color, hex_to_rgba


def stat_card(title, value, unit="", color=None, thresholds=None, fmt=None):
    """Render a Grafana-style stat card with optional threshold coloring."""
    if thresholds and value is not None:
        color = get_threshold_color(value, thresholds)
    color = color or "#1F77B4"

    if value is None:
        display = "N/A"
    elif fmt:
        display = f"{value:{fmt}}"
    elif isinstance(value, float):
        display = f"{value:.1f}"
    else:
        display = f"{value:,}" if isinstance(value, int) else str(value)

    st.markdown(f"""
    <div style="background:rgba(255,255,255,0.05); border-radius:8px; padding:16px;
                text-align:center; border-left:4px solid {color}; margin-bottom:8px;">
        <div style="font-size:0.8rem; color:#999; margin-bottom:4px;">{title}</div>
        <div style="font-size:1.8rem; font-weight:bold; color:{color};">{display}{unit}</div>
    </div>
    """, unsafe_allow_html=True)


def stat_card_mapped(title, raw_value, mapping):
    """Stat card for enum values (stress summary, resilience level)."""
    if raw_value and raw_value in mapping:
        label, color = mapping[raw_value]
    else:
        label, color = "N/A", "#888888"

    st.markdown(f"""
    <div style="background:rgba(255,255,255,0.05); border-radius:8px; padding:16px;
                text-align:center; border-left:4px solid {color}; margin-bottom:8px;">
        <div style="font-size:0.8rem; color:#999; margin-bottom:4px;">{title}</div>
        <div style="font-size:1.8rem; font-weight:bold; color:{color};">{label}</div>
    </div>
    """, unsafe_allow_html=True)


def gauge_chart(value, min_val=0, max_val=100, title="", thresholds=None, unit=""):
    """Plotly gauge indicator matching Grafana gauge panels."""
    if value is None:
        st.markdown(f"""
        <div style="background:rgba(255,255,255,0.05); border-radius:8px; padding:16px;
                    text-align:center; margin-bottom:8px;">
            <div style="font-size:0.8rem; color:#999; margin-bottom:4px;">{title}</div>
            <div style="font-size:1.8rem; font-weight:bold; color:#888;">N/A</div>
        </div>
        """, unsafe_allow_html=True)
        return

    steps = []
    if thresholds:
        for i, (cutoff, color) in enumerate(thresholds):
            upper = thresholds[i + 1][0] if i + 1 < len(thresholds) else max_val
            steps.append({"range": [cutoff, upper], "color": hex_to_rgba(color, 0.2)})

    bar_color = get_threshold_color(value, thresholds) if thresholds else "#1F77B4"

    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=value,
        number={"suffix": unit, "font": {"size": 28}},
        gauge={
            "axis": {"range": [min_val, max_val], "tickwidth": 1},
            "bar": {"color": bar_color, "thickness": 0.7},
            "steps": steps,
            "threshold": {
                "line": {"color": "white", "width": 2},
                "thickness": 0.8,
                "value": value,
            },
        },
    ))
    fig.update_layout(
        height=200,
        margin={"t": 30, "b": 0, "l": 30, "r": 30},
        paper_bgcolor="rgba(0,0,0,0)",
        font={"color": "#e0e0e0"},
    )
    st.plotly_chart(fig, width="stretch")
    if title:
        st.markdown(
            f"<p style='text-align:center; color:#999; margin-top:-10px;'>{title}</p>",
            unsafe_allow_html=True,
        )
