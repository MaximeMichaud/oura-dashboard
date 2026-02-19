"""Tests for oura_ingest.api_client (tasks 20, 22)."""

from unittest.mock import Mock

import requests
from oura_ingest.api_client import OuraClient, RateLimitError, _is_retryable

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
        client.session = Mock()
        client.session.get.return_value = resp

        results = list(client.fetch_all("daily_sleep", "2024-01-01", "2024-01-31"))
        assert results == []

    def test_single_page(self):
        client = self._make_client()
        records = [{"day": "2024-01-01", "score": 85}, {"day": "2024-01-02", "score": 90}]
        resp = Mock(status_code=200)
        resp.json.return_value = {"data": records, "next_token": None}
        resp.raise_for_status = Mock()
        client.session = Mock()
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

        client.session = Mock()
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
        client.session = Mock()
        client.session.get.return_value = resp

        results = list(client.fetch_all("nonexistent", "2024-01-01", "2024-01-31"))
        assert results == []
