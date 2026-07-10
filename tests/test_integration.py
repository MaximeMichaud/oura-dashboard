"""Integration tests requiring a real PostgreSQL connection (task 47).

Run with: pytest tests/test_integration.py -v -m integration
Requires: running PostgreSQL with the oura schema applied.
Set TEST_DATABASE_URL env var to override the default connection string.
"""

import os

import pytest

try:
    from sqlalchemy import create_engine, text
    from sqlalchemy.engine import make_url
    from sqlalchemy.exc import DBAPIError

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


@pytest.fixture(scope="module")
def grafana_engine():
    admin_url = make_url(os.getenv("TEST_DATABASE_URL", "postgresql://oura:oura@localhost:5432/oura"))
    url = admin_url.set(
        username="oura_grafana",
        password=os.getenv("GRAFANA_DB_PASSWORD", "oura_grafana"),
    )
    engine = create_engine(url)
    try:
        yield engine
    finally:
        engine.dispose()


class TestGrafanaRoleIsolation:
    def test_role_is_restricted_and_read_only_by_default(self, pg_engine):
        with pg_engine.connect() as conn:
            role = (
                conn.execute(
                    text(
                        """
                    SELECT rolcanlogin, rolsuper, rolcreatedb, rolcreaterole,
                           rolinherit, rolreplication, rolbypassrls,
                           COALESCE(rolconfig, ARRAY[]::text[]) AS settings
                    FROM pg_catalog.pg_roles
                    WHERE rolname = 'oura_grafana'
                    """
                    )
                )
                .mappings()
                .one()
            )

        assert role["rolcanlogin"] is True
        assert role["rolsuper"] is False
        assert role["rolcreatedb"] is False
        assert role["rolcreaterole"] is False
        assert role["rolinherit"] is False
        assert role["rolreplication"] is False
        assert role["rolbypassrls"] is False
        assert "default_transaction_read_only=on" in role["settings"]

    def test_table_grants_exclude_oauth_state_and_writes(self, pg_engine):
        with pg_engine.connect() as conn:
            privileges = (
                conn.execute(
                    text(
                        """
                    SELECT
                        has_table_privilege('oura_grafana', 'public.daily_sleep', 'SELECT') AS can_select,
                        has_table_privilege('oura_grafana', 'public.daily_sleep', 'INSERT') AS can_insert,
                        has_table_privilege('oura_grafana', 'public.oauth_token_state', 'SELECT') AS can_read_oauth
                    """
                    )
                )
                .mappings()
                .one()
            )

        assert privileges == {"can_select": True, "can_insert": False, "can_read_oauth": False}

    def test_future_tables_are_not_granted_by_default(self, pg_engine):
        with pg_engine.connect() as conn:
            has_default_select = conn.execute(
                text(
                    """
                    SELECT EXISTS (
                        SELECT 1
                        FROM pg_catalog.pg_default_acl AS defaults
                        JOIN pg_catalog.pg_namespace AS namespace
                          ON namespace.oid = defaults.defaclnamespace
                        CROSS JOIN LATERAL pg_catalog.aclexplode(
                            COALESCE(
                                defaults.defaclacl,
                                pg_catalog.acldefault(defaults.defaclobjtype, defaults.defaclrole)
                            )
                        ) AS privilege
                        JOIN pg_catalog.pg_roles AS grantee ON grantee.oid = privilege.grantee
                        WHERE namespace.nspname = 'public'
                          AND defaults.defaclobjtype = 'r'
                          AND grantee.rolname = 'oura_grafana'
                          AND privilege.privilege_type = 'SELECT'
                    )
                    """
                )
            ).scalar_one()

        assert has_default_select is False

    def test_select_is_allowed(self, grafana_engine):
        with grafana_engine.connect() as conn:
            assert conn.execute(text("SELECT count(*) FROM public.daily_sleep")).scalar_one() >= 0

    def test_insert_is_refused(self, grafana_engine):
        with grafana_engine.connect() as conn:
            with pytest.raises(DBAPIError):
                conn.execute(text("INSERT INTO public.daily_sleep (day) VALUES ('1900-01-01')"))

    def test_oauth_state_is_inaccessible(self, grafana_engine):
        with grafana_engine.connect() as conn:
            with pytest.raises(DBAPIError):
                conn.execute(text("SELECT provider FROM public.oauth_token_state LIMIT 1"))


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

    def test_extended_api_tables_exist(self, pg_engine):
        expected = {
            "heartrate",
            "ring_battery_level",
            "ring_configuration",
            "session",
            "tag",
            "enhanced_tag",
            "rest_mode_period",
            "personal_info",
            "oauth_token_state",
        }
        with pg_engine.connect() as conn:
            rows = conn.execute(text("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'"))
            assert expected.issubset({row[0] for row in rows})

    def test_personal_info_does_not_store_email(self, pg_engine):
        with pg_engine.connect() as conn:
            rows = conn.execute(
                text("SELECT column_name FROM information_schema.columns WHERE table_name = 'personal_info'")
            )
            assert "email" not in {row[0] for row in rows}

    def test_oauth_token_store_encrypts_and_restores_state(self, pg_engine):
        from oura_ingest.token_store import PostgresOAuthTokenStore

        store = PostgresOAuthTokenStore(pg_engine, "test-encryption-key", provider="test-suite")
        payload = {
            "access_token": "test-access-token",
            "refresh_token": "test-refresh-token",
            "expires_at": 2_000_000_000,
            "scope": "daily",
        }
        try:
            store.save(payload)
            assert store.load() == payload
            with pg_engine.connect() as conn:
                ciphertext = conn.execute(
                    text("SELECT encode(encrypted_payload, 'hex') FROM oauth_token_state WHERE provider = 'test-suite'")
                ).scalar_one()
            assert payload["access_token"].encode().hex() not in ciphertext
            assert payload["refresh_token"].encode().hex() not in ciphertext
        finally:
            with pg_engine.begin() as conn:
                conn.execute(text("DELETE FROM oauth_token_state WHERE provider = 'test-suite'"))


