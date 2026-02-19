from ..endpoint import simple_endpoint


def _transform(rec: dict) -> dict:
    c = rec.get("contributors", {})
    return {
        "day": rec["day"],
        "score": rec.get("score"),
        "temperature_deviation": rec.get("temperature_deviation"),
        "temperature_trend_deviation": rec.get("temperature_trend_deviation"),
        "contributors_activity_balance": c.get("activity_balance"),
        "contributors_body_temperature": c.get("body_temperature"),
        "contributors_hrv_balance": c.get("hrv_balance"),
        "contributors_previous_day_activity": c.get("previous_day_activity"),
        "contributors_previous_night": c.get("previous_night"),
        "contributors_recovery_index": c.get("recovery_index"),
        "contributors_resting_heart_rate": c.get("resting_heart_rate"),
        "contributors_sleep_balance": c.get("sleep_balance"),
        "contributors_sleep_regularity": c.get("sleep_regularity"),
    }


DAILY_READINESS_ENDPOINT = simple_endpoint("daily_readiness", pk="day", transform=_transform)
