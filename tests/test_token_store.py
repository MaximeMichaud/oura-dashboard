import json
from contextlib import nullcontext

import pytest
from oura_ingest.token_store import PostgresOAuthTokenStore


class _Result:
    def __init__(self, scalar):
        self.scalar = scalar

    def scalar_one_or_none(self):
        return self.scalar


class _Connection:
    def __init__(self, scalar=None):
        self.scalar = scalar
        self.executions = []

    def execute(self, statement, parameters):
        self.executions.append((str(statement), parameters))
        return _Result(self.scalar)


class _Engine:
    def __init__(self, scalar=None):
        self.connection = _Connection(scalar)
        self.connect_calls = 0
        self.begin_calls = 0

    def connect(self):
        self.connect_calls += 1
        return nullcontext(self.connection)

    def begin(self):
        self.begin_calls += 1
        return nullcontext(self.connection)


@pytest.mark.parametrize("encryption_key", ["", None])
def test_token_store_requires_encryption_key(encryption_key):
    with pytest.raises(ValueError, match="encryption key is required"):
        PostgresOAuthTokenStore(_Engine(), encryption_key)


def test_load_returns_none_when_provider_has_no_state():
    engine = _Engine()
    store = PostgresOAuthTokenStore(engine, "encryption-key", provider="test-provider")

    assert store.load() is None
    assert engine.connect_calls == 1
    assert engine.begin_calls == 0
    statement, parameters = engine.connection.executions[0]
    assert "pgp_sym_decrypt(encrypted_payload, :key)" in statement
    assert "WHERE provider = :provider" in statement
    assert parameters == {"key": "encryption-key", "provider": "test-provider"}


def test_load_returns_decrypted_object_state():
    state = {
        "access_token": "access-token",
        "refresh_token": "refresh-token",
        "expires_at": 1_700_000_000,
        "scope": "daily workout",
    }
    engine = _Engine(json.dumps(state))

    assert PostgresOAuthTokenStore(engine, "encryption-key").load() == state


@pytest.mark.parametrize("persisted_value", ["[]", '"access-token"', "null"])
def test_load_rejects_json_that_is_not_an_object(persisted_value):
    store = PostgresOAuthTokenStore(_Engine(persisted_value), "encryption-key")

    with pytest.raises(ValueError, match="token state is invalid"):
        store.load()


def test_load_surfaces_corrupted_json():
    store = PostgresOAuthTokenStore(_Engine("not-json"), "encryption-key")

    with pytest.raises(json.JSONDecodeError):
        store.load()


def test_save_upserts_parameterized_encrypted_state_in_a_transaction():
    engine = _Engine()
    store = PostgresOAuthTokenStore(engine, "encryption-key", provider="test-provider")
    state = {
        "access_token": "access-token",
        "refresh_token": "refresh-token",
        "expires_at": 1_700_000_000,
        "scope": None,
    }

    store.save(state)

    assert engine.connect_calls == 0
    assert engine.begin_calls == 1
    statement, parameters = engine.connection.executions[0]
    assert "pgp_sym_encrypt(:payload, :key, 'cipher-algo=aes256')" in statement
    assert "ON CONFLICT (provider) DO UPDATE" in statement
    assert parameters == {
        "provider": "test-provider",
        "payload": json.dumps(state, separators=(",", ":")),
        "key": "encryption-key",
    }
