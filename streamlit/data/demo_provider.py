"""Demo data provider - generates realistic synthetic Oura data."""
from __future__ import annotations

import math
import random
from datetime import date, timedelta

import pandas as pd
import streamlit as st


class DemoProvider:
    """Generates 90 days of realistic synthetic Oura data."""

    def __init__(self):
        self._seed = 42
        self._days = 90
        self._end = date.today()
        self._start = self._end - timedelta(days=self._days)
        self._data = self._generate()

    def _generate(self) -> dict:
        random.seed(self._seed)
        days = [self._start + timedelta(days=i) for i in range(self._days)]

        data = {"days": days}

        # Sleep scores: normal distribution ~78, range 55-95
        data["sleep_score"] = [max(40, min(100, int(random.gauss(78, 8)))) for _ in days]
        data["readiness_score"] = [max(40, min(100, int(random.gauss(75, 9)))) for _ in days]
        data["steps"] = [max(2000, int(random.gauss(8500, 2500))) for _ in days]
        data["active_cal"] = [max(100, int(random.gauss(450, 120))) for _ in days]
        data["total_cal"] = [ac + random.randint(1200, 1800) for ac in data["active_cal"]]

        # Sleep durations (seconds)
        data["total_sleep"] = [int(random.gauss(7.2, 0.8) * 3600) for _ in days]
        data["deep_sleep"] = [int(random.gauss(1.2, 0.3) * 3600) for _ in days]
        data["light_sleep"] = [int(random.gauss(3.5, 0.5) * 3600) for _ in days]
        data["rem_sleep"] = [int(random.gauss(1.8, 0.4) * 3600) for _ in days]
        data["awake_time"] = [max(0, ts - ds - ls - rs) for ts, ds, ls, rs in
                              zip(data["total_sleep"], data["deep_sleep"],
                                  data["light_sleep"], data["rem_sleep"])]

        # HR/HRV
        data["avg_hrv"] = [max(15, round(random.gauss(42, 10), 1)) for _ in days]
        data["lowest_hr"] = [max(38, int(random.gauss(52, 5))) for _ in days]
        data["avg_hr"] = [hr + random.randint(5, 12) for hr in data["lowest_hr"]]
        data["efficiency"] = [max(60, min(100, int(random.gauss(88, 5)))) for _ in days]
        data["latency"] = [max(60, int(random.gauss(480, 180))) for _ in days]
        data["avg_breath"] = [round(random.gauss(15.5, 1.0), 1) for _ in days]

        # Stress
        data["stress_summary"] = [random.choice(["restored", "normal", "normal", "stressful"]) for _ in days]
        data["stress_high"] = [max(0, int(random.gauss(4, 2) * 3600)) for _ in days]
        data["recovery_high"] = [max(0, int(random.gauss(6, 2) * 3600)) for _ in days]

        # Resilience
        data["resilience_level"] = [random.choice(["limited", "adequate", "solid", "solid", "strong", "exceptional"]) for _ in days]
        data["res_sleep_recovery"] = [round(random.gauss(65, 15), 1) for _ in days]
        data["res_daytime_recovery"] = [round(random.gauss(60, 18), 1) for _ in days]
        data["res_stress"] = [round(random.gauss(55, 20), 1) for _ in days]

        # SpO2
        data["spo2"] = [round(random.gauss(97.2, 0.8), 1) for _ in days]
        data["bdi"] = [max(0, round(random.gauss(2.5, 1.5), 1)) for _ in days]

        # Cardiovascular age
        data["cardio_age"] = [max(20, int(random.gauss(32, 3))) for _ in days]

        # VO2 max (changes slowly)
        base_vo2 = random.gauss(44, 3)
        data["vo2_max"] = [round(base_vo2 + random.gauss(0, 0.5), 1) for _ in days]

        # Activity breakdown (seconds)
        data["high_activity"] = [max(0, int(random.gauss(0.8, 0.4) * 3600)) for _ in days]
        data["medium_activity"] = [int(random.gauss(1.5, 0.6) * 3600) for _ in days]
        data["low_activity"] = [int(random.gauss(3.0, 1.0) * 3600) for _ in days]
        data["sedentary"] = [int(random.gauss(8, 2) * 3600) for _ in days]
        data["resting"] = [int(random.gauss(8, 1) * 3600) for _ in days]
        data["met"] = [round(random.gauss(1.5, 0.3), 1) for _ in days]
        data["distance_m"] = [int(s * 0.75) for s in data["steps"]]

        # Contributors (all 0-100)
        for key in ["deep_sleep_c", "efficiency_c", "latency_c", "rem_sleep_c",
                     "restfulness_c", "timing_c", "total_sleep_c"]:
            data[key] = [max(0, min(100, int(random.gauss(72, 12)))) for _ in days]

        for key in ["act_balance_c", "body_temp_c", "hrv_balance_c", "prev_day_c",
                     "prev_night_c", "recovery_idx_c", "resting_hr_c",
                     "sleep_balance_c", "sleep_reg_c"]:
            data[key] = [max(0, min(100, int(random.gauss(68, 14)))) for _ in days]

        for key in ["daily_targets_c", "move_hourly_c", "recovery_time_c",
                     "stay_active_c", "training_freq_c", "training_vol_c"]:
            data[key] = [max(0, min(100, int(random.gauss(70, 13)))) for _ in days]

        data["temp_deviation"] = [round(random.gauss(0, 0.3), 2) for _ in days]

        # Sleep phases for intra-night (generate encoded string)
        data["sleep_phases"] = []
        data["hr_items"] = []
        data["hrv_items"] = []
        for i in range(self._days):
            n_intervals = data["total_sleep"][i] // 300  # 5-min intervals
            phases = []
            hr = []
            hrv = []
            base_hr = data["avg_hr"][i]
            base_hrv = data["avg_hrv"][i]
            for j in range(n_intervals):
                # Cycle through phases roughly
                cycle_pos = (j % 18)  # ~90 min cycles
                if cycle_pos < 3:
                    phases.append("4")  # awake/light transition
                elif cycle_pos < 7:
                    phases.append("2")  # light
                elif cycle_pos < 11:
                    phases.append("1")  # deep
                elif cycle_pos < 15:
                    phases.append("2")  # light
                else:
                    phases.append("3")  # REM
                hr.append(max(40, int(base_hr + random.gauss(0, 3) - 5 * math.sin(j / n_intervals * 3.14))))
                hrv.append(max(10, int(base_hrv + random.gauss(0, 8))))
            data["sleep_phases"].append("".join(phases))
            data["hr_items"].append(hr)
            data["hrv_items"].append(hrv)

        # Target calories/meters
        data["target_cal"] = [500] * self._days
        data["target_meters"] = [7000] * self._days

        # Activity scores
        data["activity_score"] = [max(0, min(100, int(random.gauss(72, 10)))) for _ in days]

        return data

    def _idx(self, day: date) -> int | None:
        if day < self._start or day > self._end:
            return None
        return (day - self._start).days

    def _safe_idx(self, day: date) -> int:
        """Return index for day, clamped to valid range."""
        idx = self._idx(day)
        return min(idx, self._days - 1) if idx is not None else self._days - 1

    # ------------------------------------------------------------------
    # Latest scores
    # ------------------------------------------------------------------
    def latest_scores(self, end_date: date) -> dict:
        i = self._safe_idx(end_date)
        d = self._data
        return {
            "sleep_score": d["sleep_score"][i],
            "readiness_score": d["readiness_score"][i],
            "active_cal": d["active_cal"][i],
            "steps": d["steps"][i],
            "stress_summary": d["stress_summary"][i],
            "resilience_level": d["resilience_level"][i],
            "spo2": d["spo2"][i],
            "cardio_age": d["cardio_age"][i],
            "vo2_max": d["vo2_max"][i],
            "vo2_max_pb": max(d["vo2_max"]),
        }

    # ------------------------------------------------------------------
    # Trends
    # ------------------------------------------------------------------
    def _range_indices(self, start: date, end: date):
        s = max(0, (start - self._start).days)
        e = min(self._days, (end - self._start).days + 1)
        return range(s, e)

    def scores_trend(self, start: date, end: date) -> pd.DataFrame:
        rng = self._range_indices(start, end)
        d = self._data
        return pd.DataFrame({
            "day": [d["days"][i] for i in rng],
            "sleep_score": [d["sleep_score"][i] for i in rng],
            "readiness_score": [d["readiness_score"][i] for i in rng],
            "steps": [d["steps"][i] for i in rng],
        })

    def sleep_duration_breakdown(self, start: date, end: date) -> pd.DataFrame:
        rng = self._range_indices(start, end)
        d = self._data
        return pd.DataFrame({
            "day": [d["days"][i] for i in rng],
            "deep": [d["deep_sleep"][i] / 3600.0 for i in rng],
            "light": [d["light_sleep"][i] / 3600.0 for i in rng],
            "rem": [d["rem_sleep"][i] / 3600.0 for i in rng],
            "awake": [d["awake_time"][i] / 3600.0 for i in rng],
        })

    def sleep_contributors_latest(self, end_date: date) -> pd.DataFrame:
        i = self._safe_idx(end_date)
        d = self._data
        return pd.DataFrame([{
            "Deep Sleep": d["deep_sleep_c"][i], "Efficiency": d["efficiency_c"][i],
            "Latency": d["latency_c"][i], "REM Sleep": d["rem_sleep_c"][i],
            "Restfulness": d["restfulness_c"][i], "Timing": d["timing_c"][i],
            "Total Sleep": d["total_sleep_c"][i],
        }])

    def steps_30d(self, end_date: date) -> pd.DataFrame:
        start = end_date - timedelta(days=30)
        rng = self._range_indices(start, end_date)
        d = self._data
        return pd.DataFrame({
            "day": [d["days"][i] for i in rng],
            "steps": [d["steps"][i] for i in rng],
        })

    def spo2_trend(self, start: date, end: date) -> pd.DataFrame:
        rng = self._range_indices(start, end)
        d = self._data
        return pd.DataFrame({
            "day": [d["days"][i] for i in rng],
            "spo2": [d["spo2"][i] for i in rng],
        })

    def hrv_vs_readiness(self, start: date, end: date) -> pd.DataFrame:
        rng = self._range_indices(start, end)
        d = self._data
        records = []
        for i in rng:
            if i > 0:
                records.append({"day": d["days"][i], "hrv": d["avg_hrv"][i - 1],
                                "readiness": d["readiness_score"][i]})
        return pd.DataFrame(records)

    def weekly_trends(self, start: date, end: date) -> dict[str, pd.DataFrame]:
        rng = self._range_indices(start, end)
        d = self._data

        base = pd.DataFrame({
            "day": [d["days"][i] for i in rng],
            "sleep": [d["sleep_score"][i] for i in rng],
            "readiness": [d["readiness_score"][i] for i in rng],
            "steps": [d["steps"][i] for i in rng],
            "hrv": [d["avg_hrv"][i] for i in rng],
        })
        base["day"] = pd.to_datetime(base["day"])
        base["week"] = base["day"].dt.to_period("W").dt.start_time

        result = {}
        for key in ["sleep", "readiness", "steps", "hrv"]:
            grp = base.groupby("week")[key].mean().reset_index()
            grp.columns = ["week", "value"]
            result[key] = grp
        return result

    def sync_status(self) -> pd.DataFrame:
        return pd.DataFrame({
            "endpoint": ["demo"],
            "last_sync_date": [date.today()],
            "updated_at": [pd.Timestamp.now()],
            "status": ["Demo"],
        })

    # ------------------------------------------------------------------
    # Sleep page
    # ------------------------------------------------------------------
    def available_nights(self, start: date, end: date) -> list[date]:
        rng = self._range_indices(start, end)
        return [self._data["days"][i] for i in reversed(list(rng))]

    def sleep_session(self, night: date) -> dict | None:
        i = self._idx(night)
        if i is None:
            return None
        d = self._data
        bedtime = pd.Timestamp(f"{night} 23:15:00") - timedelta(days=1)
        return {
            "total_sleep": d["total_sleep"][i],
            "efficiency": d["efficiency"][i],
            "average_hrv": d["avg_hrv"][i],
            "lowest_heart_rate": d["lowest_hr"][i],
            "latency": d["latency"][i],
            "average_breath": d["avg_breath"][i],
            "bedtime_start": bedtime.isoformat(),
            "bedtime_end": (bedtime + timedelta(seconds=d["total_sleep"][i] + d["latency"][i])).isoformat(),
            "deep_sleep": d["deep_sleep"][i],
            "light_sleep": d["light_sleep"][i],
            "rem_sleep": d["rem_sleep"][i],
            "awake_time": d["awake_time"][i],
            "heart_rate": {"items": d["hr_items"][i]},
            "hrv": {"items": d["hrv_items"][i]},
            "sleep_phase_5_min": d["sleep_phases"][i],
            "average_heart_rate": d["avg_hr"][i],
        }

    def sleep_phases_pie(self, night: date) -> dict:
        i = self._idx(night)
        if i is None:
            return {}
        d = self._data
        return {
            "deep": d["deep_sleep"][i] / 60.0,
            "light": d["light_sleep"][i] / 60.0,
            "rem": d["rem_sleep"][i] / 60.0,
            "awake": d["awake_time"][i] / 60.0,
        }

    def sleep_phases_stacked(self, start: date, end: date) -> pd.DataFrame:
        return self.sleep_duration_breakdown(start, end)

    def sleep_hrv_trend(self, start: date, end: date) -> pd.DataFrame:
        rng = self._range_indices(start, end)
        d = self._data
        return pd.DataFrame({
            "day": [d["days"][i] for i in rng],
            "hrv": [d["avg_hrv"][i] for i in rng],
        })

    def sleep_resting_hr_trend(self, start: date, end: date) -> pd.DataFrame:
        rng = self._range_indices(start, end)
        d = self._data
        return pd.DataFrame({
            "day": [d["days"][i] for i in rng],
            "hr": [d["lowest_hr"][i] for i in rng],
        })

    def sleep_efficiency_trend(self, start: date, end: date) -> pd.DataFrame:
        rng = self._range_indices(start, end)
        d = self._data
        return pd.DataFrame({
            "day": [d["days"][i] for i in rng],
            "efficiency": [d["efficiency"][i] for i in rng],
        })

    def sleep_contributors_table(self, start: date, end: date) -> pd.DataFrame:
        rng = self._range_indices(start, end)
        d = self._data
        records = []
        for i in reversed(list(rng)):
            records.append({
                "Date": str(d["days"][i]),
                "Deep Sleep": d["deep_sleep_c"][i], "Efficiency": d["efficiency_c"][i],
                "Latency": d["latency_c"][i], "REM Sleep": d["rem_sleep_c"][i],
                "Restfulness": d["restfulness_c"][i], "Timing": d["timing_c"][i],
                "Total Sleep": d["total_sleep_c"][i],
            })
        return pd.DataFrame(records)

    def sleep_latency_trend(self, start: date, end: date) -> pd.DataFrame:
        rng = self._range_indices(start, end)
        d = self._data
        return pd.DataFrame({
            "day": [d["days"][i] for i in rng],
            "latency_min": [d["latency"][i] / 60.0 for i in rng],
        })

    def sleep_breathing_trend(self, start: date, end: date) -> pd.DataFrame:
        rng = self._range_indices(start, end)
        d = self._data
        return pd.DataFrame({
            "day": [d["days"][i] for i in rng],
            "breath": [d["avg_breath"][i] for i in rng],
        })

    def optimal_bedtime(self, end_date: date) -> dict:
        return {
            "optimal_bedtime_start": -3600,  # 11 PM
            "optimal_bedtime_end": -1800,     # 11:30 PM
            "recommendation": "on_track",
        }

    def nap_frequency(self, start: date, end: date) -> pd.DataFrame:
        rng = self._range_indices(start, end)
        d = self._data
        records = []
        random.seed(self._seed + 100)
        for i in rng:
            if random.random() < 0.15:  # ~15% of days have a nap
                records.append({"day": d["days"][i], "naps": 1})
        return pd.DataFrame(records) if records else pd.DataFrame(columns=["day", "naps"])

    # ------------------------------------------------------------------
    # Readiness page
    # ------------------------------------------------------------------
    def readiness_latest(self, end_date: date) -> dict:
        i = self._safe_idx(end_date)
        d = self._data
        return {
            "score": d["readiness_score"][i],
            "temperature_deviation": d["temp_deviation"][i],
            "Activity Balance": d["act_balance_c"][i],
            "Body Temp": d["body_temp_c"][i],
            "HRV Balance": d["hrv_balance_c"][i],
            "Prev Day Activity": d["prev_day_c"][i],
            "Previous Night": d["prev_night_c"][i],
            "Recovery Index": d["recovery_idx_c"][i],
            "Resting HR": d["resting_hr_c"][i],
            "Sleep Balance": d["sleep_balance_c"][i],
            "Sleep Regularity": d["sleep_reg_c"][i],
        }

    def readiness_trend(self, start: date, end: date) -> pd.DataFrame:
        rng = self._range_indices(start, end)
        d = self._data
        return pd.DataFrame({
            "day": [d["days"][i] for i in rng],
            "score": [d["readiness_score"][i] for i in rng],
        })

    def readiness_contributors_trend(self, start: date, end: date) -> pd.DataFrame:
        rng = self._range_indices(start, end)
        d = self._data
        return pd.DataFrame({
            "day": [d["days"][i] for i in rng],
            "HRV Balance": [d["hrv_balance_c"][i] for i in rng],
            "Sleep Balance": [d["sleep_balance_c"][i] for i in rng],
            "Recovery Index": [d["recovery_idx_c"][i] for i in rng],
            "Resting HR": [d["resting_hr_c"][i] for i in rng],
            "Sleep Regularity": [d["sleep_reg_c"][i] for i in rng],
        })

    def readiness_temp_trend(self, start: date, end: date) -> pd.DataFrame:
        rng = self._range_indices(start, end)
        d = self._data
        return pd.DataFrame({
            "day": [d["days"][i] for i in rng],
            "temp": [d["temp_deviation"][i] for i in rng],
        })

    # ------------------------------------------------------------------
    # Activity page
    # ------------------------------------------------------------------
    def activity_latest(self, end_date: date) -> dict:
        i = self._safe_idx(end_date)
        d = self._data
        return {
            "score": d["activity_score"][i],
            "active_calories": d["active_cal"][i],
            "total_calories": d["total_cal"][i],
            "steps": d["steps"][i],
            "distance_km": d["distance_m"][i] / 1000.0,
            "high_h": d["high_activity"][i] / 3600.0,
            "medium_h": d["medium_activity"][i] / 3600.0,
            "low_h": d["low_activity"][i] / 3600.0,
            "sedentary_h": d["sedentary"][i] / 3600.0,
            "resting_h": d["resting"][i] / 3600.0,
            "average_met_minutes": d["met"][i],
            "Daily Targets": d["daily_targets_c"][i],
            "Move Hourly": d["move_hourly_c"][i],
            "Recovery Time": d["recovery_time_c"][i],
            "Stay Active": d["stay_active_c"][i],
            "Training Freq": d["training_freq_c"][i],
            "Training Volume": d["training_vol_c"][i],
            "target_calories": d["target_cal"][i],
            "target_meters": d["target_meters"][i],
        }

    def activity_trend(self, start: date, end: date) -> pd.DataFrame:
        rng = self._range_indices(start, end)
        d = self._data
        return pd.DataFrame({
            "day": [d["days"][i] for i in rng],
            "active_calories": [d["active_cal"][i] for i in rng],
            "total_calories": [d["total_cal"][i] for i in rng],
            "steps": [d["steps"][i] for i in rng],
            "score": [d["activity_score"][i] for i in rng],
            "distance_km": [d["distance_m"][i] / 1000.0 for i in rng],
            "met": [d["met"][i] for i in rng],
            "target_calories": [d["target_cal"][i] for i in rng],
            "target_meters": [d["target_meters"][i] for i in rng],
        })

    def workouts(self, start: date, end: date) -> pd.DataFrame:
        rng = self._range_indices(start, end)
        d = self._data
        records = []
        random.seed(self._seed + 200)
        types = ["running", "walking", "cycling", "strength_training", "yoga", "swimming"]
        for i in rng:
            if random.random() < 0.35:
                records.append({
                    "day": d["days"][i],
                    "activity": random.choice(types),
                    "calories": round(random.gauss(300, 100)),
                    "distance": round(random.gauss(5000, 2000)),
                    "start_datetime": pd.Timestamp(f"{d['days'][i]} {(sh := random.randint(6, 17))}:00:00"),
                    "end_datetime": pd.Timestamp(f"{d['days'][i]} {sh + 1}:00:00"),
                    "intensity": random.choice(["easy", "moderate", "hard"]),
                    "source": random.choice(["manual", "autodetected"]),
                })
        return pd.DataFrame(records).sort_values("day", ascending=False) if records else pd.DataFrame(
            columns=["day", "activity", "calories", "distance", "start_datetime", "end_datetime", "intensity", "source"])

    # ------------------------------------------------------------------
    # Body page
    # ------------------------------------------------------------------
    def stress_latest(self, end_date: date) -> dict:
        i = self._safe_idx(end_date)
        d = self._data
        return {
            "day_summary": d["stress_summary"][i],
            "stress_high": d["stress_high"][i],
            "recovery_high": d["recovery_high"][i],
        }

    def stress_trend(self, start: date, end: date) -> pd.DataFrame:
        rng = self._range_indices(start, end)
        d = self._data
        return pd.DataFrame({
            "day": [d["days"][i] for i in rng],
            "stress_h": [d["stress_high"][i] / 3600.0 for i in rng],
            "recovery_h": [d["recovery_high"][i] / 3600.0 for i in rng],
        })

    def resilience_latest(self, end_date: date) -> dict:
        i = self._safe_idx(end_date)
        d = self._data
        return {
            "level": d["resilience_level"][i],
            "Sleep Recovery": d["res_sleep_recovery"][i],
            "Daytime Recovery": d["res_daytime_recovery"][i],
            "Stress": d["res_stress"][i],
        }

    def resilience_timeline(self, start: date, end: date) -> pd.DataFrame:
        rng = self._range_indices(start, end)
        d = self._data
        return pd.DataFrame({
            "day": [d["days"][i] for i in rng],
            "level": [d["resilience_level"][i] for i in rng],
        })

    def cardio_age_trend(self, start: date, end: date) -> pd.DataFrame:
        rng = self._range_indices(start, end)
        d = self._data
        return pd.DataFrame({
            "day": [d["days"][i] for i in rng],
            "vascular_age": [d["cardio_age"][i] for i in rng],
        })

    def vo2_max_trend(self, start: date, end: date) -> pd.DataFrame:
        rng = self._range_indices(start, end)
        d = self._data
        return pd.DataFrame({
            "day": [d["days"][i] for i in rng],
            "vo2_max": [d["vo2_max"][i] for i in rng],
        })

    def spo2_latest(self, end_date: date) -> dict:
        i = self._safe_idx(end_date)
        d = self._data
        return {"spo2": d["spo2"][i], "bdi": d["bdi"][i]}
