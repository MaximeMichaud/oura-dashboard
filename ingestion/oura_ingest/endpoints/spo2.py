def _transform(rec: dict) -> dict:
    return {
        "day": rec["day"],
        "spo2_percentage_average": rec.get("spo2_percentage", {}).get("average")
        if rec.get("spo2_percentage")
        else None,
        "breathing_disturbance_index": rec.get("breathing_disturbance_index"),
    }


DAILY_SPO2_ENDPOINT = {
    "name": "daily_spo2",
    "api_path": "daily_spo2",
    "table": "daily_spo2",
    "pk": "day",
    "transform": _transform,
}
