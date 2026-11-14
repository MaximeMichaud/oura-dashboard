import os
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import Mock
from zoneinfo import ZoneInfo

import pandas as pd
import pytest
import requests
from components.sidebar import _today_in_timezone
from data import providers
from data.api_provider import ApiProvider
from data.oauth import OAuthToken
from data.postgres_provider import PostgresProvider
from sqlalchemy import create_engine, text
from streamlit.testing.v1 import AppTest


class _FakeSidebar:
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def caption(self, _message):
        pass

    def expander(self, _label, *, expanded):
        assert expanded
        return self


class _FakeStreamlit:
    def __init__(self):
        self.session_state = {"provider_mode": "demo"}
        self.sidebar = _FakeSidebar()
        self.text_inputs = {}
        self.rerun_called = False

    def text_input(self, label, **kwargs):
        self.text_inputs[label] = kwargs
        return {
            "Legacy Oura Token": "",
            "Client ID": "browser-client-id",
            "Client Secret": "",
            "Callback URL or code": "authorization-code",
        }[label]

    def button(self, label):
        return label == "Connect with OAuth"

    def expander(self, label, *, expanded):
        return self.sidebar.expander(label, expanded=expanded)

    def rerun(self):
        self.rerun_called = True

    def __getattr__(self, _name):
        return lambda *_args, **_kwargs: None


def _api_response(*, data, next_token=None):
    response = Mock(status_code=200, headers={})
    response.json.return_value = {"data": data, "next_token": next_token}
    return response


def test_oauth_env_client_secret_is_not_used_as_widget_value(monkeypatch):
    fake_streamlit = _FakeStreamlit()
    exchange = Mock(return_value=OAuthToken("access-token", None, None))
    monkeypatch.setenv("OURA_CLIENT_SECRET", "server-client-secret")
    monkeypatch.setattr(providers, "st", fake_streamlit)
    monkeypatch.setattr(providers, "exchange_authorization_code", exchange)

    providers.show_provider_sidebar()

    assert fake_streamlit.text_inputs["Client Secret"] == {"type": "password"}
    exchange.assert_called_once_with(
        client_id="browser-client-id",
        client_secret="server-client-secret",
        code="authorization-code",
        redirect_uri=providers.DEFAULT_REDIRECT_URI,
    )
    assert fake_streamlit.rerun_called


def test_api_workouts_preserve_dashboard_columns():
    provider = ApiProvider("test-token")
    provider._fetch_cached = Mock(
        return_value=[
            {
                "day": "2026-07-08",
                "activity": "running",
                "calories": 420,
                "distance": 5100,
                "start_datetime": "2026-07-08T12:00:00Z",
                "end_datetime": "2026-07-08T12:45:00Z",
                "intensity": "moderate",
                "source": "autodetected",
                "type": "legacy-value",
            }
        ]
    )

    workouts = provider.workouts(date(2026, 7, 1), date(2026, 7, 9))

    assert workouts.columns.tolist() == [
        "day",
        "activity",
        "calories",
        "distance",
        "start_datetime",
        "end_datetime",
        "intensity",
        "source",
    ]
    assert workouts.iloc[0].to_dict() == {
        "day": "2026-07-08",
        "activity": "running",
        "calories": 420,
        "distance": 5100,
        "start_datetime": "2026-07-08T12:00:00Z",
        "end_datetime": "2026-07-08T12:45:00Z",
        "intensity": "moderate",
        "source": "autodetected",
    }


def test_api_fetch_rejects_cyclic_next_token(monkeypatch):
    provider = ApiProvider("test-token")
    responses = [
        _api_response(data=[{"id": "first"}], next_token="repeated-token"),
        _api_response(data=[{"id": "second"}], next_token="repeated-token"),
    ]
    get = Mock(side_effect=responses)
    monkeypatch.setattr("data.api_provider.requests.get", get)

    with pytest.raises(RuntimeError, match="cyclic next_token"):
        provider._fetch("daily_sleep", date(2026, 7, 1), date(2026, 7, 2))

    assert get.call_count == 2
    assert get.call_args_list[1].kwargs["params"] == {"next_token": "repeated-token"}


