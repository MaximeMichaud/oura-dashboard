from ..endpoint import simple_endpoint


def _transform(rec: dict) -> dict:
    return {
        "day": rec["day"],
        "stress_high": rec.get("stress_high"),
        "recovery_high": rec.get("recovery_high"),
        "day_summary": rec.get("day_summary"),
    }


DAILY_STRESS_ENDPOINT = simple_endpoint("daily_stress", pk="day", transform=_transform)
