from ..endpoint import simple_endpoint


def _transform(rec: dict) -> dict:
    return {
        "day": rec["day"],
        "vascular_age": rec.get("vascular_age"),
    }


DAILY_CARDIOVASCULAR_AGE_ENDPOINT = simple_endpoint("daily_cardiovascular_age", pk="day", transform=_transform)
