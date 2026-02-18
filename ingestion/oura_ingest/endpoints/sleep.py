import json


def _transform_sleep(rec: dict) -> dict:
    hr = rec.get("heart_rate") or {}
    hrv = rec.get("hrv") or {}
    return {
        "id": rec["id"],
        "day": rec.get("day"),
        "bedtime_start": rec.get("bedtime_start"),
        "bedtime_end": rec.get("bedtime_end"),
        "duration": rec.get("time_in_bed"),
        "total_sleep": rec.get("total_sleep_duration"),
        "awake_time": rec.get("awake_time"),
        "light_sleep": rec.get("light_sleep_duration"),
        "deep_sleep": rec.get("deep_sleep_duration"),
        "rem_sleep": rec.get("rem_sleep_duration"),
        "restless_periods": rec.get("restless_periods"),
        "efficiency": rec.get("efficiency"),
        "latency": rec.get("latency"),
        "type": rec.get("type"),
        "readiness_score_delta": rec.get("readiness_score_delta"),
        "average_breath": rec.get("average_breath"),
        "average_heart_rate": rec.get("average_heart_rate"),
        "average_hrv": rec.get("average_hrv"),
        "lowest_heart_rate": rec.get("lowest_heart_rate"),
        "heart_rate": json.dumps(hr) if hr else None,
        "hrv": json.dumps(hrv) if hrv else None,
        "sleep_phase_5_min": rec.get("sleep_phase_5_min"),
        "movement_30_sec": rec.get("movement_30_sec"),
        "sleep_score_delta": rec.get("sleep_score_delta"),
        "period": rec.get("period"),
        "low_battery_alert": rec.get("low_battery_alert"),
    }


def _transform_daily_sleep(rec: dict) -> dict:
    c = rec.get("contributors", {})
    return {
        "day": rec["day"],
        "score": rec.get("score"),
        "contributors_deep_sleep": c.get("deep_sleep"),
        "contributors_efficiency": c.get("efficiency"),
        "contributors_latency": c.get("latency"),
        "contributors_rem_sleep": c.get("rem_sleep"),
        "contributors_restfulness": c.get("restfulness"),
        "contributors_timing": c.get("timing"),
        "contributors_total_sleep": c.get("total_sleep"),
    }


SLEEP_ENDPOINT = {
    "name": "sleep",
    "api_path": "sleep",
    "table": "sleep",
    "pk": "id",
    "transform": _transform_sleep,
}

DAILY_SLEEP_ENDPOINT = {
    "name": "daily_sleep",
    "api_path": "daily_sleep",
    "table": "daily_sleep",
    "pk": "day",
    "transform": _transform_daily_sleep,
}
