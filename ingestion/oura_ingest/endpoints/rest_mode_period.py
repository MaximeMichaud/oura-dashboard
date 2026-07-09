import json

from ..endpoint import simple_endpoint


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


REST_MODE_PERIOD_ENDPOINT = simple_endpoint("rest_mode_period", pk="id", transform=_transform)
