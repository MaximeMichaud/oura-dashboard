from ..endpoint import simple_endpoint


def _transform(rec: dict) -> dict:
    return {
        "day": rec["day"],
        "spo2_percentage_average": rec.get("spo2_percentage", {}).get("average")
        if rec.get("spo2_percentage")
        else None,
        "breathing_disturbance_index": rec.get("breathing_disturbance_index"),
    }


DAILY_SPO2_ENDPOINT = simple_endpoint("daily_spo2", pk="day", transform=_transform)
