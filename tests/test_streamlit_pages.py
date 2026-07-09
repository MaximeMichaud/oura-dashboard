from pathlib import Path

import pytest

STREAMLIT_DIR = Path(__file__).parent.parent / "streamlit"

PAGE_ICONS = {
    "app.py": ":material/health_metrics:",
    "pages/1_Overview.py": ":material/dashboard:",
    "pages/2_Sleep.py": ":material/bedtime:",
    "pages/3_Readiness.py": ":material/bolt:",
    "pages/4_Activity.py": ":material/directions_run:",
    "pages/5_Body.py": ":material/monitor_heart:",
    "pages/6_Heart_Rate.py": ":material/favorite:",
    "pages/7_Context.py": ":material/event_note:",
    "pages/8_Ring.py": ":material/circle:",
}


@pytest.mark.parametrize(("relative_path", "icon"), PAGE_ICONS.items())
def test_streamlit_pages_have_distinct_icons(relative_path, icon):
    source = (STREAMLIT_DIR / relative_path).read_text()

    assert f'page_icon="{icon}"' in source
    assert ":ring:" not in source


def test_sleep_contributors_do_not_require_matplotlib():
    source = (STREAMLIT_DIR / "pages/2_Sleep.py").read_text()

    assert "background_gradient" not in source
    assert "st.column_config.ProgressColumn" in source
