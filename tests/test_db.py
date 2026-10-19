"""Tests for oura_ingest.db (task 24)."""

from unittest.mock import MagicMock, Mock, patch

import pytest


class TestInstalledPostgresDriver:
    def test_ingestion_engine_loads_installed_driver(self):
        from oura_ingest.config import Config
        from sqlalchemy import create_engine

        engine = create_engine(Config().database_url)
        try:
            assert engine.dialect.dbapi.__name__ == "psycopg2"
        finally:
            engine.dispose()

    def test_streamlit_engine_loads_installed_driver(self):
        from components.db import get_engine

        get_engine.clear()
        engine = get_engine()
        try:
            assert engine.dialect.dbapi.__name__ == "psycopg2"
        finally:
            engine.dispose()
            get_engine.clear()


class TestWaitForDb:
    def test_immediate_success(self):
        """Database available on first try."""
        mock_engine = MagicMock()
        mock_conn = MagicMock()
        mock_engine.connect.return_value.__enter__ = Mock(return_value=mock_conn)
        mock_engine.connect.return_value.__exit__ = Mock(return_value=False)

        with patch("oura_ingest.db.create_engine", return_value=mock_engine):
            from oura_ingest.db import wait_for_db

            result = wait_for_db(retries=3, delay=0)
            assert result is mock_engine
            assert mock_engine.connect.call_count == 1

    def test_success_after_retries(self):
        """Database becomes available after 2 failures."""
        mock_engine = MagicMock()

        # First 2 calls raise, third succeeds
        mock_conn = MagicMock()
        good_ctx = MagicMock()
        good_ctx.__enter__ = Mock(return_value=mock_conn)
        good_ctx.__exit__ = Mock(return_value=False)

        mock_engine.connect.side_effect = [
            Exception("not ready"),
            Exception("still not ready"),
            good_ctx,
        ]

        with (
            patch("oura_ingest.db.create_engine", return_value=mock_engine),
            patch("oura_ingest.db.time.sleep"),
        ):
            from oura_ingest.db import wait_for_db

            result = wait_for_db(retries=3, delay=0)
            assert result is mock_engine
            assert mock_engine.connect.call_count == 3

    def test_exhausted_retries(self):
        """RuntimeError raised after all retries fail."""
        mock_engine = MagicMock()
        mock_engine.connect.side_effect = Exception("db down")

        with (
            patch("oura_ingest.db.create_engine", return_value=mock_engine),
            patch("oura_ingest.db.time.sleep"),
            pytest.raises(RuntimeError, match="not available"),
        ):
            from oura_ingest.db import wait_for_db

            wait_for_db(retries=3, delay=0)
