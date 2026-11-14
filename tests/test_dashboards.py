import json
import os
import re
from datetime import date, datetime, time, timedelta, timezone
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
    # Helper ${__to} is time.max on the end day: 23:59:59.999999 local, same civil day as the
    # next midnight, so the shift is the clock only. Grafana parseDateMath keeps each token.
    assert dashboard_connection.exec_driver_sql(shift_sql.replace("$night", "2026-10-01")).scalar_one() == "23h-59m-59s"


def _local_date(value, display_timezone):
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(ZoneInfo(display_timezone)).date()


def test_nap_panel_counts_confirmed_naps_not_rejected_rest(dashboard_connection, loaded_dashboards):
    dashboard_connection.exec_driver_sql("CREATE TEMP TABLE sleep (day date, type text) ON COMMIT DROP")
    dashboard_connection.exec_driver_sql(
        "INSERT INTO sleep VALUES "
        "('2026-10-01', 'sleep'), ('2026-10-01', 'long_sleep'), ('2026-10-02', 'rest'), "
        "('2026-10-02', 'late_nap'), ('2026-10-02', 'deleted')"
    )
    sql = dashboard_sql(loaded_dashboards, "oura-sleep", 20, "2026-10-01", "2026-10-02", "America/Toronto")
    rows = dashboard_connection.exec_driver_sql(sql).all()

    assert sorted(_local_date(row[0], "America/Toronto") for row in rows) == [date(2026, 10, 1), date(2026, 10, 2)]
    assert sorted(int(row[1]) for row in rows) == [1, 1]


def test_daily_heart_rate_uses_the_dashboard_timezone(dashboard_connection, loaded_dashboards):
    dashboard_connection.exec_driver_sql("SET LOCAL TIME ZONE 'UTC'")
    dashboard_connection.exec_driver_sql(
        "CREATE TEMP TABLE heartrate (timestamp timestamptz, bpm integer) ON COMMIT DROP"
    )
    dashboard_connection.exec_driver_sql(
        "INSERT INTO heartrate VALUES ('2026-11-13 17:00:00+00', 80), ('2026-11-14 02:00:00+00', 40)"
    )
    sql = dashboard_sql(loaded_dashboards, "oura-heart-rate", 7, "2026-11-13", "2026-11-13", "America/Toronto")
    rows = dashboard_connection.exec_driver_sql(sql).all()

    assert len(rows) == 1
    assert _local_date(rows[0][0], "America/Toronto") == date(2026, 11, 13)
    assert rows[0][1] == 40
    assert rows[0][3] == 80


def test_workout_clock_uses_the_dashboard_timezone(dashboard_connection, loaded_dashboards):
    dashboard_connection.exec_driver_sql("SET LOCAL TIME ZONE 'UTC'")
    dashboard_connection.exec_driver_sql(
        "CREATE TEMP TABLE workout ("
        "day date, activity text, intensity text, calories numeric, "
        "start_datetime timestamptz, end_datetime timestamptz, source text"
        ") ON COMMIT DROP"
    )
    dashboard_connection.exec_driver_sql(
        "INSERT INTO workout VALUES ("
        "'2026-10-01', 'running', 'moderate', 100, "
        "'2026-10-01 22:00:00+00', '2026-10-01 22:30:00+00', 'manual')"
    )
    sql = dashboard_sql(loaded_dashboards, "oura-activity", 15, "2026-10-01", "2026-10-01", "America/Toronto")
    row = dashboard_connection.exec_driver_sql(sql).one()

    assert row[5] == "18:00"
    assert row[6] == "18:30"


def test_open_rest_mode_days_use_the_dashboard_timezone(dashboard_connection, loaded_dashboards):
    dashboard_connection.exec_driver_sql("SET LOCAL TIME ZONE 'Pacific/Kiritimati'")
    now = dashboard_connection.exec_driver_sql("SELECT CURRENT_TIMESTAMP").scalar_one()
    local_day = now.astimezone(ZoneInfo("Pacific/Pago_Pago")).date()
    session_day = now.astimezone(ZoneInfo("Pacific/Kiritimati")).date()
    assert session_day != local_day
    dashboard_connection.exec_driver_sql(
        "CREATE TEMP TABLE rest_mode_period ("
        "start_day date, end_day date, start_time timestamptz, end_time timestamptz, episodes jsonb"
        ") ON COMMIT DROP"
    )
    dashboard_connection.exec_driver_sql(
        "INSERT INTO rest_mode_period (start_day) VALUES (%s)",
        (local_day,),
    )
    day = local_day.isoformat()
    sql = dashboard_sql(loaded_dashboards, "oura-context", 7, day, day, "Pacific/Pago_Pago")
    row = dashboard_connection.exec_driver_sql(sql).one()

    assert int(row[2]) == 1


