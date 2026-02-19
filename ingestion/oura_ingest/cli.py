import argparse
import logging
import os
import signal
import threading

import schedule

from .api_client import OuraClient
from .config import cfg
from .db import wait_for_db
from .endpoints import ALL_ENDPOINTS
from .ingest import TokenExpiredError, sync_all

log = logging.getLogger(__name__)

_stop = threading.Event()


def _shutdown(signum, frame):
    log.info("Received signal %d, shutting down...", signum)
    _stop.set()


def main():
    parser = argparse.ArgumentParser(description="Oura ingestion service")
    parser.add_argument("--endpoint", help="Sync only this endpoint name")
    parser.add_argument("--once", action="store_true", help="Sync once and exit (no scheduler)")
    parser.add_argument("--list-endpoints", action="store_true", help="Print available endpoints and exit")
    args = parser.parse_args()

    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    )

    if args.list_endpoints:
        for ep in ALL_ENDPOINTS:
            print(ep.name)
        return

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    cfg.validate()

    log.info("Oura ingestion starting")
    engine = wait_for_db()
    client = OuraClient()

    # Initial sync
    log.info("Running initial sync...")
    try:
        sync_all(engine, client, only_endpoint=args.endpoint)
    except TokenExpiredError:
        log.critical("Exiting due to invalid Oura token. Refresh your OURA_TOKEN and restart.")
        return

    if args.once:
        log.info("--once flag set, exiting after initial sync")
        return

    # Schedule periodic sync
    interval = cfg.SYNC_INTERVAL_MINUTES
    log.info("Scheduling sync every %d minutes", interval)

    def _safe_sync():
        try:
            sync_all(engine, client, only_endpoint=args.endpoint)
        except TokenExpiredError:
            log.critical("Oura token expired during scheduled sync. Stopping scheduler.")
            _stop.set()

    schedule.every(interval).minutes.do(_safe_sync)

    while not _stop.is_set():
        schedule.run_pending()
        _stop.wait(timeout=10)

    log.info("Shutdown complete")


if __name__ == "__main__":
    main()
