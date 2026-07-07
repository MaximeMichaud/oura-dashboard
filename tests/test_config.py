import os
import time

import pytest

OAUTH_KEYS = [
    "OURA_CLIENT_ID",
    "OURA_CLIENT_SECRET",
    "OURA_REFRESH_TOKEN",
    "OURA_ACCESS_TOKEN",
    "OURA_ACCESS_TOKEN_EXPIRES_AT",
    "OURA_REDIRECT_URI",
    "OURA_OAUTH_SCOPES",
]


class TestConfigDefaults:
    def test_defaults(self):
        env_backup = os.environ.copy()
        for key in [
            "OURA_TOKEN",
            *OAUTH_KEYS,
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
            assert cfg.OURA_CLIENT_ID == ""
            assert cfg.OURA_CLIENT_SECRET == ""
            assert cfg.OURA_REFRESH_TOKEN == ""
            assert cfg.OURA_ACCESS_TOKEN == ""
            assert cfg.OURA_ACCESS_TOKEN_EXPIRES_AT == ""
            assert cfg.OURA_REDIRECT_URI == "http://localhost:8765/callback"
            assert "daily" in cfg.OURA_OAUTH_SCOPES
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
        os.environ["OURA_CLIENT_ID"] = "client-id"
        os.environ["OURA_CLIENT_SECRET"] = "client-secret"
        os.environ["OURA_REFRESH_TOKEN"] = "refresh-token"
        os.environ["OURA_ACCESS_TOKEN"] = "access-token"
        os.environ["OURA_ACCESS_TOKEN_EXPIRES_AT"] = "12345"
        os.environ["OURA_REDIRECT_URI"] = "http://localhost:9999/callback"
        os.environ["OURA_OAUTH_SCOPES"] = "daily workout"
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
            assert cfg.OURA_CLIENT_ID == "client-id"
            assert cfg.OURA_CLIENT_SECRET == "client-secret"
            assert cfg.OURA_REFRESH_TOKEN == "refresh-token"
            assert cfg.OURA_ACCESS_TOKEN == "access-token"
            assert cfg.OURA_ACCESS_TOKEN_EXPIRES_AT == "12345"
            assert cfg.OURA_REDIRECT_URI == "http://localhost:9999/callback"
            assert cfg.OURA_OAUTH_SCOPES == "daily workout"
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
        for key in OAUTH_KEYS:
            os.environ.pop(key, None)

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

    def test_valid_oauth_passes(self):
        env_backup = os.environ.copy()
        os.environ.pop("OURA_TOKEN", None)
        os.environ["OURA_CLIENT_ID"] = "client-id"
        os.environ["OURA_CLIENT_SECRET"] = "client-secret"
        os.environ["OURA_REFRESH_TOKEN"] = "refresh-token"

        try:
            from oura_ingest.config import Config

            cfg = Config()
            cfg.validate()  # should not raise
        finally:
            os.environ.clear()
            os.environ.update(env_backup)

    def test_valid_access_token_only_passes(self):
        env_backup = os.environ.copy()
        os.environ.pop("OURA_TOKEN", None)
        for key in OAUTH_KEYS:
            os.environ.pop(key, None)
        os.environ["OURA_ACCESS_TOKEN"] = "cached-access"
        os.environ["OURA_ACCESS_TOKEN_EXPIRES_AT"] = str(int(time.time()) + 3600)

        try:
            from oura_ingest.config import Config

            cfg = Config()
            assert cfg.has_valid_access_token is True
            cfg.validate()  # a still-valid cached access token is enough
        finally:
            os.environ.clear()
            os.environ.update(env_backup)

    def test_expired_access_token_alone_is_not_valid(self):
        env_backup = os.environ.copy()
        os.environ.pop("OURA_TOKEN", None)
        for key in OAUTH_KEYS:
            os.environ.pop(key, None)
        os.environ["OURA_ACCESS_TOKEN"] = "cached-access"
        os.environ["OURA_ACCESS_TOKEN_EXPIRES_AT"] = "1"

        try:
            from oura_ingest.config import Config

            cfg = Config()
            assert cfg.has_valid_access_token is False
            with pytest.raises(SystemExit):
                cfg.validate()
        finally:
            os.environ.clear()
            os.environ.update(env_backup)