def test_tag_labels_are_plain_names(dashboard_connection, loaded_dashboards):
    dashboard_connection.exec_driver_sql(
        "CREATE TEMP TABLE tag (timestamp timestamptz, day date, tags jsonb, text text) ON COMMIT DROP"
    )
    dashboard_connection.exec_driver_sql(
        "CREATE TEMP TABLE enhanced_tag ("
        "start_time timestamptz, start_day date, end_day date, custom_name text, tag_type_code text, comment text"
        ") ON COMMIT DROP"
    )
    dashboard_connection.exec_driver_sql(
        "INSERT INTO tag VALUES ('2026-10-01 15:00:00+00', '2026-10-01', '[\"caffeine\", \"alcohol\"]', 'after lunch')"
    )
    sql = dashboard_sql(loaded_dashboards, "oura-context", 6, "2026-10-01", "2026-10-01", "America/Toronto")
    row = dashboard_connection.exec_driver_sql(sql).one()

    assert row[2] == "caffeine, alcohol"


def test_enhanced_tag_duration_overlaps_the_selected_days(dashboard_connection, loaded_dashboards):
    """A tag with an end day stays visible on every day it covers.

    end_day is the last day of a duration. NULL means the tag has no duration,
    so only its start day counts. An open rest-mode period is a different rule.
    """
    dashboard_connection.exec_driver_sql(
        "CREATE TEMP TABLE tag (timestamp timestamptz, day date, tags jsonb, text text) ON COMMIT DROP"
    )
    dashboard_connection.exec_driver_sql(
        "CREATE TEMP TABLE enhanced_tag ("
        "start_time timestamptz, start_day date, end_day date, "
        "custom_name text, tag_type_code text, comment text"
        ") ON COMMIT DROP"
    )
    dashboard_connection.exec_driver_sql(
        "INSERT INTO enhanced_tag "
        "(start_time, start_day, end_day, custom_name, tag_type_code, comment) VALUES "
        "('2026-09-28 12:00+00', '2026-09-28', '2026-10-02', 'illness', NULL, NULL), "
        "('2026-09-01 12:00+00', '2026-09-01', '2026-09-15', 'travel', NULL, NULL), "
        "('2026-10-01 12:00+00', '2026-10-01', NULL, 'caffeine', NULL, NULL), "
        "('2026-09-30 12:00+00', '2026-09-30', NULL, NULL, 'alcohol', NULL), "
        "('2026-10-02 12:00+00', '2026-10-02', '2026-10-05', 'sauna', NULL, NULL), "
        "('2026-10-03 12:00+00', '2026-10-03', '2026-10-04', 'late', NULL, NULL)"
    )
    listed = dashboard_sql(loaded_dashboards, "oura-context", 6, "2026-10-01", "2026-10-02", "America/Toronto")
    labels = {row[2] for row in dashboard_connection.exec_driver_sql(listed).all()}
    assert labels == {"illness", "caffeine", "sauna"}
    counted = dashboard_sql(loaded_dashboards, "oura-context", 2, "2026-10-01", "2026-10-02", "America/Toronto")
    assert int(dashboard_connection.exec_driver_sql(counted).scalar_one()) == 3


# Grafana 13.2.4 moment subtracts h/m/s as absolute milliseconds and d as a calendar day.
# A calendar day across a DST change does not land on the next local midnight. parseDateMath
# also rejects any token longer than 5 digits, so hours past 99999 are a second h token.
_ABSOLUTE_SHIFT = re.compile(
    r"(?:\d{1,5}h)(?:-\d{1,5}h)*(?:-\d{1,5}m)?(?:-\d{1,5}s)?"
    r"|\d{1,5}m(?:-\d{1,5}s)?"
    r"|\d{1,5}s"
)
_SHIFT_SECONDS = {"h": 3600, "m": 60, "s": 1}


def _grafana_shift(value: str) -> timedelta:
    text = str(value)
    assert _ABSOLUTE_SHIFT.fullmatch(text), text
    total = 0
    for amount, unit in re.findall(r"(\d{1,5})([hms])", text):
        total += int(amount) * _SHIFT_SECONDS[unit]
    return timedelta(seconds=total)


