"""Tests for oura_ingest.endpoint (task 26)."""

import pytest
from oura_ingest.endpoint import Endpoint, simple_endpoint


def _identity(x):
    return x


class TestEndpoint:
    def test_construction(self):
        ep = Endpoint(
            name="daily_sleep",
            api_path="daily_sleep",
            table="daily_sleep",
            pk="day",
            transform=_identity,
        )
        assert ep.name == "daily_sleep"
        assert ep.api_path == "daily_sleep"
        assert ep.table == "daily_sleep"
        assert ep.pk == "day"
        assert ep.transform is _identity

    def test_frozen_immutability(self):
        ep = Endpoint(name="test", api_path="test", table="test", pk="id", transform=_identity)
        with pytest.raises(AttributeError):
            ep.name = "changed"

    def test_transform_callable(self):
        def double_val(x):
            return {"day": x["day"], "val": x["val"] * 2}

        ep = Endpoint(name="test", api_path="test", table="test", pk="day", transform=double_val)
        result = ep.transform({"day": "2025-01-01", "val": 5})
        assert result == {"day": "2025-01-01", "val": 10}


class TestSimpleEndpoint:
    def test_factory_sets_all_fields(self):
        ep = simple_endpoint("daily_sleep", "day", _identity)
        assert ep.name == "daily_sleep"
        assert ep.api_path == "daily_sleep"
        assert ep.table == "daily_sleep"
        assert ep.pk == "day"
        assert ep.transform is _identity

    def test_factory_returns_endpoint_instance(self):
        ep = simple_endpoint("test", "id", _identity)
        assert isinstance(ep, Endpoint)

    def test_factory_different_name_pk(self):
        ep = simple_endpoint("daily_stress", "day", _identity)
        assert ep.name == "daily_stress"
        assert ep.pk == "day"
