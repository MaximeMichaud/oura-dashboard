import os
import sys
import time

OAUTH_REQUIRED_KEYS = (
    "OURA_CLIENT_ID",
    "OURA_CLIENT_SECRET",
    "OURA_REFRESH_TOKEN",
)

# Treat a cached access token as usable only while it has this much life left.
TOKEN_REFRESH_MARGIN_SECONDS = 300


class Config:
    def __init__(self):
        self.OURA_TOKEN: str = os.environ.get("OURA_TOKEN", "")
        self.OURA_CLIENT_ID: str = os.environ.get("OURA_CLIENT_ID", "")
        self.OURA_CLIENT_SECRET: str = os.environ.get("OURA_CLIENT_SECRET", "")
        self.OURA_REFRESH_TOKEN: str = os.environ.get("OURA_REFRESH_TOKEN", "")
        self.OURA_ACCESS_TOKEN: str = os.environ.get("OURA_ACCESS_TOKEN", "")
        self.OURA_ACCESS_TOKEN_EXPIRES_AT: str = os.environ.get("OURA_ACCESS_TOKEN_EXPIRES_AT", "")
        self.OURA_REDIRECT_URI: str = os.environ.get("OURA_REDIRECT_URI", "http://localhost:8765/callback")
        self.OURA_OAUTH_SCOPES: str = os.environ.get(
            "OURA_OAUTH_SCOPES",
            "email personal daily heartrate tag workout session spo2 ring_configuration stress heart_health",
        )
        self.POSTGRES_HOST: str = os.environ.get("POSTGRES_HOST", "localhost")
        self.POSTGRES_PORT: str = os.environ.get("POSTGRES_PORT", "5432")
        self.POSTGRES_DB: str = os.environ.get("POSTGRES_DB", "oura")
        self.POSTGRES_USER: str = os.environ.get("POSTGRES_USER", "oura")
        self.POSTGRES_PASSWORD: str = os.environ.get("POSTGRES_PASSWORD", "oura")
        self.HISTORY_START_DATE: str = os.environ.get("HISTORY_START_DATE", "2020-01-01")
        self.SYNC_INTERVAL_MINUTES: int = int(os.environ.get("SYNC_INTERVAL_MINUTES", "30"))
        self.OVERLAP_DAYS: int = int(os.environ.get("OVERLAP_DAYS", "2"))

    @property
    def has_legacy_token(self) -> bool:
        return bool(self.OURA_TOKEN)

    @property
    def has_oauth_refresh(self) -> bool:
        return all(getattr(self, key) for key in OAUTH_REQUIRED_KEYS)

    @property
    def has_valid_access_token(self) -> bool:
        """True when a cached OAuth access token exists and is not near expiry."""
        if not self.OURA_ACCESS_TOKEN:
            return False
        try:
            expires_at = int(self.OURA_ACCESS_TOKEN_EXPIRES_AT)
        except (TypeError, ValueError):
            return False
        return expires_at > int(time.time()) + TOKEN_REFRESH_MARGIN_SECONDS

    def validate(self):
        if not self.has_legacy_token and not self.has_oauth_refresh and not self.has_valid_access_token:
            print("ERROR: Oura authentication is not configured.", file=sys.stderr)
            print("Set legacy OURA_TOKEN or run: python -m oura_ingest.cli --oauth-setup", file=sys.stderr)
            sys.exit(1)

    @property
    def database_url(self) -> str:
        return (
            f"postgresql://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )


cfg = Config()
