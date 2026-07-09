import json

from oura_ingest.endpoints.activity import _transform as transform_activity
from oura_ingest.endpoints.cardiovascular import _transform as transform_cardiovascular
from oura_ingest.endpoints.enhanced_tag import _transform as transform_enhanced_tag
from oura_ingest.endpoints.heartrate import _transform as transform_heartrate
from oura_ingest.endpoints.personal_info import _transform as transform_personal_info
from oura_ingest.endpoints.readiness import _transform as transform_readiness
from oura_ingest.endpoints.resilience import _transform as transform_resilience
from oura_ingest.endpoints.rest_mode_period import _transform as transform_rest_mode_period
from oura_ingest.endpoints.ring_battery_level import _transform as transform_ring_battery
from oura_ingest.endpoints.ring_configuration import _transform as transform_ring_configuration
from oura_ingest.endpoints.session import _transform as transform_session
from oura_ingest.endpoints.sleep import _transform_daily_sleep, _transform_sleep
from oura_ingest.endpoints.sleep_time import _transform as transform_sleep_time
from oura_ingest.endpoints.spo2 import _transform as transform_spo2
from oura_ingest.endpoints.stress import _transform as transform_stress
from oura_ingest.endpoints.tag import _transform as transform_tag
from oura_ingest.endpoints.vo2_max import _transform as transform_vo2_max
from oura_ingest.endpoints.workout import _transform as transform_workout


class TestSleepTransform:
    def test_full_record(self):
        rec = {
            "id": "abc-123",
            "day": "2025-01-15",
            "bedtime_start": "2025-01-15T23:30:00+02:00",
            "bedtime_end": "2025-01-16T07:15:00+02:00",
            "time_in_bed": 27900,
            "total_sleep_duration": 25200,
            "awake_time": 2700,
            "light_sleep_duration": 10800,
            "deep_sleep_duration": 7200,
            "rem_sleep_duration": 7200,
            "restless_periods": 12,
            "efficiency": 90,
            "latency": 300,
            "type": "long_sleep",
            "readiness_score_delta": 5,
            "average_breath": 15.2,
            "average_heart_rate": 52.3,
            "average_hrv": 45.7,
            "lowest_heart_rate": 48,
            "heart_rate": {"interval": 300, "items": [52, 51, 50]},
            "hrv": {"interval": 300, "items": [45, 48, 42]},
            "sleep_phase_5_min": "4433322211",
            "movement_30_sec": "1112111211",
            "sleep_score_delta": 2.5,
            "period": 0,
            "low_battery_alert": False,
        }
        result = _transform_sleep(rec)
        assert result["id"] == "abc-123"
        assert result["day"] == "2025-01-15"
        assert result["duration"] == 27900
        assert result["total_sleep"] == 25200
        assert result["deep_sleep"] == 7200
        assert result["rem_sleep"] == 7200
        assert result["efficiency"] == 90
        assert result["type"] == "long_sleep"
        assert result["lowest_heart_rate"] == 48
        assert json.loads(result["heart_rate"]) == {"interval": 300, "items": [52, 51, 50]}
        assert json.loads(result["hrv"]) == {"interval": 300, "items": [45, 48, 42]}
        assert result["sleep_phase_5_min"] == "4433322211"
        assert result["low_battery_alert"] is False

    def test_minimal_record(self):
        rec = {"id": "min-1", "day": "2025-01-15"}
        result = _transform_sleep(rec)
        assert result["id"] == "min-1"
        assert result["day"] == "2025-01-15"
        assert result["heart_rate"] is None
        assert result["hrv"] is None
        assert result["total_sleep"] is None

    def test_empty_hr_hrv(self):
        rec = {"id": "empty-hr", "heart_rate": {}, "hrv": {}}
        result = _transform_sleep(rec)
        assert result["heart_rate"] is None
        assert result["hrv"] is None


class TestDailySleepTransform:
    def test_full_record(self):
        rec = {
            "day": "2025-01-15",
            "score": 85,
            "contributors": {
                "deep_sleep": 80,
                "efficiency": 90,
                "latency": 95,
                "rem_sleep": 75,
                "restfulness": 88,
                "timing": 70,
                "total_sleep": 82,
            },
        }
        result = _transform_daily_sleep(rec)
        assert result["day"] == "2025-01-15"
        assert result["score"] == 85
        assert result["contributors_deep_sleep"] == 80
        assert result["contributors_timing"] == 70

    def test_missing_contributors(self):
        rec = {"day": "2025-01-15", "score": 72}
        result = _transform_daily_sleep(rec)
        assert result["day"] == "2025-01-15"
        assert result["contributors_deep_sleep"] is None


