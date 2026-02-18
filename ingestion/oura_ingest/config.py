import os
import sys


class Config:
    def __init__(self):
        self.OURA_TOKEN: str = os.environ.get("OURA_TOKEN", "")
        self.POSTGRES_HOST: str = os.environ.get("POSTGRES_HOST", "localhost")
        self.POSTGRES_PORT: str = os.environ.get("POSTGRES_PORT", "5432")
        self.POSTGRES_DB: str = os.environ.get("POSTGRES_DB", "oura")
        self.POSTGRES_USER: str = os.environ.get("POSTGRES_USER", "oura")
        self.POSTGRES_PASSWORD: str = os.environ.get("POSTGRES_PASSWORD", "oura")
        self.HISTORY_START_DATE: str = os.environ.get("HISTORY_START_DATE", "2020-01-01")
        self.SYNC_INTERVAL_MINUTES: int = int(os.environ.get("SYNC_INTERVAL_MINUTES", "30"))
        self.OVERLAP_DAYS: int = int(os.environ.get("OVERLAP_DAYS", "2"))

    def validate(self):
        if not self.OURA_TOKEN:
            print("ERROR: OURA_TOKEN environment variable is required.", file=sys.stderr)
            print("Get your token at https://cloud.ouraring.com/personal-access-tokens", file=sys.stderr)
            sys.exit(1)

    @property
    def database_url(self) -> str:
        return (
            f"postgresql://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )


cfg = Config()
