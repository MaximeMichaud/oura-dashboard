import logging
import time
from typing import Iterator

import requests
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

from .config import cfg

log = logging.getLogger(__name__)

BASE_URL = "https://api.ouraring.com/v2/usercollection"


def _is_retryable(exc: BaseException) -> bool:
    if isinstance(exc, requests.HTTPError):
        return exc.response is not None and exc.response.status_code in (500, 502, 503)
    if isinstance(exc, requests.ConnectionError):
        return True
    return False


class RateLimitError(Exception):
    def __init__(self, retry_after: int):
        self.retry_after = retry_after


class OuraClient:
    def __init__(self, token: str | None = None):
        self.session = requests.Session()
        self.session.headers["Authorization"] = f"Bearer {token or cfg.OURA_TOKEN}"

    @retry(
        stop=stop_after_attempt(6),
        wait=wait_exponential(multiplier=2, min=4, max=120),
        retry=retry_if_exception(_is_retryable),
        before_sleep=before_sleep_log(log, logging.WARNING),
        reraise=True,
    )
    def _get(self, url: str, params: dict) -> requests.Response:
        resp = self.session.get(url, params=params, timeout=30)
        if resp.status_code == 429:
            retry_after = int(resp.headers.get("Retry-After", "60"))
            log.warning("Rate limited (429), waiting %ds before retry", retry_after)
            time.sleep(retry_after)
            # Retry the request after waiting
            resp = self.session.get(url, params=params, timeout=30)
            resp.raise_for_status()
        resp.raise_for_status()
        return resp

    def fetch_all(self, endpoint: str, start_date: str, end_date: str) -> Iterator[dict]:
        """Paginate through an Oura v2 endpoint, yielding each record."""
        url = f"{BASE_URL}/{endpoint}"
        params = {"start_date": start_date, "end_date": end_date}
        while True:
            try:
                resp = self._get(url, params)
            except requests.HTTPError as e:
                if e.response is not None and e.response.status_code == 404:
                    log.warning("[%s] Endpoint not found (404), skipping", endpoint)
                    return
                raise
            body = resp.json()
            yield from body.get("data", [])
            next_token = body.get("next_token")
            if not next_token:
                break
            params = {"next_token": next_token}