def test_api_datetime_range_uses_selected_timezone(monkeypatch):
    provider = ApiProvider("test-token")
    monkeypatch.setitem(providers.st.session_state, "user_timezone", "America/Toronto")
    fixed_now = datetime(2026, 7, 9, 2, 30, tzinfo=timezone.utc)

    class _FixedDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return fixed_now if tz else fixed_now.replace(tzinfo=None)

    monkeypatch.setattr("data.api_provider.datetime", _FixedDatetime)

    params = provider._datetime_range_params(date(2026, 7, 7), date(2026, 7, 8))

    assert params == {
        "start_datetime": "2026-07-07T04:00:00+00:00",
        "end_datetime": "2026-07-09T02:30:00+00:00",
    }


@pytest.mark.parametrize("start", [date(2026, 10, 7), date(2026, 8, 8)])
def test_api_datetime_chunks_respect_30_days_across_fall_back(monkeypatch, start):
    monkeypatch.setattr(providers.st, "session_state", {"user_timezone": "America/Toronto"})
    provider = ApiProvider("test-token")
    provider._request = Mock(return_value=_api_response(data=[]))
    end = date(2026, 11, 5)

    assert provider._fetch("heartrate", start, end, query_mode="datetime") == []

    ranges = [
        (
            datetime.fromisoformat(call.args[1]["start_datetime"]),
            datetime.fromisoformat(call.args[1]["end_datetime"]),
        )
        for call in provider._request.call_args_list
    ]
    expected = provider._datetime_range_params(start, end)
    assert ranges[0][0] == datetime.fromisoformat(expected["start_datetime"])
    assert ranges[-1][1] == datetime.fromisoformat(expected["end_datetime"])
    for range_start, range_end in ranges:
        assert range_end - range_start <= timedelta(days=30)
    for (_, previous_end), (next_start, _) in zip(ranges, ranges[1:]):
        assert next_start == previous_end + timedelta(microseconds=1)


def test_api_request_retries_transient_network_errors(monkeypatch):
    provider = ApiProvider("test-token")
    response = _api_response(data=[])
    get = Mock(side_effect=[requests.Timeout("slow"), response])
    delays = []
    monkeypatch.setattr("data.api_provider.requests.get", get)
    monkeypatch.setattr("data.api_provider.time.sleep", delays.append)

    assert provider._request("https://example.test", {}) is response
    assert get.call_count == 2
    assert delays == [1]


def test_today_uses_selected_timezone():
    instant = datetime(2026, 7, 9, 2, 30, tzinfo=timezone.utc)

    assert _today_in_timezone("America/Toronto", instant) == date(2026, 7, 8)
    assert _today_in_timezone("Asia/Tokyo", instant) == date(2026, 7, 9)


def test_setup_day_follows_the_selected_timezone(monkeypatch):
    values = pd.Series(
        [
            pd.Timestamp("2026-11-13 02:00:00+00:00"),
            "2026-11-13T02:00:00.000Z",
            pd.Timestamp("2026-11-13 22:00:00+00:00"),
            None,
        ]
    )

    provider = Mock()
    provider.ring_summary.return_value = {}
    provider.battery_series.return_value = pd.DataFrame()
    provider.ring_configurations.side_effect = lambda: pd.DataFrame({"set_up_at": values})
    provider.personal_profile.return_value = {}
    monkeypatch.setattr(providers, "get_provider", lambda: provider)
    monkeypatch.setattr("components.sidebar.render_sidebar", lambda: None)
    page = AppTest.from_file(str(Path(__file__).parents[1] / "streamlit/pages/8_Ring.py"))
    page.session_state["user_timezone"] = "America/Toronto"
    page.run()

    assert not page.exception
    days = page.dataframe[0].value["Set Up"].tolist()
    assert days[:3] == ["2026-11-12", "2026-11-12", "2026-11-13"]
    assert pd.isna(days[3])
    page.session_state["user_timezone"] = "Asia/Tokyo"
    page.run()
    assert not page.exception
    days = page.dataframe[0].value["Set Up"].tolist()
    assert days[:3] == ["2026-11-13", "2026-11-13", "2026-11-14"]
    assert pd.isna(days[3])


@pytest.fixture
def frontend_pg_connection(monkeypatch):
    """Execute provider queries against transaction-local synthetic tables."""
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL is required for PostgreSQL provider tests")
    engine = create_engine(url)
    try:
        with engine.connect() as connection, connection.begin():
            monkeypatch.setattr(
                "data.postgres_provider.query_df",
                lambda sql, params=None: pd.read_sql(text(sql), connection, params=params),
            )
            yield connection
    finally:
        engine.dispose()