class TestReadinessTransform:
    def test_full_record(self):
        rec = {
            "day": "2025-01-15",
            "score": 88,
            "temperature_deviation": 0.12,
            "temperature_trend_deviation": -0.05,
            "contributors": {
                "activity_balance": 85,
                "body_temperature": 90,
                "hrv_balance": 82,
                "previous_day_activity": 78,
                "previous_night": 92,
                "recovery_index": 88,
                "resting_heart_rate": 95,
                "sleep_balance": 80,
                "sleep_regularity": 75,
            },
        }
        result = transform_readiness(rec)
        assert result["day"] == "2025-01-15"
        assert result["score"] == 88
        assert result["temperature_deviation"] == 0.12
        assert result["contributors_hrv_balance"] == 82
        assert result["contributors_sleep_regularity"] == 75

    def test_no_contributors(self):
        rec = {"day": "2025-01-15"}
        result = transform_readiness(rec)
        assert result["contributors_activity_balance"] is None


class TestActivityTransform:
    def test_full_record(self):
        rec = {
            "day": "2025-01-15",
            "score": 92,
            "active_calories": 450,
            "total_calories": 2200,
            "steps": 12500,
            "equivalent_walking_distance": 9800,
            "low_activity_time": 3600,
            "medium_activity_time": 1800,
            "high_activity_time": 900,
            "resting_time": 28800,
            "sedentary_time": 36000,
            "non_wear_time": 7200,
            "average_met_minutes": 1.8,
            "high_activity_met_minutes": 200,
            "medium_activity_met_minutes": 150,
            "low_activity_met_minutes": 100,
            "sedentary_met_minutes": 50,
            "inactivity_alerts": 3,
            "target_calories": 500,
            "target_meters": 10000,
            "meters_to_target": 200,
            "contributors": {
                "meet_daily_targets": 90,
                "move_every_hour": 85,
                "recovery_time": 95,
                "stay_active": 88,
                "training_frequency": 80,
                "training_volume": 75,
            },
        }
        result = transform_activity(rec)
        assert result["steps"] == 12500
        assert result["active_calories"] == 450
        assert result["contributors_training_volume"] == 75
        assert len(result) == 27


class TestSpo2Transform:
    def test_full_record(self):
        rec = {
            "day": "2025-01-15",
            "spo2_percentage": {"average": 97.5},
            "breathing_disturbance_index": 1.2,
        }
        result = transform_spo2(rec)
        assert result["day"] == "2025-01-15"
        assert result["spo2_percentage_average"] == 97.5
        assert result["breathing_disturbance_index"] == 1.2

    def test_null_spo2(self):
        rec = {"day": "2025-01-15", "spo2_percentage": None}
        result = transform_spo2(rec)
        assert result["spo2_percentage_average"] is None

    def test_missing_spo2(self):
        rec = {"day": "2025-01-15"}
        result = transform_spo2(rec)
        assert result["spo2_percentage_average"] is None


class TestStressTransform:
    def test_full_record(self):
        rec = {
            "day": "2025-01-15",
            "stress_high": 3600,
            "recovery_high": 7200,
            "day_summary": "restored",
        }
        result = transform_stress(rec)
        assert result["day"] == "2025-01-15"
        assert result["stress_high"] == 3600
        assert result["recovery_high"] == 7200
        assert result["day_summary"] == "restored"


class TestResilienceTransform:
    def test_full_record(self):
        rec = {
            "day": "2025-01-15",
            "level": "solid",
            "contributors": {
                "sleep_recovery": 85.5,
                "daytime_recovery": 72.3,
                "stress": 90.1,
            },
        }
        result = transform_resilience(rec)
        assert result["day"] == "2025-01-15"
        assert result["level"] == "solid"
        assert result["contributors_sleep_recovery"] == 85.5
        assert result["contributors_stress"] == 90.1


class TestCardiovascularTransform:
    def test_full_record(self):
        rec = {"day": "2025-01-15", "vascular_age": 32}
        result = transform_cardiovascular(rec)
        assert result["day"] == "2025-01-15"
        assert result["vascular_age"] == 32

    def test_null_age(self):
        rec = {"day": "2025-01-15"}
        result = transform_cardiovascular(rec)
        assert result["vascular_age"] is None


