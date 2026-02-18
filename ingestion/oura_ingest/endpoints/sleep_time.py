def _transform(rec: dict) -> dict:
    ob = rec.get("optimal_bedtime") or {}
    return {
        "id": rec["id"],
        "day": rec.get("day"),
        "optimal_bedtime_start": ob.get("start_offset"),
        "optimal_bedtime_end": ob.get("end_offset"),
        "optimal_bedtime_tz": ob.get("day_tz"),
        "recommendation": rec.get("recommendation"),
        "status": rec.get("status"),
    }


SLEEP_TIME_ENDPOINT = {
    "name": "sleep_time",
    "api_path": "sleep_time",
    "table": "sleep_time",
    "pk": "id",
    "transform": _transform,
}
