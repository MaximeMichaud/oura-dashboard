"""Integration tests requiring a real PostgreSQL connection (task 47).

Run with: pytest tests/test_integration.py -v -m integration
Requires: running PostgreSQL with the oura schema applied.
Set TEST_DATABASE_URL env var to override the default connection string.
"""

import os

import pytest

try:
    from sqlalchemy import create_engine, text

    HAS_SQLALCHEMY = True
except ImportError:
    HAS_SQLALCHEMY = False


def _get_engine():
    url = os.getenv("TEST_DATABASE_URL", "postgresql://oura:oura@localhost:5432/oura")
    return create_engine(url)


def _db_available():
    if not HAS_SQLALCHEMY:
        return False
    try:
        engine = _get_engine()
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not _db_available(), reason="PostgreSQL not available")


@pytest.fixture(scope="module")
def pg_engine():
    return _get_engine()


class TestSleepPrimaryView:
    def test_view_exists(self, pg_engine):
        """sleep_primary materialized view should exist."""
        with pg_engine.connect() as conn:
            result = conn.execute(text("SELECT count(*) FROM pg_matviews WHERE matviewname = 'sleep_primary'"))
            assert result.scalar() == 1

    def test_distinct_on_picks_longest(self, pg_engine):
        """sleep_primary should keep only the longest sleep session per day."""
        with pg_engine.connect() as conn:
            # Insert test data
            conn.execute(
                text("""
                INSERT INTO sleep (id, day, type, total_sleep)
                VALUES ('test-short-1', '1999-01-01', 'long_sleep', 20000)
                ON CONFLICT (id) DO UPDATE SET total_sleep = EXCLUDED.total_sleep
            """)
            )
            conn.execute(
                text("""
                INSERT INTO sleep (id, day, type, total_sleep)
                VALUES ('test-long-1', '1999-01-01', 'long_sleep', 30000)
                ON CONFLICT (id) DO UPDATE SET total_sleep = EXCLUDED.total_sleep
            """)
            )
            conn.commit()

            # Refresh the view
            conn.execute(text("REFRESH MATERIALIZED VIEW CONCURRENTLY sleep_primary"))
            conn.commit()

            # Verify the view picks the longest
            result = conn.execute(text("SELECT total_sleep FROM sleep_primary WHERE day = '1999-01-01'"))
            row = result.fetchone()
            assert row is not None
            assert row[0] == 30000

            # Cleanup test data
            conn.execute(text("DELETE FROM sleep WHERE id IN ('test-short-1', 'test-long-1')"))
            conn.commit()
            conn.execute(text("REFRESH MATERIALIZED VIEW CONCURRENTLY sleep_primary"))
            conn.commit()

    def test_unique_index_on_day(self, pg_engine):
        """sleep_primary should have a unique index on day."""
        with pg_engine.connect() as conn:
            result = conn.execute(
                text("""
                    SELECT count(*) FROM pg_indexes
                    WHERE tablename = 'sleep_primary' AND indexname = 'idx_sleep_primary_day'
                """)
            )
            assert result.scalar() == 1


class TestSyncLogSchema:
    def test_sync_log_columns(self, pg_engine):
        """sync_log should have all expected columns."""
        with pg_engine.connect() as conn:
            result = conn.execute(
                text("""
                    SELECT column_name FROM information_schema.columns
                    WHERE table_name = 'sync_log'
                    ORDER BY ordinal_position
                """)
            )
            columns = {row[0] for row in result}
            expected = {
                "endpoint",
                "last_sync_date",
                "record_count",
                "updated_at",
                "last_error",
                "consecutive_failures",
                "last_success_at",
            }
            assert expected.issubset(columns)

    def test_sync_history_table_exists(self, pg_engine):
        """sync_history table should exist."""
        with pg_engine.connect() as conn:
            result = conn.execute(
                text("""
                    SELECT count(*) FROM information_schema.tables
                    WHERE table_name = 'sync_history' AND table_schema = 'public'
                """)
            )
            assert result.scalar() == 1
