import logging
import time

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from .config import cfg

log = logging.getLogger(__name__)


def wait_for_db(retries: int = 30, delay: float = 2.0) -> Engine:
    engine = create_engine(cfg.database_url, pool_pre_ping=True)
    for attempt in range(1, retries + 1):
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            log.info("Database ready")
            return engine
        except Exception as e:
            log.warning("Waiting for database... (%d/%d) %s: %s", attempt, retries, type(e).__name__, e)
            time.sleep(delay)
    raise RuntimeError("Database not available after %d retries" % retries)
