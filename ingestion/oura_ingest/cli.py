import logging
import os
import signal
import threading

import schedule

from .api_client import OuraClient
from .config import cfg
from .db import wait_for_db
from .ingest import TokenExpiredError, sync_all

log = logging.getLogger(__name__)

_stop = threading.Event()


def _shutdown(signum, frame):
    log.info("Received signal %d, shutting down...", signum)
    _stop.set()


def main():
    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    )

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    cfg.validate()

    log.info("Oura ingestion starting")
    engine = wait_for_db()
    client = OuraClient()

    # Initial sync
    log.info("Running initial sync...")
    try:
        sync_all(engine, client)
    except TokenExpiredError:
        log.critical("Exiting due to invalid Oura token. Refresh your OURA_TOKEN and restart.")
        return

    # Schedule periodic sync
    interval = cfg.SYNC_INTERVAL_MINUTES
    log.info("Scheduling sync every %d minutes", interval)

    def _safe_sync():
        try:
            sync_all(engine, client)
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
