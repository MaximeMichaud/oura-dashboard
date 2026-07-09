import json

from ..endpoint import Endpoint


def _transform(rec: dict) -> dict:
    episodes = rec.get("episodes")
    return {
        "id": rec["id"],
        "start_day": rec["start_day"],
        "end_day": rec.get("end_day"),
        "start_time": rec.get("start_time"),
        "end_time": rec.get("end_time"),
        "episodes": json.dumps(episodes) if episodes else None,
    }


REST_MODE_PERIOD_ENDPOINT = Endpoint(
    name="rest_mode_period",
    api_path="rest_mode_period",
    table="rest_mode_period",
    pk="id",
    transform=_transform,
    always_full_sync=True,
)
