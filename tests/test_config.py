import os

import pytest


class TestConfigDefaults:
    def test_defaults(self):
        env_backup = os.environ.copy()
        for key in [
            "OURA_TOKEN",
            "POSTGRES_HOST",
            "POSTGRES_PORT",
            "POSTGRES_DB",
            "POSTGRES_USER",
            "POSTGRES_PASSWORD",
            "HISTORY_START_DATE",
            "SYNC_INTERVAL_MINUTES",
            "OVERLAP_DAYS",
        ]:
            os.environ.pop(key, None)

        try:
            from oura_ingest.config import Config

            cfg = Config()
            assert cfg.OURA_TOKEN == ""
            assert cfg.POSTGRES_HOST == "localhost"
            assert cfg.POSTGRES_PORT == "5432"
            assert cfg.POSTGRES_DB == "oura"
            assert cfg.POSTGRES_USER == "oura"
            assert cfg.POSTGRES_PASSWORD == "oura"
            assert cfg.HISTORY_START_DATE == "2020-01-01"
            assert cfg.SYNC_INTERVAL_MINUTES == 30
            assert cfg.OVERLAP_DAYS == 2
        finally:
            os.environ.clear()
            os.environ.update(env_backup)

    def test_custom_values(self):
        env_backup = os.environ.copy()
        os.environ["OURA_TOKEN"] = "test-token-123"
        os.environ["POSTGRES_HOST"] = "db.example.com"
        os.environ["POSTGRES_PORT"] = "5433"
        os.environ["POSTGRES_DB"] = "mydb"
        os.environ["POSTGRES_USER"] = "myuser"
        os.environ["POSTGRES_PASSWORD"] = "mypass"
        os.environ["SYNC_INTERVAL_MINUTES"] = "60"
        os.environ["OVERLAP_DAYS"] = "5"

        try:
            from oura_ingest.config import Config

            cfg = Config()
            assert cfg.OURA_TOKEN == "test-token-123"
            assert cfg.POSTGRES_HOST == "db.example.com"
            assert cfg.POSTGRES_PORT == "5433"
            assert cfg.SYNC_INTERVAL_MINUTES == 60
            assert cfg.OVERLAP_DAYS == 5
        finally:
            os.environ.clear()
            os.environ.update(env_backup)


class TestDatabaseUrl:
    def test_database_url(self):
        env_backup = os.environ.copy()
        os.environ["POSTGRES_HOST"] = "myhost"
        os.environ["POSTGRES_PORT"] = "5433"
        os.environ["POSTGRES_DB"] = "mydb"
        os.environ["POSTGRES_USER"] = "myuser"
        os.environ["POSTGRES_PASSWORD"] = "mypass"

        try:
            from oura_ingest.config import Config

            cfg = Config()
            assert cfg.database_url == "postgresql://myuser:mypass@myhost:5433/mydb"
        finally:
            os.environ.clear()
            os.environ.update(env_backup)


class TestValidate:
    def test_missing_token_exits(self):
        env_backup = os.environ.copy()
        os.environ.pop("OURA_TOKEN", None)

        try:
            from oura_ingest.config import Config

            cfg = Config()
            with pytest.raises(SystemExit):
                cfg.validate()
        finally:
            os.environ.clear()
            os.environ.update(env_backup)

    def test_valid_token_passes(self):
        env_backup = os.environ.copy()
        os.environ["OURA_TOKEN"] = "valid-token"

        try:
            from oura_ingest.config import Config

            cfg = Config()
            cfg.validate()  # should not raise
        finally:
            os.environ.clear()
            os.environ.update(env_backup)
