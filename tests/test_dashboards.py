import json
import os
import re
from datetime import datetime, time, timezone
from zoneinfo import ZoneInfo

import pytest

EXPECTED_DASHBOARDS = {
    "01-overview.json": "oura-overview",
    "02-sleep.json": "oura-sleep",
    "03-readiness.json": "oura-readiness",
    "04-activity.json": "oura-activity",
    "05-body.json": "oura-body",
    "06-heart-rate.json": "oura-heart-rate",
    "07-context.json": "oura-context",
    "08-ring.json": "oura-ring",
}

DATASOURCE_UID = "oura-pg"


class TestDashboardFiles:
    def test_all_dashboards_exist(self, dashboard_files):
        names = {f.name for f in dashboard_files}
        for expected in EXPECTED_DASHBOARDS:
            assert expected in names, f"Missing dashboard: {expected}"

    def test_valid_json(self, dashboard_files):
        for f in dashboard_files:
            data = json.loads(f.read_text())
            assert isinstance(data, dict), f"{f.name} root is not an object"


class TestDashboardStructure:
    def test_required_fields(self, loaded_dashboards, dashboard_files):
        for dash, f in zip(loaded_dashboards, dashboard_files):
            assert "uid" in dash, f"{f.name} missing uid"
            assert "title" in dash, f"{f.name} missing title"
            assert "panels" in dash, f"{f.name} missing panels"
            assert isinstance(dash["panels"], list), f"{f.name} panels is not a list"
            assert len(dash["panels"]) > 0, f"{f.name} has no panels"

    def test_unique_uids(self, loaded_dashboards):
        uids = [d["uid"] for d in loaded_dashboards]
        assert len(uids) == len(set(uids)), f"Duplicate UIDs found: {uids}"

    def test_expected_uids(self, loaded_dashboards):
        uids = {d["uid"] for d in loaded_dashboards}
        for expected_uid in EXPECTED_DASHBOARDS.values():
            assert expected_uid in uids, f"Missing UID: {expected_uid}"


class TestDatasourceRefs:
    def test_panel_datasources(self, loaded_dashboards, dashboard_files):
        for dash, f in zip(loaded_dashboards, dashboard_files):
            for panel in dash["panels"]:
                ds = panel.get("datasource")
                if ds and isinstance(ds, dict) and ds.get("uid"):
                    assert ds["uid"] == DATASOURCE_UID, (
                        f"{f.name} panel '{panel.get('title')}' has wrong datasource UID: {ds['uid']}"
                    )

    def test_target_datasources(self, loaded_dashboards, dashboard_files):
        for dash, f in zip(loaded_dashboards, dashboard_files):
            for panel in dash["panels"]:
                for target in panel.get("targets", []):
                    ds = target.get("datasource")
                    if ds and isinstance(ds, dict) and ds.get("uid"):
                        assert ds["uid"] == DATASOURCE_UID, (
                            f"{f.name} panel '{panel.get('title')}' target has wrong datasource: {ds['uid']}"
                        )


class TestPanelIntegrity:
    def test_all_panels_have_titles(self, loaded_dashboards, dashboard_files):
        for dash, f in zip(loaded_dashboards, dashboard_files):
            for panel in dash["panels"]:
                if panel.get("type") != "row":
                    assert panel.get("title"), f"{f.name} panel id={panel.get('id')} has no title"

    def test_all_panels_have_ids(self, loaded_dashboards, dashboard_files):
        for dash, f in zip(loaded_dashboards, dashboard_files):
            ids = []
            for panel in dash["panels"]:
                assert "id" in panel, f"{f.name} has panel without id"
                ids.append(panel["id"])
            assert len(ids) == len(set(ids)), f"{f.name} has duplicate panel IDs"

    def test_panel_count(self, loaded_dashboards):
        """Each dashboard should have a minimum number of panels."""
        minimums = {
            "oura-overview": 8,
            "oura-sleep": 12,
            "oura-readiness": 6,
            "oura-activity": 8,
            "oura-body": 8,
            "oura-heart-rate": 7,
            "oura-context": 7,
            "oura-ring": 8,
        }
        for dash in loaded_dashboards:
            uid = dash["uid"]
            count = len(dash["panels"])
            if uid in minimums:
                assert count >= minimums[uid], f"{uid} has {count} panels, expected at least {minimums[uid]}"


