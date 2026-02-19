from ..endpoint import simple_endpoint


def _transform(rec: dict) -> dict:
    return {
        "day": rec["day"],
        "vo2_max": rec.get("vo2_max"),
    }


DAILY_VO2_MAX_ENDPOINT = simple_endpoint("daily_vo2_max", pk="day", transform=_transform)