class TestUpsertBatchRealDb:
    """Validates the production UPSERT path (_upsert_batch) against a real PostgreSQL instead
    of only asserting on the generated SQL string: real INSERT, real ON CONFLICT UPDATE,
    no duplicate rows, NULL handling for optional columns, and the updated_at bump.
    A query that looks correct but is rejected by PostgreSQL, or that duplicates/overwrites
    rows during overlap sync, would slip past the string-matching unit tests but fails here."""

    @pytest.fixture
    def upsert_table(self, pg_engine):
        # A regular (non-temporary) table: _upsert_batch opens its own pooled connection via
        # engine.begin(), so a TEMPORARY table created on another connection would be invisible.
        with pg_engine.begin() as conn:
            conn.execute(text("DROP TABLE IF EXISTS _test_upsert_batch"))
            conn.execute(
                text(
                    "CREATE TABLE _test_upsert_batch ("
                    "day date PRIMARY KEY, score integer, note text, "
                    "updated_at timestamptz DEFAULT now())"
                )
            )
        try:
            yield "_test_upsert_batch"
        finally:
            with pg_engine.begin() as conn:
                conn.execute(text("DROP TABLE IF EXISTS _test_upsert_batch"))

    def test_insert_then_conflicting_update(self, pg_engine, upsert_table):
        from datetime import datetime, timezone

        from oura_ingest.ingest import _upsert_batch

        # Initial insert.
        assert _upsert_batch(pg_engine, upsert_table, "day", [{"day": "2025-01-01", "score": 85}]) == 1
        with pg_engine.connect() as conn:
            row = conn.execute(text(f"SELECT score FROM {upsert_table} WHERE day = '2025-01-01'")).fetchone()
        assert row.score == 85

        # Pin updated_at to a known-old value so the bump is provable rather than incidental:
        # if the ON CONFLICT clause stopped setting updated_at = now(), the row would keep this
        # timestamp and the strict assertion below would fail.
        pinned = datetime(2000, 1, 1, tzinfo=timezone.utc)
        with pg_engine.begin() as conn:
            conn.execute(
                text(f"UPDATE {upsert_table} SET updated_at = :ts WHERE day = '2025-01-01'"),
                {"ts": pinned},
            )

        # Conflicting upsert on the same PK must UPDATE in place, never create a duplicate.
        assert _upsert_batch(pg_engine, upsert_table, "day", [{"day": "2025-01-01", "score": 99}]) == 1
        with pg_engine.connect() as conn:
            rows = conn.execute(
                text(f"SELECT score, updated_at FROM {upsert_table} WHERE day = '2025-01-01'")
            ).fetchall()
        assert len(rows) == 1
        assert rows[0].score == 99
        # Strictly newer than the pinned value -> ON CONFLICT really executed updated_at = now().
        assert rows[0].updated_at > pinned

    def test_multi_row_batch_normalises_missing_columns_to_null(self, pg_engine, upsert_table):
        from oura_ingest.ingest import _upsert_batch

        rows = [{"day": "2025-02-01", "score": 70}, {"day": "2025-02-02", "note": "rest day"}]
        assert _upsert_batch(pg_engine, upsert_table, "day", rows) == 2
        with pg_engine.connect() as conn:
            stored = {
                r.day.isoformat(): (r.score, r.note)
                for r in conn.execute(text(f"SELECT day, score, note FROM {upsert_table} ORDER BY day"))
            }
        # Within one batch, every row carries the full column union; the column absent from a
        # given row is written as NULL.
        assert stored["2025-02-01"] == (70, None)
        assert stored["2025-02-02"] == (None, "rest day")

    def test_upsert_batch_only_updates_columns_present_in_the_batch(self, pg_engine, upsert_table):
        """Primitive-level contract of _upsert_batch itself: a column absent from the whole
        batch's key union is left out of the UPDATE SET clause and therefore preserved on
        conflict. NOTE: this preservation path is NOT reached by the real sync - production
        transforms emit a fixed key set (rec.get(...) -> None), so omitted API fields arrive as
        explicit NULLs instead of absent keys. See
        test_overlap_resync_through_transform_overwrites_omitted_fields for what actually happens
        end to end."""
        from oura_ingest.ingest import _upsert_batch

        # Seed a row with both columns populated.
        _upsert_batch(pg_engine, upsert_table, "day", [{"day": "2025-03-01", "score": 50, "note": "keep me"}])

        # Upsert the same PK with 'note' absent from the entire batch -> not in UPDATE SET.
        _upsert_batch(pg_engine, upsert_table, "day", [{"day": "2025-03-01", "score": 51}])

        with pg_engine.connect() as conn:
            row = conn.execute(text(f"SELECT score, note FROM {upsert_table} WHERE day = '2025-03-01'")).fetchone()
        assert row.score == 51  # updated
        assert row.note == "keep me"  # preserved: column was not part of the batch

    @pytest.fixture
    def sleep_probe_id(self, pg_engine):
        probe = "_test_overlap_resync_probe"
        with pg_engine.begin() as conn:
            conn.execute(text("DELETE FROM sleep WHERE id = :i"), {"i": probe})
        try:
            yield probe
        finally:
            with pg_engine.begin() as conn:
                conn.execute(text("DELETE FROM sleep WHERE id = :i"), {"i": probe})

    def test_overlap_resync_through_transform_overwrites_omitted_fields(self, pg_engine, sleep_probe_id):
        """The REAL overlap-sync path, end to end (real _transform_sleep + _upsert_batch against
        the real sleep table). Because the transform always emits the heart_rate/hrv keys (None
        when the API omits them), a re-fetch that drops those fields overwrites the previously
        stored intra-night JSONB with NULL. This documents and guards the actual behaviour - the
        API is treated as source of truth on every conflict - so the data-loss surface is explicit
        instead of hidden behind a primitive-level test that production never exercises."""
        from oura_ingest.endpoints.sleep import _transform_sleep
        from oura_ingest.ingest import _upsert_batch

        full = {
            "id": sleep_probe_id,
            "day": "1999-12-31",
            "type": "long_sleep",
            "heart_rate": {"items": [60, 61]},
            "hrv": {"items": [40]},
        }
        _upsert_batch(pg_engine, "sleep", "id", [_transform_sleep(full)])
        with pg_engine.connect() as conn:
            stored = conn.execute(text("SELECT heart_rate FROM sleep WHERE id = :i"), {"i": sleep_probe_id}).scalar()
        assert stored is not None  # intra-night HR persisted on first sync

        # Overlap re-fetch of the same session, this time with heart_rate/hrv absent from the payload.
        omitted = {"id": sleep_probe_id, "day": "1999-12-31", "type": "long_sleep"}
        _upsert_batch(pg_engine, "sleep", "id", [_transform_sleep(omitted)])
        with pg_engine.connect() as conn:
            after = conn.execute(
                text("SELECT heart_rate, hrv FROM sleep WHERE id = :i"), {"i": sleep_probe_id}
            ).fetchone()
        # Overwritten with NULL. If preserving fields across overlap sync ever becomes a required
        # invariant, this is the test that must change, together with the transform/upsert learning
        # to distinguish an absent field from an explicit NULL.
        assert after.heart_rate is None
        assert after.hrv is None