def test_postgres_scores_preserve_days_without_activity(frontend_pg_connection):
    conn = frontend_pg_connection
    for table, metric in [("daily_sleep", "score"), ("daily_readiness", "score"), ("daily_activity", "steps")]:
        conn.execute(text(f"CREATE TEMP TABLE {table} (day date PRIMARY KEY, {metric} int) ON COMMIT DROP"))
    conn.execute(text("INSERT INTO daily_sleep VALUES ('2026-07-01', 81), ('2026-07-03', 83), ('2026-07-04', 99)"))
    conn.execute(text("INSERT INTO daily_readiness VALUES ('2026-07-02', 82), ('2026-07-03', 84)"))
    conn.execute(text("INSERT INTO daily_activity VALUES ('2026-07-03', 5000)"))

    frame = PostgresProvider.scores_trend.__wrapped__(PostgresProvider(), date(2026, 7, 1), date(2026, 7, 3))

    assert frame["day"].tolist() == [date(2026, 7, day) for day in range(1, 4)]
    assert frame.iloc[0]["sleep_score"] == 81
    assert pd.isna(frame.iloc[0]["steps"])
    assert frame.iloc[1]["readiness_score"] == 82
    assert frame.iloc[2]["sleep_score"] == 83
    assert frame.iloc[2]["readiness_score"] == 84
    assert frame.iloc[2]["steps"] == 5000


def test_api_latest_scores_keep_the_newest_record_outside_the_last_week():
    """Latest cards must follow the newest day on or before the selected end.

    Postgres has no seven-day cap. A gap longer than a week, or a response that is
    not ordered by day, must not blank the card or show an older score.
    """
    provider = ApiProvider("test-token")

    def fetch(endpoint, start=None, end=None, **_kwargs):
        if endpoint != "daily_sleep":
            return []
        if start is None or start > date(2026, 5, 1):
            return []
        return [
            {"day": "2026-05-20", "score": 61},
            {"day": "2026-05-01", "score": 99},
        ]

    provider._fetch_cached = fetch

    assert provider.latest_scores(date(2026, 7, 1))["sleep_score"] == 61


def test_api_latest_score_uses_the_newest_day_when_the_payload_is_unsorted():
    provider = ApiProvider("test-token")
    provider._fetch_cached = lambda endpoint, start=None, end=None, **_kwargs: (
        [
            {"day": "2026-06-30", "score": 80},
            {"day": "2026-06-28", "score": 10},
        ]
        if endpoint == "daily_sleep"
        else []
    )

    assert provider.latest_scores(date(2026, 7, 1))["sleep_score"] == 80


def test_api_vo2_personal_best_includes_history_older_than_one_year():
    provider = ApiProvider("test-token")

    def fetch(endpoint, start=None, end=None, **_kwargs):
        if endpoint != "vO2_max":
            return []
        recent = {"day": "2026-06-01", "vo2_max": 42}
        if start is not None and start > date(2024, 1, 1):
            return [recent]
        return [{"day": "2024-01-01", "vo2_max": 55}, recent]

    provider._fetch_cached = fetch

    result = provider.latest_scores(date(2026, 7, 1))

    assert result["vo2_max"] == 42
    assert result["vo2_max_pb"] == 55


@pytest.mark.parametrize(
    ("endpoint", "method", "record", "field", "expected"),
    [
        ("daily_sleep", "sleep_contributors_latest", {"contributors": {"deep_sleep": 75}}, "Deep Sleep", 75),
        ("sleep_time", "optimal_bedtime", {"optimal_bedtime": {"start_offset": 3600}}, "optimal_bedtime_start", 3600),
        ("daily_readiness", "readiness_latest", {"score": 80}, "score", 80),
        ("daily_activity", "activity_latest", {"score": 70}, "score", 70),
        ("daily_stress", "stress_latest", {"day_summary": "restored"}, "day_summary", "restored"),
        ("daily_resilience", "resilience_latest", {"level": "solid"}, "level", "solid"),
        ("daily_spo2", "spo2_latest", {"spo2_percentage": {"average": 97}}, "spo2", 97),
    ],
)
def test_api_detail_cards_select_latest_historical_day(endpoint, method, record, field, expected):
    provider = ApiProvider("test-token")
    records = [
        {"day": "2026-05-20", **record},
        {"day": "2026-05-01"},
        {"day": "2026-08-01"},
    ]

    def fetch(actual_endpoint, start, end):
        assert actual_endpoint == endpoint
        return [row for row in records if start.isoformat() <= row["day"] <= end.isoformat()]

    provider._fetch_cached = fetch
    result = getattr(provider, method)(date(2026, 7, 1))
    if isinstance(result, pd.DataFrame):
        result = result.iloc[0]
    assert result[field] == expected


