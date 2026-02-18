import logging
import os
import signal
import threading

import schedule

from .api_client import OuraClient
from .config import cfg
from .db import wait_for_db
from .ingest import sync_all

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
)
log = logging.getLogger(__name__)

_stop = threading.Event()


def _shutdown(signum, frame):
    log.info("Received signal %d, shutting down...", signum)
    _stop.set()


def main():
    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    cfg.validate()

    log.info("Oura ingestion starting")
    engine = wait_for_db()
    client = OuraClient()

    # Initial sync
    log.info("Running initial sync...")
    sync_all(engine, client)

    # Schedule periodic sync
    interval = cfg.SYNC_INTERVAL_MINUTES
    log.info("Scheduling sync every %d minutes", interval)
    schedule.every(interval).minutes.do(sync_all, engine=engine, client=client)

    while not _stop.is_set():
        schedule.run_pending()
        _stop.wait(timeout=10)

    log.info("Shutdown complete")


if __name__ == "__main__":
    main()
