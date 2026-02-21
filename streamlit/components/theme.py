"""Color palette and threshold definitions matching Grafana dashboards."""

# -- Color palette (from Grafana) --
BLUE = "#1F77B4"
GREEN = "#2CA02C"
GREEN_LIGHT = "#73BF69"
ORANGE = "#FF7F0E"
ORANGE_LIGHT = "#FFBB78"
RED = "#D62728"
RED_LIGHT = "#F2495C"
YELLOW = "#FF9830"
PURPLE = "#9467BD"
CYAN = "#17BECF"
LIGHT_BLUE = "#7EB2DD"
PINK = "#E377C2"
DARK_GREEN = "#145A32"

# Sleep phase colors
SLEEP_PHASE_COLORS = {
    "Deep": BLUE,
    "Light": LIGHT_BLUE,
    "REM": PURPLE,
    "Awake": RED,
}

# -- Thresholds: list of (min_value, color) --
SCORE_THRESHOLDS = [(0, RED_LIGHT), (60, YELLOW), (80, GREEN_LIGHT)]
SPO2_THRESHOLDS = [(0, RED_LIGHT), (92, YELLOW), (95, GREEN_LIGHT)]
EFFICIENCY_THRESHOLDS = [(0, RED_LIGHT), (75, YELLOW), (90, GREEN_LIGHT)]
CARDIO_AGE_THRESHOLDS = [(0, GREEN_LIGHT), (40, YELLOW), (55, RED_LIGHT)]
VO2_THRESHOLDS = [(0, RED_LIGHT), (35, YELLOW), (45, GREEN_LIGHT)]
BREATHING_THRESHOLDS = [(0, GREEN_LIGHT), (5, YELLOW), (15, RED_LIGHT)]

# -- Enum value mappings: raw -> (display_label, color) --
STRESS_MAP = {
    "restored": ("Restored", GREEN),
    "normal": ("Normal", YELLOW),
    "stressful": ("Stressful", RED_LIGHT),
}

RESILIENCE_MAP = {
    "limited": ("Limited", RED_LIGHT),
    "adequate": ("Adequate", YELLOW),
    "solid": ("Solid", ORANGE_LIGHT),
    "strong": ("Strong", GREEN_LIGHT),
    "exceptional": ("Exceptional", BLUE),
}

RESILIENCE_TIMELINE_COLORS = {
    "limited": RED,
    "adequate": ORANGE,
    "solid": ORANGE_LIGHT,
    "strong": GREEN,
    "exceptional": BLUE,
}


def get_threshold_color(value, thresholds):
    """Return color for a value based on threshold list [(cutoff, color), ...]."""
    if value is None:
        return "#888888"
    color = thresholds[0][1]
    for cutoff, c in thresholds:
        if value >= cutoff:
            color = c
    return color


def hex_to_rgba(hex_color, alpha=0.13):
    """Convert '#RRGGBB' to 'rgba(r,g,b,alpha)' for Plotly compatibility."""
    if not hex_color:
        return f"rgba(128,128,128,{alpha})"
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"rgba({r},{g},{b},{alpha})"
