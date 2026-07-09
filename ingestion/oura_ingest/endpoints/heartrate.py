from ..endpoint import Endpoint


def _transform(rec: dict) -> dict:
    return {
        "timestamp": rec["timestamp"],
        "producer_timestamp": rec.get("producer_timestamp"),
        "timestamp_unix": rec.get("timestamp_unix"),
        "bpm": rec["bpm"],
        "source": rec["source"],
    }


HEARTRATE_ENDPOINT = Endpoint(
    name="heartrate",
    api_path="heartrate",
    table="heartrate",
    pk="timestamp",
    transform=_transform,
    query_mode="datetime",
    initial_history_days=-1,
)
