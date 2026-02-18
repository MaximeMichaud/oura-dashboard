import json
from pathlib import Path

import pytest

DASHBOARDS_DIR = Path(__file__).parent.parent / "grafana" / "provisioning" / "dashboards-json"


@pytest.fixture
def dashboard_dir():
    return DASHBOARDS_DIR


@pytest.fixture
def dashboard_files():
    return sorted(DASHBOARDS_DIR.glob("*.json"))


@pytest.fixture
def loaded_dashboards(dashboard_files):
    dashboards = []
    for f in dashboard_files:
        dashboards.append(json.loads(f.read_text()))
    return dashboards
