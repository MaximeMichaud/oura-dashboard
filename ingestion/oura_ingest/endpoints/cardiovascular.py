def _transform(rec: dict) -> dict:
    return {
        "day": rec["day"],
        "vascular_age": rec.get("vascular_age"),
    }


DAILY_CARDIOVASCULAR_AGE_ENDPOINT = {
    "name": "daily_cardiovascular_age",
    "api_path": "daily_cardiovascular_age",
    "table": "daily_cardiovascular_age",
    "pk": "day",
    "transform": _transform,
}