def test_api_overview_skips_missing_spo2_and_stress_summaries():
    provider = ApiProvider("test-token")
    payloads = {
        "daily_spo2": [
            {"day": "2026-06-27", "spo2_percentage": {"average": 97}},
            {"day": "2026-06-28", "spo2_percentage": {"average": 0}},
            {"day": "2026-06-29", "spo2_percentage": {"average": -1}},
            {"day": "2026-06-30", "spo2_percentage": None},
        ],
        "daily_stress": [
            {"day": "2026-06-28", "day_summary": "restored"},
            {"day": "2026-06-29", "day_summary": ""},
            {"day": "2026-06-30", "day_summary": None},
        ],
    }
    provider._fetch_cached = lambda endpoint, *_args: payloads.get(endpoint, [])
    scores = provider.latest_scores(date(2026, 7, 1))
    assert scores["spo2"] == 97
    assert scores["stress_summary"] == "restored"
    assert provider.spo2_latest(date(2026, 7, 1))["spo2"] is None
    assert provider.stress_latest(date(2026, 7, 1))["day_summary"] is None


def test_api_heart_rate_daily_uses_the_selected_timezone(monkeypatch):
    monkeypatch.setattr(providers.st, "session_state", {"user_timezone": "America/Toronto"})
    provider = ApiProvider("test-token")
    provider._fetch_cached = lambda *_args, **_kwargs: [
        {"timestamp": "2026-11-13T17:00:00+00:00", "bpm": 80, "source": "awake"},
        {"timestamp": "2026-11-14T02:00:00+00:00", "bpm": 40, "source": "awake"},
    ]

    frame = provider.heart_rate_daily(date(2026, 11, 13), date(2026, 11, 13))

    assert frame["day"].tolist() == [date(2026, 11, 13)]
    assert int(frame.iloc[0]["minimum"]) == 40
    assert int(frame.iloc[0]["maximum"]) == 80


def test_postgres_heart_rate_day_follows_the_user_timezone(frontend_pg_connection, monkeypatch):
    monkeypatch.setattr("data.postgres_provider.st.session_state", {"user_timezone": "America/Toronto"})
    conn = frontend_pg_connection
    conn.execute(text("SET LOCAL TIME ZONE 'UTC'"))
    conn.execute(text("CREATE TEMP TABLE heartrate (timestamp timestamptz PRIMARY KEY, bpm int) ON COMMIT DROP"))
    conn.execute(
        text("""
            INSERT INTO heartrate VALUES
                ('2026-11-13 17:00:00+00', 80),
                ('2026-11-14 02:00:00+00', 40)
        """)
    )

    provider = PostgresProvider()
    same_day = provider.heart_rate_daily(date(2026, 11, 13), date(2026, 11, 13))
    next_day = provider.heart_rate_daily(date(2026, 11, 14), date(2026, 11, 14))

    assert same_day["day"].tolist() == [date(2026, 11, 13)]
    assert int(same_day.iloc[0]["minimum"]) == 40
    assert int(same_day.iloc[0]["maximum"]) == 80
    assert next_day.empty


