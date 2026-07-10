import logging
from datetime import date, datetime, time, timedelta, timezone
from typing import Iterator
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import requests
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception,
    stop_after_attempt,
)

from .auth import EnvTokenProvider, StaticTokenProvider
from .config import cfg

log = logging.getLogger(__name__)

BASE_URL = "https://api.ouraring.com/v2/usercollection"


MAX_RETRY_AFTER = 300  # Cap Retry-After to 5 minutes


def _is_retryable(exc: BaseException) -> bool:
    if isinstance(exc, RateLimitError):
        return True
    if isinstance(exc, requests.HTTPError):
        return exc.response is not None and exc.response.status_code in (500, 502, 503)
    if isinstance(exc, (requests.ConnectionError, requests.Timeout)):
        return True
    return False


class RateLimitError(Exception):
    def __init__(self, retry_after: int):
        self.retry_after = retry_after
        super().__init__(f"Rate limited, retry after {retry_after}s")


def _wait_for_rate_limit(retry_state) -> float:
    """Custom wait: use Retry-After for 429, exponential backoff otherwise."""
    exc = retry_state.outcome.exception()
    if isinstance(exc, RateLimitError):
        return min(exc.retry_after, MAX_RETRY_AFTER)
    # Exponential backoff for other retryable errors
    return min(2**retry_state.attempt_number * 2, 120)


class OuraClient:
    def __init__(
        self,
        token: str | None = None,
        token_provider=None,
        user_timezone: str | None = None,
    ):
        self.session = requests.Session()
        if token_provider is not None:
            self.token_provider = token_provider
        elif token is not None:
            self.token_provider = StaticTokenProvider(token)
        else:
            self.token_provider = EnvTokenProvider()
        provider_config = getattr(self.token_provider, "config", None)
        provider_timezone = getattr(provider_config, "USER_TIMEZONE", None)
        timezone_name = user_timezone or (
            provider_timezone if isinstance(provider_timezone, str) and provider_timezone else cfg.USER_TIMEZONE
        )
        try:
            self.user_timezone = ZoneInfo(timezone_name)
        except ZoneInfoNotFoundError as exc:
            raise ValueError(f"Invalid user timezone: {timezone_name!r}") from exc

    def _set_authorization_header(self, force_refresh: bool = False) -> None:
        token = self.token_provider.get_token(force_refresh=force_refresh)
        self.session.headers["Authorization"] = f"Bearer {token}"

    @retry(
        stop=stop_after_attempt(6),
        wait=_wait_for_rate_limit,
        retry=retry_if_exception(_is_retryable),
        before_sleep=before_sleep_log(log, logging.WARNING),
        reraise=True,
    )
    def _get(self, url: str, params: dict) -> requests.Response:
        self._set_authorization_header()
        resp = self.session.get(url, params=params, timeout=30)
        if resp.status_code == 401 and self.token_provider.can_refresh:
            log.warning("Oura access token was rejected, refreshing OAuth token and retrying once")
            self._set_authorization_header(force_refresh=True)
            resp = self.session.get(url, params=params, timeout=30)
        if resp.status_code == 429:
            retry_after = int(float(resp.headers.get("Retry-After", "60")))
            log.warning("Rate limited (429), retry after %ds", retry_after)
            raise RateLimitError(retry_after)
        resp.raise_for_status()
        return resp

    def _range_params(self, start_date: str | None, end_date: str | None, query_mode: str) -> dict:
        if query_mode == "none":
            return {}
        if query_mode == "date":
            return {"start_date": start_date, "end_date": end_date}
        if query_mode != "datetime":
            raise ValueError(f"Unknown query mode: {query_mode}")

        now = datetime.now(timezone.utc)
        local_today = now.astimezone(self.user_timezone).date()
        start = datetime.combine(
            date.fromisoformat(start_date),
            time.min,
            tzinfo=self.user_timezone,
        ).astimezone(timezone.utc)
        end_day = date.fromisoformat(end_date)
        end = (
            now
            if end_day == local_today
            else datetime.combine(end_day, time.max, tzinfo=self.user_timezone).astimezone(timezone.utc)
        )
        return {"start_datetime": start.isoformat(), "end_datetime": end.isoformat()}

    def fetch_all(
        self,
        endpoint: str,
        start_date: str | None = None,
        end_date: str | None = None,
        *,
        query_mode: str = "date",
        response_mode: str = "collection",
    ) -> Iterator[dict]:
        """Paginate through an Oura v2 endpoint, yielding each record."""
        if query_mode == "datetime" and start_date and end_date:
            current = date.fromisoformat(start_date)
            final = date.fromisoformat(end_date)
            if (final - current).days >= 30:
                while current <= final:
                    chunk_end = min(current + timedelta(days=29), final)
                    yield from self.fetch_all(
                        endpoint,
                        current.isoformat(),
                        chunk_end.isoformat(),
                        query_mode=query_mode,
                        response_mode=response_mode,
                    )
                    current = chunk_end + timedelta(days=1)
                return

        url = f"{BASE_URL}/{endpoint}"
        params = self._range_params(start_date, end_date, query_mode)
        seen_next_tokens: set[str] = set()
        while True:
            try:
                resp = self._get(url, params)
            except requests.HTTPError as e:
                if response_mode == "single" and e.response is not None and e.response.status_code == 404:
                    log.warning("[%s] Singleton endpoint not found (404), skipping", endpoint)
                    return
                raise
            body = resp.json()
            if response_mode == "single":
                if not isinstance(body, dict):
                    raise ValueError(f"Unexpected singleton response for {endpoint}")
                yield body
                break
            if response_mode != "collection":
                raise ValueError(f"Unknown response mode: {response_mode}")
            yield from body.get("data", [])
            next_token = body.get("next_token")
            if not next_token:
                break
            if next_token in seen_next_tokens:
                raise RuntimeError(f"Pagination cycle detected for {endpoint}")
            seen_next_tokens.add(next_token)
            params = {"next_token": next_token}
