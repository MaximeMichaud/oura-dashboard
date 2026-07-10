from datetime import date, datetime, timezone
from unittest.mock import Mock

import pytest
import requests
from components.sidebar import _today_in_timezone
from data import providers
from data.api_provider import ApiProvider
from data.oauth import OAuthToken


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