def test_postgres_timestamp_ranges_follow_the_user_timezone(frontend_pg_connection, monkeypatch):
    """Summary, series, sources, and battery use the same local civil-day bounds."""
    monkeypatch.setattr("data.postgres_provider.st.session_state", {"user_timezone": "America/Toronto"})
    conn = frontend_pg_connection
    conn.execute(text("SET LOCAL TIME ZONE 'UTC'"))
    conn.execute(
        text("""
            CREATE TEMP TABLE heartrate (
                timestamp timestamptz PRIMARY KEY, bpm int, source text
            ) ON COMMIT DROP
        """)
    )
    conn.execute(
        text("""
            CREATE TEMP TABLE ring_battery_level (
                timestamp timestamptz PRIMARY KEY, level int, charging bool, in_charger bool
            ) ON COMMIT DROP
        """)
    )
    conn.execute(
        text(
            "CREATE TEMP TABLE ring_configuration ("
            "hardware_type text, firmware_version text, set_up_at timestamptz"
            ") ON COMMIT DROP"
        )
    )
    conn.execute(
        text("""
            INSERT INTO heartrate VALUES
                ('2026-11-13 17:00:00+00', 80, 'awake'),
                ('2026-11-14 02:00:00+00', 40, 'awake')
        """)
    )
    conn.execute(
        text("""
            INSERT INTO ring_battery_level VALUES
                ('2026-11-13 17:00:00+00', 90, false, false),
                ('2026-11-14 02:00:00+00', 70, true, false)
        """)
    )

    provider = PostgresProvider()
    summary = provider.heart_rate_summary(date(2026, 11, 13), date(2026, 11, 13))
    sources = provider.heart_rate_sources(date(2026, 11, 13), date(2026, 11, 13))
    series = provider.heart_rate_series(date(2026, 11, 13), date(2026, 11, 13))
    battery = provider.battery_series(date(2026, 11, 13), date(2026, 11, 13))
    ring = provider.ring_summary(date(2026, 11, 13), date(2026, 11, 13))
    next_summary = provider.heart_rate_summary(date(2026, 11, 14), date(2026, 11, 14))

    assert int(summary["minimum"]) == 40
    assert int(summary["maximum"]) == 80
    assert int(summary["latest"]) == 40
    assert int(sources.iloc[0]["count"]) == 2
    assert len(series) == 2
    assert battery["level"].tolist() == [90, 70]
    assert int(ring["latest_level"]) == 70
    assert int(ring["minimum_level"]) == 70
    assert pd.isna(next_summary["minimum"])


@pytest.mark.parametrize("day", [date(2026, 3, 8), date(2026, 11, 1)])
def test_postgres_timestamp_bounds_cover_dst_days_and_timezone_changes(frontend_pg_connection, monkeypatch, day):
    session = {"user_timezone": "America/Toronto"}
    monkeypatch.setattr("data.postgres_provider.st.session_state", session)
    conn = frontend_pg_connection
    conn.execute(text("SET LOCAL TIME ZONE 'UTC'"))
    conn.execute(text("CREATE TEMP TABLE heartrate (timestamp timestamptz, bpm int) ON COMMIT DROP"))
    zone = ZoneInfo("America/Toronto")
    start = datetime.combine(day, datetime.min.time(), zone).astimezone(timezone.utc)
    end = datetime.combine(day + timedelta(days=1), datetime.min.time(), zone).astimezone(timezone.utc)
    conn.execute(
        text("INSERT INTO heartrate VALUES (:timestamp, :bpm)"),
        [
            {"timestamp": start - timedelta(microseconds=1), "bpm": 100},
            {"timestamp": start, "bpm": 60},
            {"timestamp": end - timedelta(microseconds=1), "bpm": 40},
            {"timestamp": end, "bpm": 120},
        ],
    )
    provider = PostgresProvider()
    local = provider.heart_rate_daily(day, day)
    assert local["day"].tolist() == [day]
    assert local.iloc[0][["minimum", "average", "maximum"]].tolist() == [40, 50, 60]
    session["user_timezone"] = "UTC"
    utc = provider.heart_rate_daily(day, day)
    assert utc.iloc[0][["minimum", "average", "maximum"]].tolist() == [60, 80, 100]
    session["user_timezone"] = "America/Toronto"
    pd.testing.assert_frame_equal(provider.heart_rate_daily(day, day), local)


def test_postgres_tag_labels_list_tag_names(frontend_pg_connection):
    conn = frontend_pg_connection
    conn.execute(
        text("""
            CREATE TEMP TABLE tag (
                timestamp timestamptz, day date, text text, tags jsonb
            ) ON COMMIT DROP
        """)
    )
    conn.execute(
        text("""
            CREATE TEMP TABLE enhanced_tag (
                start_time timestamptz, start_day date, end_day date, custom_name text,
                tag_type_code text, comment text
            ) ON COMMIT DROP
        """)
    )
    conn.execute(
        text("""
            INSERT INTO tag VALUES
                ('2026-10-01 12:00+00', '2026-10-01', 'after lunch', '["caffeine", "alcohol"]')
        """)
    )

    frame = PostgresProvider().tags(date(2026, 10, 1), date(2026, 10, 1))

    assert frame.iloc[0]["label"] == "caffeine, alcohol"


