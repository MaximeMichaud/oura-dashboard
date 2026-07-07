"""Tests for oura_ingest.api_client (tasks 20, 22)."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import requests
from oura_ingest.api_client import (
    MAX_RETRY_AFTER,
    OuraClient,
    RateLimitError,
    _is_retryable,
    _wait_for_rate_limit,
)

# --- Task 20: _is_retryable tests ---


class TestIsRetryable:
    def test_rate_limit_error(self):
        assert _is_retryable(RateLimitError(60)) is True

    def test_retryable_500(self):
        exc = requests.HTTPError(response=Mock(status_code=500))
        assert _is_retryable(exc) is True

    def test_retryable_502(self):
        exc = requests.HTTPError(response=Mock(status_code=502))
        assert _is_retryable(exc) is True

    def test_retryable_503(self):
        exc = requests.HTTPError(response=Mock(status_code=503))
        assert _is_retryable(exc) is True

    def test_not_retryable_404(self):
        exc = requests.HTTPError(response=Mock(status_code=404))
        assert _is_retryable(exc) is False

    def test_not_retryable_401(self):
        exc = requests.HTTPError(response=Mock(status_code=401))
        assert _is_retryable(exc) is False

    def test_not_retryable_no_response(self):
        exc = requests.HTTPError(response=None)
        assert _is_retryable(exc) is False

    def test_retryable_connection_error(self):
        assert _is_retryable(requests.ConnectionError("network")) is True

    def test_retryable_timeout(self):
        assert _is_retryable(requests.Timeout("timed out")) is True

    def test_not_retryable_value_error(self):
        assert _is_retryable(ValueError("bad")) is False


class TestRateLimitError:
    def test_stores_retry_after(self):
        err = RateLimitError(120)
        assert err.retry_after == 120
        assert "120" in str(err)


# --- Task 22: fetch_all tests ---


class TestFetchAll:
    def _make_client(self):
        return OuraClient(token="test-token")

    def test_empty_response(self):
        client = self._make_client()
        resp = Mock(status_code=200)
        resp.json.return_value = {"data": [], "next_token": None}
        resp.raise_for_status = Mock()
        client.session = Mock(headers={})
        client.session.get.return_value = resp

        results = list(client.fetch_all("daily_sleep", "2024-01-01", "2024-01-31"))
        assert results == []

    def test_single_page(self):
        client = self._make_client()
        records = [{"day": "2024-01-01", "score": 85}, {"day": "2024-01-02", "score": 90}]
        resp = Mock(status_code=200)
        resp.json.return_value = {"data": records, "next_token": None}
        resp.raise_for_status = Mock()
        client.session = Mock(headers={})
        client.session.get.return_value = resp

        results = list(client.fetch_all("daily_sleep", "2024-01-01", "2024-01-31"))
        assert results == records
        assert client.session.get.call_count == 1

    def test_multi_page(self):
        client = self._make_client()
        page1 = [{"day": "2024-01-01"}]
        page2 = [{"day": "2024-01-02"}]

        resp1 = Mock(status_code=200, raise_for_status=Mock())
        resp1.json.return_value = {"data": page1, "next_token": "abc123"}
        resp2 = Mock(status_code=200, raise_for_status=Mock())
        resp2.json.return_value = {"data": page2, "next_token": None}

        client.session = Mock(headers={})
        client.session.get.side_effect = [resp1, resp2]

        results = list(client.fetch_all("daily_sleep", "2024-01-01", "2024-01-31"))
        assert results == page1 + page2
        assert client.session.get.call_count == 2

    def test_404_returns_empty(self):
        client = self._make_client()
        error_resp = Mock(status_code=404)
        exc = requests.HTTPError(response=error_resp)

        resp = Mock(status_code=404)
        resp.raise_for_status.side_effect = exc
        client.session = Mock(headers={})
        client.session.get.return_value = resp

        results = list(client.fetch_all("nonexistent", "2024-01-01", "2024-01-31"))
        assert results == []

    def test_401_refreshes_oauth_token_once(self):
        token_provider = Mock()
        token_provider.can_refresh = True
        token_provider.get_token.side_effect = ["old-token", "new-token"]
        client = OuraClient(token_provider=token_provider)

        resp_401 = Mock(status_code=401)
        resp_401.raise_for_status = Mock()
        resp_ok = Mock(status_code=200)
        resp_ok.json.return_value = {"data": [{"day": "2024-01-01"}], "next_token": None}
        resp_ok.raise_for_status = Mock()

        client.session = Mock(headers={})
        client.session.get.side_effect = [resp_401, resp_ok]

        results = list(client.fetch_all("daily_sleep", "2024-01-01", "2024-01-31"))

        assert results == [{"day": "2024-01-01"}]
        assert token_provider.get_token.call_count == 2
        token_provider.get_token.assert_any_call(force_refresh=True)


# --- _wait_for_rate_limit: the custom tenacity wait strategy ---


class TestWaitForRateLimit:
    @staticmethod
    def _state(exc, attempt):
        # Mimic tenacity's RetryCallState: outcome.exception() + attempt_number.
        return SimpleNamespace(
            outcome=SimpleNamespace(exception=lambda: exc),
            attempt_number=attempt,
        )

    def test_uses_retry_after_for_rate_limit(self):
        assert _wait_for_rate_limit(self._state(RateLimitError(100), 1)) == 100

    def test_caps_retry_after_at_max(self):
        assert _wait_for_rate_limit(self._state(RateLimitError(10_000), 1)) == MAX_RETRY_AFTER

    def test_exponential_backoff_for_other_errors(self):
        # Backoff is min(2 ** attempt_number * 2, 120).
        assert _wait_for_rate_limit(self._state(requests.ConnectionError("x"), 1)) == 4
        assert _wait_for_rate_limit(self._state(requests.ConnectionError("x"), 2)) == 8

    def test_backoff_capped_at_120(self):
        assert _wait_for_rate_limit(self._state(requests.Timeout("x"), 20)) == 120


# --- _get: 429 translation, tested without the tenacity retry wrapper ---


class TestGetRateLimit:
    """Calling the decorated _get with a retryable error would make tenacity sleep
    between attempts. __wrapped__ is the raw, undecorated method, so the 429 -> RateLimitError
    translation can be tested in isolation without real backoff sleeps."""

    @staticmethod
    def _raw_get(client, resp):
        client.session = Mock(headers={})
        client.session.get.return_value = resp
        return OuraClient._get.__wrapped__(client, "https://api.example/x", {})

    def test_429_raises_rate_limit_error_from_header(self):
        client = OuraClient(token="t")
        resp = Mock(status_code=429, headers={"Retry-After": "120"})
        with pytest.raises(RateLimitError) as ei:
            self._raw_get(client, resp)
        assert ei.value.retry_after == 120

    def test_429_defaults_to_60_without_header(self):
        client = OuraClient(token="t")
        resp = Mock(status_code=429, headers={})
        with pytest.raises(RateLimitError) as ei:
            self._raw_get(client, resp)
        assert ei.value.retry_after == 60

    def test_429_parses_fractional_retry_after(self):
        client = OuraClient(token="t")
        resp = Mock(status_code=429, headers={"Retry-After": "90.7"})
        with pytest.raises(RateLimitError) as ei:
            self._raw_get(client, resp)
        assert ei.value.retry_after == 90

    def test_success_returns_response(self):
        client = OuraClient(token="t")
        resp = Mock(status_code=200, raise_for_status=Mock())
        assert self._raw_get(client, resp) is resp
        resp.raise_for_status.assert_called_once()

    def test_server_error_propagates_via_raise_for_status(self):
        client = OuraClient(token="t")
        resp = Mock(status_code=500)
        resp.raise_for_status.side_effect = requests.HTTPError(response=Mock(status_code=500))
        with pytest.raises(requests.HTTPError):
            self._raw_get(client, resp)


# --- _get: the live tenacity retry policy (decorated method, sleeping neutralised) ---


class TestGetRetryPolicy:
    """Exercises the real tenacity-decorated _get (not __wrapped__) so a regression in the
    retry predicate, the attempt cap, or the wait strategy is caught. A fake sleep is injected
    with retry_with(sleep=...) - no global controller mutation - and its recorded delays prove
    that Retry-After (429) and exponential backoff (5xx / network) are actually honoured, so a
    regression to wait_fixed(0) or one that ignores Retry-After would fail these tests."""

    @staticmethod
    def _client(responses):
        client = OuraClient(token="t")
        client.session = Mock(headers={})
        client.session.get.side_effect = responses
        return client

    @staticmethod
    def _run(client):
        """Drive the decorated _get with each sleep captured instead of performed."""
        delays = []
        decorated = OuraClient._get.retry_with(sleep=delays.append)
        resp = decorated(client, "https://api.example/x", {})
        return resp, delays

    @staticmethod
    def _ok():
        return Mock(status_code=200, raise_for_status=Mock())

    @staticmethod
    def _rate_limited(retry_after="1"):
        return Mock(status_code=429, headers={"Retry-After": retry_after})

    @staticmethod
    def _server_error():
        resp = Mock(status_code=500)
        resp.raise_for_status.side_effect = requests.HTTPError(response=Mock(status_code=500))
        return resp

    def test_retries_429_and_waits_the_retry_after_value(self):
        client = self._client([self._rate_limited("1"), self._rate_limited("1"), self._ok()])
        resp, delays = self._run(client)
        assert resp.status_code == 200
        assert client.session.get.call_count == 3
        # Each wait equals the Retry-After header, not a generic backoff.
        assert delays == [1, 1]

    def test_retries_500_with_exponential_backoff(self):
        client = self._client([self._server_error(), self._ok()])
        resp, delays = self._run(client)
        assert resp.status_code == 200
        assert client.session.get.call_count == 2
        # min(2 ** attempt_number * 2, 120) -> 4s on the first retry.
        assert delays == [4]

    def test_retries_connection_error_with_backoff(self):
        client = self._client([requests.ConnectionError("reset"), self._ok()])
        resp, delays = self._run(client)
        assert resp.status_code == 200
        assert client.session.get.call_count == 2
        assert delays == [4]

    def test_gives_up_after_six_attempts_on_persistent_429(self):
        client = self._client([self._rate_limited("1") for _ in range(6)])
        delays = []
        decorated = OuraClient._get.retry_with(sleep=delays.append)
        with pytest.raises(RateLimitError):
            decorated(client, "https://api.example/x", {})
        # stop_after_attempt(6): six calls, five Retry-After waits between them, then reraise.
        assert client.session.get.call_count == 6
        assert delays == [1, 1, 1, 1, 1]

    def test_does_not_retry_non_retryable_404(self):
        notfound = Mock(status_code=404)
        notfound.raise_for_status.side_effect = requests.HTTPError(response=Mock(status_code=404))
        client = self._client([notfound])
        delays = []
        decorated = OuraClient._get.retry_with(sleep=delays.append)
        with pytest.raises(requests.HTTPError):
            decorated(client, "https://api.example/x", {})
        # 404 is not retryable -> a single attempt and no waiting.
        assert client.session.get.call_count == 1
        assert delays == []


# --- fetch_all: error propagation ---


class TestFetchAllErrors:
    """_get is replaced on the instance so the tenacity retry/sleep machinery never runs."""

    def test_non_404_http_error_is_reraised(self):
        client = OuraClient(token="t")
        client._get = Mock(side_effect=requests.HTTPError(response=Mock(status_code=500)))
        with pytest.raises(requests.HTTPError):
            list(client.fetch_all("daily_sleep", "2024-01-01", "2024-01-31"))

    def test_http_error_without_response_is_reraised(self):
        client = OuraClient(token="t")
        client._get = Mock(side_effect=requests.HTTPError(response=None))
        with pytest.raises(requests.HTTPError):
            list(client.fetch_all("daily_sleep", "2024-01-01", "2024-01-31"))
