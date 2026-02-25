"""Reusable Plotly chart builders matching Grafana panel types."""

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots

import streamlit as st
from components.theme import get_threshold_color, hex_to_rgba

_LAYOUT_DEFAULTS = dict(
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    font=dict(color="#e0e0e0"),
    margin=dict(t=40, b=40, l=50, r=20),
    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    xaxis=dict(gridcolor="rgba(255,255,255,0.08)"),
    yaxis=dict(gridcolor="rgba(255,255,255,0.08)"),
    height=350,
)


def _apply_defaults(fig, title="", height=None):
    kw = dict(_LAYOUT_DEFAULTS)
    if title:
        kw["title"] = dict(text=title, font=dict(size=14))
    if height:
        kw["height"] = height
    fig.update_layout(**kw)
    return fig


# -- Line chart --
def line_chart(df, x, y_cols, colors=None, title="", y_label="", fill=False, smooth=True, dashed=None, height=None):
    """Multi-series line chart. dashed: list of column names to draw dashed."""
    fig = go.Figure()
    dashed = dashed or []
    for i, col in enumerate(y_cols if isinstance(y_cols, list) else [y_cols]):
        color = colors[i] if colors and i < len(colors) else None
        dash = "dash" if col in dashed else "solid"
        fig.add_trace(
            go.Scatter(
                x=df[x],
                y=df[col],
                name=col,
                mode="lines",
                line=dict(color=color, width=2, dash=dash, shape="spline" if smooth else "linear"),
                fill="tozeroy" if fill and i == 0 else None,
                fillcolor=hex_to_rgba(color, 0.13) if fill and color else None,
            )
        )
    if y_label:
        fig.update_yaxes(title_text=y_label)
    return _apply_defaults(fig, title, height)


# -- Dual-axis chart --
def dual_axis_chart(
    df,
    x,
    left_cols,
    right_cols,
    title="",
    left_label="",
    right_label="",
    left_colors=None,
    right_colors=None,
    bar_cols=None,
    height=None,
):
    """Dual Y-axis chart using secondary_y. bar_cols rendered as bars."""
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    bar_cols = bar_cols or []
    for i, col in enumerate(left_cols):
        color = left_colors[i] if left_colors and i < len(left_colors) else None
        is_bar = col in bar_cols
        if is_bar:
            fig.add_trace(
                go.Bar(
                    x=df[x],
                    y=df[col],
                    name=col,
                    marker_color=color,
                    opacity=0.6,
                ),
                secondary_y=False,
            )
        else:
            fig.add_trace(
                go.Scatter(
                    x=df[x],
                    y=df[col],
                    name=col,
                    mode="lines",
                    line=dict(color=color, width=2, shape="spline"),
                ),
                secondary_y=False,
            )
    for i, col in enumerate(right_cols):
        color = right_colors[i] if right_colors and i < len(right_colors) else None
        is_bar = col in bar_cols
        if is_bar:
            fig.add_trace(
                go.Bar(
                    x=df[x],
                    y=df[col],
                    name=col,
                    marker_color=color,
                    opacity=0.6,
                ),
                secondary_y=True,
            )
        else:
            fig.add_trace(
                go.Scatter(
                    x=df[x],
                    y=df[col],
                    name=col,
                    mode="lines",
                    line=dict(color=color, width=2, shape="spline"),
                ),
                secondary_y=True,
            )
    fig.update_yaxes(title_text=left_label, secondary_y=False, gridcolor="rgba(255,255,255,0.08)")
    fig.update_yaxes(title_text=right_label, secondary_y=True, gridcolor="rgba(255,255,255,0.04)")
    return _apply_defaults(fig, title, height)


# -- Bar chart --
def bar_chart(df, x, y, color=None, title="", y_label="", thresholds=None, height=None):
    """Simple bar chart with optional per-bar threshold coloring."""
    if thresholds:
        colors = [get_threshold_color(v, thresholds) for v in df[y]]
        fig = go.Figure(go.Bar(x=df[x], y=df[y], marker_color=colors))
    else:
        fig = go.Figure(go.Bar(x=df[x], y=df[y], marker_color=color or "#FF7F0E"))
    if y_label:
        fig.update_yaxes(title_text=y_label)
    fig.update_xaxes(tickangle=-45)
    return _apply_defaults(fig, title, height)


# -- Stacked area --
def stacked_area(df, x, y_cols, colors=None, title="", percent=False, height=None):
    """Stacked area chart. percent=True for 0-100% normalization."""
    fig = go.Figure()
    groupnorm = "percent" if percent else None
    for i, col in enumerate(y_cols):
        color = colors[i] if colors and i < len(colors) else None
        fig.add_trace(
            go.Scatter(
                x=df[x],
                y=df[col],
                name=col,
                mode="lines",
                line=dict(color=color, width=0),
                stackgroup="one",
                groupnorm=groupnorm,
                fillcolor=color,
            )
        )
    if percent:
        fig.update_yaxes(range=[0, 100], ticksuffix="%")
    return _apply_defaults(fig, title, height)


# -- Pie / donut --
def pie_chart(labels, values, colors=None, title="", hole=0.4, height=None):
    """Donut or pie chart."""
    fig = go.Figure(
        go.Pie(
            labels=labels,
            values=values,
            hole=hole,
            marker=dict(colors=colors) if colors else {},
            textinfo="percent+label",
            textposition="inside",
        )
    )
    return _apply_defaults(fig, title, height or 300)


# -- Horizontal bar (bargauge) --
def horizontal_bar(names, values, thresholds=None, max_val=100, fixed_color=None, title="", height=None):
    """Horizontal bars for contributor scores."""
    if thresholds:
        colors = [get_threshold_color(v, thresholds) for v in values]
    else:
        colors = [fixed_color or "#9467BD"] * len(values)
    fig = go.Figure(
        go.Bar(
            y=names,
            x=values,
            orientation="h",
            marker_color=colors,
            text=[f"{v}" for v in values],
            textposition="auto",
        )
    )
    fig.update_xaxes(range=[0, max_val])
    fig.update_layout(yaxis=dict(autorange="reversed"))
    auto_height = max(200, len(names) * 35 + 60)
    return _apply_defaults(fig, title, height or auto_height)


# -- State timeline (Gantt-style) --
def state_timeline(df, color_map, title="", height=None):
    """Horizontal timeline from DataFrame with columns: start, end, state.
    Used for sleep phases and resilience level timeline."""
    if df.empty:
        st.info("No data available.")
        return None
    fig = px.timeline(
        df,
        x_start="start",
        x_end="end",
        y=pd.Series([""] * len(df)),
        color="state",
        color_discrete_map=color_map,
    )
    fig.update_layout(
        yaxis_visible=False,
        showlegend=True,
    )
    return _apply_defaults(fig, title, height or 180)


# -- Intra-night chart (HR/HRV) --
def intranight_chart(df, color, title="", unit="bpm", height=None):
    """Line chart for intra-night HR/HRV data with min/mean/max stats."""
    if df.empty:
        st.info(f"No {title.lower()} data available.")
        return None
    vmin, vmean, vmax = df["value"].min(), df["value"].mean(), df["value"].max()
    stats = f"Min: {vmin:.0f}  |  Mean: {vmean:.0f}  |  Max: {vmax:.0f}"
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=df["time"],
            y=df["value"],
            mode="lines",
            line=dict(color=color, width=2, shape="spline"),
            fill="tozeroy",
            fillcolor=hex_to_rgba(color, 0.13),
            name=title,
        )
    )
    fig.update_yaxes(title_text=unit)
    return _apply_defaults(fig, f"{title}<br><sup>{stats}</sup>", height)