@pytest.fixture
def dashboard_connection():
    """Run dashboard SQL against temporary tables, never the stored user data."""
    database_url = os.getenv("TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("Set TEST_DATABASE_URL to run dashboard SQL regressions")
    sqlalchemy = pytest.importorskip("sqlalchemy")
    engine = sqlalchemy.create_engine(database_url)
    try:
        with engine.connect() as connection, connection.begin():
            yield connection
    finally:
        engine.dispose()


def dashboard_sql(loaded_dashboards, uid, panel_id, start="2026-10-01", end="2026-10-02", display_timezone="UTC"):
    dashboard = next(d for d in loaded_dashboards if d["uid"] == uid)
    panel = next(p for p in dashboard["panels"] if p["id"] == panel_id)
    return interpolate_dashboard_sql(panel["targets"][0]["rawSql"], start, end, display_timezone)


def interpolate_dashboard_sql(sql, start, end, display_timezone):
    zone = ZoneInfo(display_timezone)
    start_instant = datetime.combine(datetime.fromisoformat(start).date(), time.min, zone).astimezone(timezone.utc)
    end_instant = datetime.combine(datetime.fromisoformat(end).date(), time.max, zone).astimezone(timezone.utc)
    sql = sql.replace("$__timeFrom()", f"'{start_instant.isoformat()}'")
    sql = sql.replace("$__timeTo()", f"'{end_instant.isoformat()}'")
    sql = sql.replace("${__from}", str(int(start_instant.timestamp() * 1000)))
    sql = sql.replace("${__to}", str(int(end_instant.timestamp() * 1000)))
    sql = sql.replace("$__timezone", display_timezone)
    return re.sub(
        r"\$__timeFilter\(([^)]+)\)",
        lambda match: f"{match[1]} BETWEEN '{start_instant.isoformat()}' AND '{end_instant.isoformat()}'",
        sql,
    )


SNAPSHOT_TABLES = {
    "daily_sleep": "contributors_deep_sleep contributors_efficiency contributors_latency contributors_rem_sleep "
    "contributors_restfulness contributors_timing contributors_total_sleep",
    "daily_readiness": "contributors_activity_balance contributors_body_temperature contributors_hrv_balance "
    "contributors_previous_day_activity contributors_previous_night contributors_recovery_index "
    "contributors_resting_heart_rate contributors_sleep_balance contributors_sleep_regularity",
    "daily_activity": "equivalent_walking_distance high_activity_time medium_activity_time low_activity_time "
    "sedentary_time resting_time contributors_meet_daily_targets contributors_move_every_hour "
    "contributors_recovery_time contributors_stay_active contributors_training_frequency contributors_training_volume",
    "daily_stress": "stress_high recovery_high",
    "daily_resilience": "contributors_sleep_recovery contributors_daytime_recovery contributors_stress",
    "daily_cardiovascular_age": "vascular_age",
}


@pytest.mark.parametrize(
    ("uid", "panel_id", "table"),
    [
        ("oura-overview", 9, "daily_sleep"),
        ("oura-readiness", 4, "daily_readiness"),
        ("oura-activity", 4, "daily_activity"),
        ("oura-activity", 6, "daily_activity"),
        ("oura-activity", 8, "daily_activity"),
        ("oura-activity", 12, "daily_activity"),
        ("oura-body", 6, "daily_stress"),
        ("oura-body", 8, "daily_resilience"),
        ("oura-body", 9, "daily_resilience"),
        ("oura-body", 11, "daily_cardiovascular_age"),
    ],
)
@pytest.mark.parametrize("display_timezone", ["UTC", "America/Toronto", "Asia/Tokyo"])
def test_historical_snapshot_does_not_use_future_records(
    dashboard_connection, loaded_dashboards, uid, panel_id, table, display_timezone
):
    columns = SNAPSHOT_TABLES[table].split()
    definitions = ", ".join(f"{column} integer" for column in columns)
    if table == "daily_resilience":
        definitions += ", level text"
    dashboard_connection.exec_driver_sql(f"CREATE TEMP TABLE {table} (day date, {definitions}) ON COMMIT DROP")
    for day, value, level in [("2026-10-02", 1000, "adequate"), ("2026-10-03", 9000, "exceptional")]:
        values = ", ".join([str(value)] * len(columns))
        if table == "daily_resilience":
            values += f", '{level}'"
        dashboard_connection.exec_driver_sql(f"INSERT INTO {table} VALUES ('{day}', {values})")

    sql = dashboard_sql(loaded_dashboards, uid, panel_id, display_timezone=display_timezone)
    with_future_records = dashboard_connection.exec_driver_sql(sql).all()
    dashboard_connection.exec_driver_sql(f"DELETE FROM {table} WHERE day > '2026-10-02'")
    historical_records_only = dashboard_connection.exec_driver_sql(sql).all()

    assert historical_records_only
    assert with_future_records == historical_records_only


@pytest.mark.parametrize(
    ("uid", "panel_id", "table", "column", "scale"),
    [
        ("oura-sleep", 12, "sleep", "average_hrv", 1),
        ("oura-sleep", 16, "sleep", "latency", 60),
        ("oura-readiness", 6, "daily_readiness", "score", 1),
    ],
)
def test_seven_day_average_uses_calendar_days_and_preceding_history(
    dashboard_connection, loaded_dashboards, uid, panel_id, table, column, scale
):
    extra_columns = ", type text DEFAULT 'long_sleep', total_sleep integer DEFAULT 28800" if table == "sleep" else ""
    dashboard_connection.exec_driver_sql(
        f"CREATE TEMP TABLE {table} (day date, {column} integer{extra_columns}) ON COMMIT DROP"
    )
    for day, value in [("2026-09-01", 10), ("2026-09-26", 20), ("2026-09-30", 80), ("2026-10-01", 100)]:
        dashboard_connection.exec_driver_sql(f"INSERT INTO {table} (day, {column}) VALUES ('{day}', {value * scale})")

    # Changing the displayed range must not change the average for the same day.
    for start in ["2026-10-01", "2026-09-01"]:
        rows = dashboard_connection.exec_driver_sql(dashboard_sql(loaded_dashboards, uid, panel_id, start=start)).all()
        assert float(rows[-1][2]) == pytest.approx((20 + 80 + 100) / 3)


@pytest.mark.parametrize("display_timezone", ["UTC", "America/Toronto", "Asia/Tokyo"])
@pytest.mark.parametrize("session_timezone", ["UTC", "Pacific/Auckland"])
def test_daily_series_uses_selected_civil_days_and_local_midnight(
    dashboard_connection, loaded_dashboards, display_timezone, session_timezone
):
    dashboard_connection.exec_driver_sql(f"SET LOCAL TIME ZONE '{session_timezone}'")
    dashboard_connection.exec_driver_sql("CREATE TEMP TABLE daily_readiness (day date, score integer) ON COMMIT DROP")
    dashboard_connection.exec_driver_sql(
        "INSERT INTO daily_readiness VALUES "
        "('2026-09-30', 30), ('2026-10-01', 60), ('2026-10-02', 80), ('2026-10-03', 90)"
    )
    sql = dashboard_sql(loaded_dashboards, "oura-readiness", 3, display_timezone=display_timezone)
    rows = dashboard_connection.exec_driver_sql(sql).all()

    assert [row[1] for row in rows] == [60, 80]
    for row, day in zip(rows, ["2026-10-01", "2026-10-02"]):
        expected = datetime.combine(datetime.fromisoformat(day).date(), time.min, ZoneInfo(display_timezone))
        assert row[0] == expected


@pytest.mark.parametrize("display_timezone", ["UTC", "America/Toronto", "Asia/Tokyo"])
def test_context_counts_only_the_selected_civil_days(dashboard_connection, loaded_dashboards, display_timezone):
    dashboard_connection.exec_driver_sql("CREATE TEMP TABLE session (day date) ON COMMIT DROP")
    dashboard_connection.exec_driver_sql(
        "INSERT INTO session VALUES ('2026-09-30'), ('2026-10-01'), ('2026-10-02'), ('2026-10-03')"
    )
    sql = dashboard_sql(loaded_dashboards, "oura-context", 1, display_timezone=display_timezone)
    assert dashboard_connection.exec_driver_sql(sql).scalar_one() == 2


@pytest.mark.parametrize("display_timezone", ["UTC", "America/Toronto", "Asia/Tokyo"])
def test_night_selector_uses_the_dashboard_timezone(dashboard_connection, loaded_dashboards, display_timezone):
    dashboard_connection.exec_driver_sql("CREATE TEMP TABLE sleep (day date, type text) ON COMMIT DROP")
    dashboard_connection.exec_driver_sql(
        "INSERT INTO sleep VALUES ('2026-09-30', 'long_sleep'), ('2026-10-01', 'long_sleep'), "
        "('2026-10-02', 'long_sleep'), ('2026-10-03', 'long_sleep')"
    )
    dashboard = next(d for d in loaded_dashboards if d["uid"] == "oura-sleep")
    variables = {v["name"]: v["query"] for v in dashboard["templating"]["list"]}
    sql = interpolate_dashboard_sql(variables["night"], "2026-10-01", "2026-10-02", display_timezone)
    assert dashboard_connection.exec_driver_sql(sql).scalars().all() == ["2026-10-02", "2026-10-01"]
    shift_sql = interpolate_dashboard_sql(variables["night_shift"], "2026-10-01", "2026-10-02", display_timezone)
    assert dashboard_connection.exec_driver_sql(shift_sql.replace("$night", "2026-10-01")).scalar_one() == "1d"
