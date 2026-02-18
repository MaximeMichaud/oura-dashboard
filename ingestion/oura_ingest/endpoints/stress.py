def _transform(rec: dict) -> dict:
    return {
        "day": rec["day"],
        "stress_high": rec.get("stress_high"),
        "recovery_high": rec.get("recovery_high"),
        "day_summary": rec.get("day_summary"),
    }


DAILY_STRESS_ENDPOINT = {
    "name": "daily_stress",
    "api_path": "daily_stress",
    "table": "daily_stress",
    "pk": "day",
    "transform": _transform,
}
