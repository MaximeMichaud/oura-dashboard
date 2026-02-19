from ..endpoint import simple_endpoint


def _transform(rec: dict) -> dict:
    c = rec.get("contributors", {})
    return {
        "day": rec["day"],
        "score": rec.get("score"),
        "active_calories": rec.get("active_calories"),
        "total_calories": rec.get("total_calories"),
        "steps": rec.get("steps"),
        "equivalent_walking_distance": rec.get("equivalent_walking_distance"),
        "low_activity_time": rec.get("low_activity_time"),
        "medium_activity_time": rec.get("medium_activity_time"),
        "high_activity_time": rec.get("high_activity_time"),
        "resting_time": rec.get("resting_time"),
        "sedentary_time": rec.get("sedentary_time"),
        "non_wear_time": rec.get("non_wear_time"),
        "average_met_minutes": rec.get("average_met_minutes"),
        "high_activity_met_minutes": rec.get("high_activity_met_minutes"),
        "medium_activity_met_minutes": rec.get("medium_activity_met_minutes"),
        "low_activity_met_minutes": rec.get("low_activity_met_minutes"),
        "sedentary_met_minutes": rec.get("sedentary_met_minutes"),
        "inactivity_alerts": rec.get("inactivity_alerts"),
        "target_calories": rec.get("target_calories"),
        "target_meters": rec.get("target_meters"),
        "meters_to_target": rec.get("meters_to_target"),
        "contributors_meet_daily_targets": c.get("meet_daily_targets"),
        "contributors_move_every_hour": c.get("move_every_hour"),
        "contributors_recovery_time": c.get("recovery_time"),
        "contributors_stay_active": c.get("stay_active"),
        "contributors_training_frequency": c.get("training_frequency"),
        "contributors_training_volume": c.get("training_volume"),
    }


DAILY_ACTIVITY_ENDPOINT = simple_endpoint("daily_activity", pk="day", transform=_transform)
