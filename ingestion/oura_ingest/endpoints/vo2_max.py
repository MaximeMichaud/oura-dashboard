from ..endpoint import Endpoint


def _transform(rec: dict) -> dict:
    return {
        "day": rec["day"],
        "vo2_max": rec.get("vo2_max"),
    }


DAILY_VO2_MAX_ENDPOINT = Endpoint(
    name="daily_vo2_max",
    api_path="vO2_max",
    table="daily_vo2_max",
    pk="day",
    transform=_transform,
)
