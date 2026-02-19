import logging
import re
from datetime import date, timedelta

import requests
from sqlalchemy import text
from sqlalchemy.engine import Engine

from .api_client import OuraClient
from .config import cfg
from .endpoints import ALL_ENDPOINTS

# Raised on 401 to stop all syncing (invalid/expired token)


class TokenExpiredError(Exception):
    pass

log = logging.getLogger(__name__)

BATCH_SIZE = 500

# Only allow safe SQL identifiers (lowercase letters, digits, underscores)
_SAFE_IDENT = re.compile(r"^[a-z_][a-z0-9_]*$")


def _validate_ident(name: str) -> str:
    if not _SAFE_IDENT.match(name):
        raise ValueError(f"Invalid SQL identifier: {name!r}")
    return name


def _get_start_date(engine: Engine, endpoint_name: str) -> str:
    """Get the start date for an endpoint: last sync date minus overlap, or HISTORY_START_DATE."""
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT last_sync_date FROM sync_log WHERE endpoint = :ep"),
            {"ep": endpoint_name},
        ).fetchone()
    if row:
        d = row[0] - timedelta(days=cfg.OVERLAP_DAYS)
        return d.isoformat()
    return cfg.HISTORY_START_DATE


def _upsert_batch(engine: Engine, table: str, pk: str, rows: list[dict]) -> int:
    """UPSERT a batch of rows using ON CONFLICT DO UPDATE."""
    if not rows:
        return 0

    table = _validate_ident(table)
    pk = _validate_ident(pk)
    cols = [_validate_ident(c) for c in rows[0].keys()]

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


def _update_sync_log(engine: Engine, endpoint_name: str, count: int):
    sql = (
        "INSERT INTO sync_log (endpoint, last_sync_date, record_count, updated_at) "
        "VALUES (:ep, :d, :c, now()) "
        "ON CONFLICT (endpoint) DO UPDATE SET last_sync_date = :d, record_count = :c, updated_at = now()"
    )
    with engine.begin() as conn:
        conn.execute(text(sql), {"ep": endpoint_name, "d": date.today().isoformat(), "c": count})


def sync_endpoint(engine: Engine, client: OuraClient, ep: dict) -> int:
    """Sync a single endpoint: fetch from API, transform, upsert."""
    start = _get_start_date(engine, ep["name"])
    end = date.today().isoformat()
    log.info("[%s] Fetching %s -> %s", ep["name"], start, end)

    rows = []
    for rec in client.fetch_all(ep["api_path"], start, end):
        try:
            rows.append(ep["transform"](rec))
        except Exception:
            log.warning("[%s] Transform error for record: %s", ep["name"], rec.get("id", rec.get("day", "?")), exc_info=True)

    count = _upsert(engine, ep["table"], ep["pk"], rows)
    if count > 0:
        _update_sync_log(engine, ep["name"], count)
    else:
        log.info("[%s] No records upserted, sync_log not advanced", ep["name"])
    log.info("[%s] Upserted %d records", ep["name"], count)
    return count


def sync_all(engine: Engine, client: OuraClient):
    """Sync all endpoints."""
    total = 0
    for ep in ALL_ENDPOINTS:
        try:
            total += sync_endpoint(engine, client, ep)
        except requests.HTTPError as e:
            if e.response is not None and e.response.status_code == 401:
                log.critical("Oura API token is invalid or expired (401). Stopping all syncs.")
                raise TokenExpiredError("Oura API token is invalid or expired") from e
            log.error("[%s] Sync failed", ep["name"], exc_info=True)
        except Exception:
            log.error("[%s] Sync failed", ep["name"], exc_info=True)
    log.info("Sync complete - %d total records", total)
