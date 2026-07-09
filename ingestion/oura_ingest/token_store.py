from __future__ import annotations

import json
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Engine


class PostgresOAuthTokenStore:
    """Stores OAuth state encrypted by PostgreSQL pgcrypto."""

    def __init__(self, engine: Engine, encryption_key: str, provider: str = "oura"):
        if not encryption_key:
            raise ValueError("OAuth token encryption key is required")
        self.engine = engine
        self.encryption_key = encryption_key
        self.provider = provider

    def load(self) -> dict[str, Any] | None:
        with self.engine.connect() as conn:
            payload = conn.execute(
                text(
                    "SELECT pgp_sym_decrypt(encrypted_payload, :key)::text "
                    "FROM oauth_token_state WHERE provider = :provider"
                ),
                {"key": self.encryption_key, "provider": self.provider},
            ).scalar_one_or_none()
        if payload is None:
            return None
        data = json.loads(payload)
        if not isinstance(data, dict):
            raise ValueError("Persisted OAuth token state is invalid")
        return data

    def save(self, payload: dict[str, Any]) -> None:
        encoded = json.dumps(payload, separators=(",", ":"))
        with self.engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO oauth_token_state (provider, encrypted_payload, updated_at) "
                    "VALUES (:provider, pgp_sym_encrypt(:payload, :key, 'cipher-algo=aes256'), now()) "
                    "ON CONFLICT (provider) DO UPDATE SET "
                    "encrypted_payload = EXCLUDED.encrypted_payload, updated_at = now()"
                ),
                {"provider": self.provider, "payload": encoded, "key": self.encryption_key},
            )
