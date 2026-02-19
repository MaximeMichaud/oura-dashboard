from ..endpoint import simple_endpoint


def _transform(rec: dict) -> dict:
    return {
        "id": rec["id"],
        "day": rec.get("day"),
        "activity": rec.get("activity"),
        "calories": rec.get("calories"),
        "distance": rec.get("distance"),
        "start_datetime": rec.get("start_datetime"),
        "end_datetime": rec.get("end_datetime"),
        "intensity": rec.get("intensity"),
        "label": rec.get("label"),
        "source": rec.get("source"),
    }


WORKOUT_ENDPOINT = simple_endpoint("workout", pk="id", transform=_transform)
