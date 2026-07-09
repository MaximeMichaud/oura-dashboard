import json

from ..endpoint import simple_endpoint


def _json(value):
    return json.dumps(value) if value else None


def _transform(rec: dict) -> dict:
    return {
        "id": rec["id"],
        "day": rec["day"],
        "start_datetime": rec.get("start_datetime"),
        "end_datetime": rec.get("end_datetime"),
        "type": rec.get("type"),
        "mood": rec.get("mood"),
        "heart_rate": _json(rec.get("heart_rate")),
        "heart_rate_variability": _json(rec.get("heart_rate_variability")),
        "motion_count": _json(rec.get("motion_count")),
    }


SESSION_ENDPOINT = simple_endpoint("session", pk="id", transform=_transform)