def test_postgres_enhanced_tag_duration_overlaps_the_selected_days(frontend_pg_connection):
    conn = frontend_pg_connection
    conn.execute(text("CREATE TEMP TABLE tag (timestamp timestamptz, day date, text text, tags jsonb) ON COMMIT DROP"))
    conn.execute(
        text("""
            CREATE TEMP TABLE enhanced_tag (
                start_time timestamptz, start_day date, end_day date,
                custom_name text, tag_type_code text, comment text
            ) ON COMMIT DROP
        """)
    )
    conn.execute(
        text("""
            INSERT INTO enhanced_tag
                (start_time, start_day, end_day, custom_name, tag_type_code, comment)
            VALUES
                ('2026-09-28 12:00+00', '2026-09-28', '2026-10-02', 'illness', NULL, NULL),
                ('2026-09-01 12:00+00', '2026-09-01', '2026-09-15', 'travel', NULL, NULL),
                ('2026-10-01 12:00+00', '2026-10-01', NULL, 'caffeine', NULL, NULL),
                ('2026-09-30 12:00+00', '2026-09-30', NULL, NULL, 'alcohol', NULL),
                ('2026-10-02 12:00+00', '2026-10-02', '2026-10-05', 'sauna', NULL, NULL),
                ('2026-10-03 12:00+00', '2026-10-03', '2026-10-04', 'late', NULL, NULL)
        """)
    )

    labels = set(PostgresProvider().tags(date(2026, 10, 1), date(2026, 10, 2))["label"])

    assert labels == {"illness", "caffeine", "sauna"}


def test_postgres_sync_status_does_not_treat_failed_attempts_as_fresh(frontend_pg_connection):
    conn = frontend_pg_connection
    conn.execute(
        text("""
            CREATE TEMP TABLE sync_log (
                endpoint text PRIMARY KEY, last_sync_date date, updated_at timestamptz,
                last_success_at timestamptz, last_error text, consecutive_failures int
            ) ON COMMIT DROP
        """)
    )
    conn.execute(
        text("""
            INSERT INTO sync_log VALUES
                ('healthy', CURRENT_DATE, now(), now(), NULL, 0),
                ('failing', CURRENT_DATE, now(), now(), 'HTTP 401', 1),
                ('stale', CURRENT_DATE - 1, now(), now() - interval '1 day', NULL, 0),
                ('never_synced', NULL, now(), NULL, NULL, 0)
        """)
    )

    frame = PostgresProvider.sync_status.__wrapped__(PostgresProvider())
    statuses = frame.set_index("endpoint")["status"].to_dict()

    assert statuses == {"healthy": "Fresh", "failing": "Error", "stale": "Stale", "never_synced": "Never synced"}
    assert frame.set_index("endpoint").loc["failing", "last_error"] == "HTTP 401"


def test_api_cache_expires_so_new_sync_data_becomes_visible(monkeypatch):
    monkeypatch.setattr(providers.st, "session_state", {})
    clock = Mock(return_value=1000)
    monkeypatch.setattr("data.api_provider.time.monotonic", clock)
    provider = ApiProvider("test-token")
    provider._fetch = Mock(side_effect=[[], [{"day": "2026-07-08", "score": 90}]])
    args = ("daily_sleep", date(2026, 7, 1), date(2026, 7, 8))

    assert provider._fetch_cached(*args) == []
    clock.return_value = 1299
    assert provider._fetch_cached(*args) == []
    provider._fetch.assert_called_once()
    clock.return_value = 1300
    assert provider._fetch_cached(*args) == [{"day": "2026-07-08", "score": 90}]


def test_api_cache_is_isolated_between_accounts(monkeypatch):
    monkeypatch.setattr(providers.st, "session_state", {})
    first = ApiProvider("first-account-token")
    second = ApiProvider("second-account-token")
    first._fetch = Mock(return_value=[{"score": 90}])
    second._fetch = Mock(return_value=[{"score": 50}])

    assert first._fetch_cached("daily_sleep") == [{"score": 90}]
    assert second._fetch_cached("daily_sleep") == [{"score": 50}]


def test_api_datetime_cache_changes_with_selected_timezone(monkeypatch):
    session = {"user_timezone": "America/Toronto"}
    monkeypatch.setattr(providers.st, "session_state", session)
    provider = ApiProvider("test-token")
    provider._fetch = Mock(side_effect=[[{"bpm": 60}], [{"bpm": 70}]])
    args = ("heartrate", date(2026, 7, 1), date(2026, 7, 8))

    assert provider._fetch_cached(*args, query_mode="datetime") == [{"bpm": 60}]
    session["user_timezone"] = "Asia/Tokyo"
    assert provider._fetch_cached(*args, query_mode="datetime") == [{"bpm": 70}]
