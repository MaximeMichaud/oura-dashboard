import itertools
import logging
import re
import threading
import time
from datetime import date, timedelta
from pathlib import Path

import requests
from sqlalchemy import text
from sqlalchemy.engine import Engine

from .api_client import OuraClient
from .auth import OAuthError
from .config import cfg
from .endpoints import ALL_ENDPOINTS

# Raised on 401 to stop all syncing (invalid/expired token)


class TokenExpiredError(Exception):
    pass


class TransformError(RuntimeError):
    def __init__(self, endpoint_name: str, failed_count: int):
        self.failed_count = failed_count
        self.record_count = 0
        self.duration = 0.0
        super().__init__(f"{failed_count} record(s) failed transformation for {endpoint_name}")


log = logging.getLogger(__name__)

BATCH_SIZE = 500

_sync_lock = threading.Lock()
_SENTINEL_PATH = Path("/tmp/oura-last-sync")

# Only allow safe SQL identifiers (lowercase letters, digits, underscores)
_SAFE_IDENT = re.compile(r"^[a-z_][a-z0-9_]*$")


def _validate_ident(name: str) -> str:
    if not _SAFE_IDENT.match(name):
        raise ValueError(f"Invalid SQL identifier: {name!r}")
    return name


def _get_start_date(
    engine: Engine,
    endpoint_name: str,
    initial_history_days: int | None = None,
    always_full_sync: bool = False,
    today: date | None = None,
) -> str:
    """Get the start date for an endpoint: last sync date minus overlap, or HISTORY_START_DATE."""
    if always_full_sync:
        return cfg.HISTORY_START_DATE
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT last_sync_date FROM sync_log WHERE endpoint = :ep"),
            {"ep": endpoint_name},
        ).fetchone()
    if row and row[0]:
        d = row[0] - timedelta(days=cfg.OVERLAP_DAYS)
        return d.isoformat()
    history_start = date.fromisoformat(cfg.HISTORY_START_DATE)
    if initial_history_days is not None:
        today = today or cfg.local_date()
        history_start = max(history_start, today - timedelta(days=initial_history_days))
    return history_start.isoformat()


def _upsert_batch(engine: Engine, table: str, pk: str, rows: list[dict]) -> int:
    """UPSERT a batch of rows using ON CONFLICT DO UPDATE."""
    if not rows:
        return 0

    table = _validate_ident(table)
    pk = _validate_ident(pk)
    # Union of all keys across rows to handle optional fields
    all_keys: set[str] = set()
    for r in rows:
        all_keys.update(r.keys())
    cols = sorted(_validate_ident(c) for c in all_keys)
    # Normalise rows so every row has every key
    rows = [{c: r.get(c) for c in cols} for r in rows]

    non_pk_cols = [c for c in cols if c != pk]
    if not non_pk_cols:
        return 0

    col_list = ", ".join(cols)
    val_list = ", ".join(f":{c}" for c in cols)
    update_list = ", ".join(f"{c} = EXCLUDED.{c}" for c in non_pk_cols)

    sql = (
        f"INSERT INTO {table} ({col_list}) VALUES ({val_list}) "
        f"ON CONFLICT ({pk}) DO UPDATE SET {update_list}, updated_at = now()"
    )
    with engine.begin() as conn:
        conn.execute(text(sql), rows)
    return len(rows)


def _upsert(engine: Engine, table: str, pk: str, rows: list[dict]) -> int:
    """UPSERT rows in batches."""
    if not rows:
        return 0
    total = 0
    for i in range(0, len(rows), BATCH_SIZE):
        batch = rows[i : i + BATCH_SIZE]
        total += _upsert_batch(engine, table, pk, batch)
    return total


def _update_sync_log(engine: Engine, endpoint_name: str, count: int, sync_date: date | None = None):
    sql = (
        "INSERT INTO sync_log (endpoint, last_sync_date, record_count, updated_at,"
        " last_error, consecutive_failures, last_success_at) "
        "VALUES (:ep, :d, :c, now(), NULL, 0, now()) "
        "ON CONFLICT (endpoint) DO UPDATE SET "
        "last_sync_date = :d, record_count = :c, updated_at = now(), "
        "last_error = NULL, consecutive_failures = 0, last_success_at = now()"
    )
    with engine.begin() as conn:
        cursor_date = sync_date or cfg.local_date()
        conn.execute(text(sql), {"ep": endpoint_name, "d": cursor_date.isoformat(), "c": count})


def _record_sync_failure(engine: Engine, endpoint_name: str, error_msg: str):
    sql = (
        "INSERT INTO sync_log (endpoint, updated_at, last_error, consecutive_failures) "
        "VALUES (:ep, now(), :err, 1) "
        "ON CONFLICT (endpoint) DO UPDATE SET "
        "last_error = :err, consecutive_failures = sync_log.consecutive_failures + 1, "
        "updated_at = now()"
    )
    with engine.begin() as conn:
        conn.execute(text(sql), {"ep": endpoint_name, "err": error_msg})


