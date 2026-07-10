from pathlib import Path

ROOT = Path(__file__).parent.parent
CI_SEED_PATH = ROOT / "postgres/ci-seed.sql"


def test_grafana_validator_covers_all_dashboards_and_runtime_errors():
    source = (ROOT / "scripts/validate-dashboards.mjs").read_text()

    for uid in (
        "oura-overview",
        "oura-sleep",
        "oura-readiness",
        "oura-activity",
        "oura-body",
        "oura-heart-rate",
        "oura-context",
        "oura-ring",
    ):
        assert f'"{uid}"' in source

    assert 'page.on("pageerror"' in source
    assert 'page.on("console"' in source
    assert 'page.on("requestfailed"' in source
    assert 'page.on("response"' in source
    assert 'response.url().includes("/api/ds/query")' in source
    assert 'error !== "net::ERR_ABORTED"' in source
    assert 'error.message.includes("Network.getResponseBody")' in source
    assert "DashboardEditPaneSplitter body container" in source
    assert "element.scrollTo" in source
    assert "window.scrollTo" in source
    assert "dashboard-${viewportName}.png" in source
    assert "browser = await chromium.launch" in source
    assert "browser = undefined" in source


def test_ci_seed_covers_every_dashboard_data_family():
    source = CI_SEED_PATH.read_text()

    for table in (
        "daily_sleep",
        "daily_readiness",
        "daily_activity",
        "daily_spo2",
        "daily_stress",
        "daily_resilience",
        "daily_cardiovascular_age",
        "daily_vo2_max",
        "sleep",
        "sleep_time",
        "workout",
        "heartrate",
        "ring_battery_level",
        "ring_configuration",
        "personal_info",
        "session",
        "tag",
        "enhanced_tag",
        "rest_mode_period",
        "sync_log",
    ):
        assert f"INSERT INTO {table}" in source

    assert "REFRESH MATERIALIZED VIEW sleep_primary" in source