class TestVo2MaxTransform:
    def test_full_record(self):
        rec = {"day": "2025-01-15", "vo2_max": 42.5}
        result = transform_vo2_max(rec)
        assert result["day"] == "2025-01-15"
        assert result["vo2_max"] == 42.5

    def test_null_vo2(self):
        rec = {"day": "2025-01-15"}
        result = transform_vo2_max(rec)
        assert result["vo2_max"] is None


class TestWorkoutTransform:
    def test_full_record(self):
        rec = {
            "id": "wk-456",
            "day": "2025-01-15",
            "activity": "running",
            "calories": 350.5,
            "distance": 5200.0,
            "start_datetime": "2025-01-15T07:00:00+02:00",
            "end_datetime": "2025-01-15T07:45:00+02:00",
            "intensity": "moderate",
            "label": "Morning run",
            "source": "autodetected",
        }
        result = transform_workout(rec)
        assert result["id"] == "wk-456"
        assert result["activity"] == "running"
        assert result["calories"] == 350.5
        assert result["intensity"] == "moderate"

    def test_minimal(self):
        rec = {"id": "wk-min", "day": "2025-01-15"}
        result = transform_workout(rec)
        assert result["id"] == "wk-min"
        assert result["calories"] is None


class TestSleepTimeTransform:
    def test_full_record(self):
        rec = {
            "id": "st-789",
            "day": "2025-01-15",
            "optimal_bedtime": {
                "start_offset": -3600,
                "end_offset": -1800,
                "day_tz": 7200,
            },
            "recommendation": "earlier_bedtime",
            "status": "optimal_found",
        }
        result = transform_sleep_time(rec)
        assert result["id"] == "st-789"
        assert result["optimal_bedtime_start"] == -3600
        assert result["optimal_bedtime_end"] == -1800
        assert result["optimal_bedtime_tz"] == 7200
        assert result["recommendation"] == "earlier_bedtime"
        assert result["status"] == "optimal_found"

    def test_no_optimal_bedtime(self):
        rec = {"id": "st-none", "day": "2025-01-15", "optimal_bedtime": None}
        result = transform_sleep_time(rec)
        assert result["optimal_bedtime_start"] is None
        assert result["optimal_bedtime_end"] is None


class TestExtendedApiTransforms:
    def test_heartrate_supports_live_and_documented_timestamps(self):
        result = transform_heartrate(
            {
                "timestamp": "2026-07-09T12:00:00Z",
                "producer_timestamp": 1783598402000,
                "timestamp_unix": 1783598400000,
                "bpm": 74,
                "source": "awake",
            }
        )
        assert result["bpm"] == 74
        assert result["producer_timestamp"] == 1783598402000
        assert result["timestamp_unix"] == 1783598400000

    def test_ring_battery(self):
        result = transform_ring_battery(
            {"timestamp": "2026-07-09T12:00:00Z", "level": 81, "charging": False, "in_charger": False}
        )
        assert result["level"] == 81
        assert result["timestamp_unix"] is None

    def test_ring_configuration_gen4(self):
        result = transform_ring_configuration(
            {"id": "ring", "hardware_type": "gen4", "firmware_version": "3.2.1", "size": 10}
        )
        assert result["hardware_type"] == "gen4"
        assert result["size"] == 10

    def test_session_serializes_samples(self):
        result = transform_session(
            {
                "id": "session",
                "day": "2026-07-09",
                "type": "meditation",
                "heart_rate": {"interval": 5, "items": [60, 61]},
            }
        )
        assert json.loads(result["heart_rate"])["items"] == [60, 61]
        assert result["heart_rate_variability"] is None

    def test_tag_serializes_tags(self):
        result = transform_tag(
            {"id": "tag", "day": "2026-07-09", "timestamp": "2026-07-09T09:00:00", "tags": ["caffeine"]}
        )
        assert json.loads(result["tags"]) == ["caffeine"]

    def test_enhanced_tag(self):
        result = transform_enhanced_tag({"id": "tag2", "start_day": "2026-07-09", "tag_type_code": "custom"})
        assert result["tag_type_code"] == "custom"

    def test_rest_mode_serializes_episodes(self):
        result = transform_rest_mode_period({"id": "rest", "start_day": "2026-07-01", "episodes": [{"tags": ["sick"]}]})
        assert json.loads(result["episodes"])[0]["tags"] == ["sick"]

    def test_personal_info_omits_email(self):
        result = transform_personal_info(
            {
                "id": "user",
                "age": 35,
                "weight": 75,
                "height": 1.78,
                "biological_sex": "male",
                "email": "private@example.com",
            }
        )
        assert result["age"] == 35
        assert "email" not in result
