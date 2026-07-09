from ..endpoint import Endpoint


def _transform(rec: dict) -> dict:
    return {
        "timestamp": rec["timestamp"],
        "producer_timestamp": rec.get("producer_timestamp"),
        "timestamp_unix": rec.get("timestamp_unix"),
        "charging": rec.get("charging"),
        "in_charger": rec.get("in_charger"),
        "level": rec["level"],
    }


RING_BATTERY_LEVEL_ENDPOINT = Endpoint(
    name="ring_battery_level",
    api_path="ring_battery_level",
    table="ring_battery_level",
    pk="timestamp",
    transform=_transform,
    query_mode="datetime",
    initial_history_days=-1,
)