def _record_sync_history(
    engine: Engine,
    endpoint_name: str,
    count: int,
    duration: float,
    status: str,
    error: str | None = None,
):
    sql = (
        "INSERT INTO sync_history (endpoint, record_count, duration_seconds, status, error_message) "
        "VALUES (:ep, :cnt, :dur, :status, :err)"
    )
    with engine.begin() as conn:
        conn.execute(text(sql), {"ep": endpoint_name, "cnt": count, "dur": duration, "status": status, "err": error})


def _chunked(iterable, n):
    """Yield successive chunks of size n from iterable."""
    it = iter(iterable)
    while True:
        chunk = []
        try:
            chunk.extend(itertools.islice(it, n))
        except Exception:
            if chunk:
                yield chunk
            raise
        if not chunk:
            return
        yield chunk


def _transform_stream(ep, records):
    """Apply transforms, then fail the stream if any records were invalid."""
    failed_count = 0
    for rec in records:
        try:
            yield ep.transform(rec)
        except Exception:
            failed_count += 1
            rec_id = rec.get("id", rec.get("day", "?"))
            log.warning("[%s] Transform error for record: %s", ep.name, rec_id, exc_info=True)
    if failed_count:
        raise TransformError(ep.name, failed_count)


def sync_endpoint(engine: Engine, client: OuraClient, ep) -> int:
    """Sync a single endpoint: fetch from API, transform, upsert in chunks."""
    t0 = time.monotonic()
    today = cfg.local_date()
    initial_history_days = ep.initial_history_days
    if initial_history_days == -1:
        initial_history_days = cfg.TIMESERIES_HISTORY_DAYS
    start = _get_start_date(engine, ep.name, initial_history_days, ep.always_full_sync, today)
    end = today.isoformat()
    log.info("[%s] Fetching %s -> %s", ep.name, start, end)

    # Staleness gap warning
    gap_days = (today - date.fromisoformat(start)).days
    if gap_days > 3 and not ep.always_full_sync:
        log.warning("[%s] Sync gap: %d days behind", ep.name, gap_days)

    # Stream and upsert in chunks instead of buffering all in RAM
    count = 0
    stream = _transform_stream(
        ep,
        client.fetch_all(
            ep.api_path,
            start,
            end,
            query_mode=ep.query_mode,
            response_mode=ep.response_mode,
        ),
    )
    try:
        for batch in _chunked(stream, BATCH_SIZE):
            count += _upsert_batch(engine, ep.table, ep.pk, batch)
    except TransformError as exc:
        exc.record_count = count
        exc.duration = time.monotonic() - t0
        raise

    duration = time.monotonic() - t0

    _update_sync_log(engine, ep.name, count, today)

    _record_sync_history(engine, ep.name, count, duration, "success")
    log.info("[%s] Upserted %d records in %.1fs", ep.name, count, duration)
    return count


def sync_all(engine: Engine, client: OuraClient, only_endpoint: str | None = None):
    """Sync all (or one) endpoints with overlap guard."""
    if not _sync_lock.acquire(blocking=False):
        log.warning("Sync already in progress, skipping this run")
        return

    try:
        endpoints = ALL_ENDPOINTS
        if only_endpoint:
            endpoints = [ep for ep in ALL_ENDPOINTS if ep.name == only_endpoint]
            if not endpoints:
                log.error("Unknown endpoint: %s", only_endpoint)
                return

        total = 0
        successful_endpoints = 0
        for ep in endpoints:
            try:
                total += sync_endpoint(engine, client, ep)
                successful_endpoints += 1
            except requests.HTTPError as e:
                if e.response is not None and e.response.status_code == 401:
                    log.critical("Oura API token is invalid or expired (401). Stopping all syncs.")
                    raise TokenExpiredError("Oura API token is invalid or expired") from e
                _record_sync_failure(engine, ep.name, str(e))
                _record_sync_history(engine, ep.name, 0, 0, "error", str(e))
                log.error("[%s] Sync failed", ep.name, exc_info=True)
            except OAuthError as e:
                log.critical(
                    "Oura OAuth token refresh failed (%s). Stopping all syncs; re-run 'make oauth-setup'.",
                    e,
                )
                raise TokenExpiredError("Oura OAuth token refresh failed") from e
            except Exception as e:
                _record_sync_failure(engine, ep.name, str(e))
                _record_sync_history(
                    engine,
                    ep.name,
                    getattr(e, "record_count", 0),
                    getattr(e, "duration", 0),
                    "error",
                    str(e),
                )
                log.error("[%s] Sync failed", ep.name, exc_info=True)

        # Refresh materialized view after sync (CONCURRENTLY cannot run inside a transaction)
        try:
            with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
                conn.execute(text("REFRESH MATERIALIZED VIEW CONCURRENTLY sleep_primary"))
            log.info("Refreshed materialized view sleep_primary")
        except Exception:
            log.warning("Could not refresh sleep_primary view", exc_info=True)

        # A failed run must not make the ingestion healthcheck look fresh.
        if successful_endpoints:
            try:
                _SENTINEL_PATH.touch()
            except OSError:
                log.debug("Could not write sentinel file %s", _SENTINEL_PATH)

        log.info("Sync complete - %d total records", total)
    finally:
        _sync_lock.release()