def _apply_absolute_shift(clock: datetime, shift: timedelta) -> datetime:
    """Subtract h/m/s the way Grafana moment does: absolute milliseconds, not civil days."""
    return datetime.fromtimestamp(clock.timestamp() - shift.total_seconds(), clock.tzinfo)


def _sleep_phase_window(loaded_dashboards, dashboard_to: datetime, night: date, display_timezone: str):
    dashboard = next(item for item in loaded_dashboards if item["uid"] == "oura-sleep")
    panel = next(item for item in dashboard["panels"] if item["id"] == 9)
    variable = next(item for item in dashboard["templating"]["list"] if item["name"] == "night_shift")
    assert panel["timeFrom"] == "2d"
    assert panel["timeShift"] == "$night_shift"
    sql = variable["query"].replace("${__to}", str(int(dashboard_to.timestamp() * 1000)))
    sql = sql.replace("$__timezone", display_timezone).replace("$night", night.isoformat())
    return sql


def test_sleep_phase_window_covers_bedtime_and_late_wake(dashboard_connection, loaded_dashboards):
    """The phase timeline must end at the next local midnight, including across DST.

    Grafana subtracts h/m/s as absolute milliseconds. A calendar day does not.
    """
    dashboard_connection.exec_driver_sql("SET LOCAL TIME ZONE 'Pacific/Kiritimati'")
    zone = ZoneInfo("America/Toronto")
    bedtime = datetime(2026, 10, 31, 18, 0, tzinfo=zone)
    wake = datetime(2026, 11, 1, 12, 0, tzinfo=zone)
    cases = (
        (
            datetime(2026, 11, 13, 7, 30, tzinfo=zone),
            date(2026, 11, 1),
            "271h-30m",
            datetime(2026, 11, 2, 0, 0, tzinfo=zone),
        ),
        (
            datetime(2026, 11, 13, 22, 15, tzinfo=zone),
            date(2026, 11, 1),
            "286h-15m",
            datetime(2026, 11, 2, 0, 0, tzinfo=zone),
        ),
        (
            datetime(2026, 3, 9, 7, 30, tzinfo=zone),
            date(2026, 3, 7),
            "30h-30m",
            datetime(2026, 3, 8, 0, 0, tzinfo=zone),
        ),
        (
            datetime(2026, 3, 8, 10, 0, tzinfo=zone),
            date(2026, 3, 7),
            "9h",
            datetime(2026, 3, 8, 0, 0, tzinfo=zone),
        ),
        (
            datetime(2026, 11, 2, 7, 30, tzinfo=zone),
            date(2026, 10, 31),
            "32h-30m",
            datetime(2026, 11, 1, 0, 0, tzinfo=zone),
        ),
        (
            datetime(2026, 11, 13, 7, 30, tzinfo=zone),
            date(2015, 6, 16),
            "99999h-17h-30m",
            datetime(2015, 6, 17, 0, 0, tzinfo=zone),
        ),
    )
    for clock, night, expected, next_midnight in cases:
        sql = _sleep_phase_window(loaded_dashboards, clock, night, "America/Toronto")
        raw_shift = dashboard_connection.exec_driver_sql(sql).scalar_one()
        assert raw_shift == expected
        window_end = _apply_absolute_shift(clock, _grafana_shift(raw_shift))
        assert window_end == next_midnight
        if night == date(2026, 11, 1):
            window_start = datetime.fromtimestamp(window_end.timestamp() - 2 * 86400, zone)
            assert window_start <= bedtime
            assert wake <= window_end

    this_morning = datetime(2026, 11, 13, 7, 30, tzinfo=zone)
    sql = _sleep_phase_window(loaded_dashboards, this_morning, this_morning.date(), "America/Toronto")
    raw_shift = dashboard_connection.exec_driver_sql(sql).scalar_one()
    assert raw_shift == "0s"
    shift = _grafana_shift(raw_shift)
    assert shift == timedelta(0)
    window_end = _apply_absolute_shift(this_morning, shift)
    window_start = datetime.fromtimestamp(window_end.timestamp() - 2 * 86400, zone)
    assert window_start <= datetime(2026, 11, 12, 22, 0, tzinfo=zone)
    assert datetime(2026, 11, 13, 7, 0, tzinfo=zone) <= window_end
