def _transform(rec: dict) -> dict:
    c = rec.get("contributors", {})
    return {
        "day": rec["day"],
        "level": rec.get("level"),
        "contributors_sleep_recovery": c.get("sleep_recovery"),
        "contributors_daytime_recovery": c.get("daytime_recovery"),
        "contributors_stress": c.get("stress"),
    }


DAILY_RESILIENCE_ENDPOINT = {
    "name": "daily_resilience",
    "api_path": "daily_resilience",
    "table": "daily_resilience",
    "pk": "day",
    "transform": _transform,
}
