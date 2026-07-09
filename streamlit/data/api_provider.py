"""API data provider - calls Oura API v2 directly (for Streamlit Cloud)."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from datetime import time as datetime_time
from typing import Any

import pandas as pd
import requests

import streamlit as st


class ApiProvider:
    """Fetches data directly from the Oura API v2."""

    BASE_URL = "https://api.ouraring.com/v2/usercollection"

    def __init__(self, token: str):
        self._token = token
        self._headers = {"Authorization": f"Bearer {token}"}

    def _fetch(
        self,
        endpoint: str,
        start: date | None = None,
        end: date | None = None,
        *,
        query_mode: str = "date",
        response_mode: str = "collection",
    ) -> list[dict]:
        """Fetch all pages from an Oura API endpoint."""
        import time

        if query_mode == "datetime" and start and end and (end - start).days >= 30:
            all_chunks = []
            current = start
            while current <= end:
                chunk_end = min(current + timedelta(days=29), end)
                all_chunks.extend(
                    self._fetch(endpoint, current, chunk_end, query_mode=query_mode, response_mode=response_mode)
                )
                current = chunk_end + timedelta(days=1)
            return all_chunks

        params: dict[str, Any] = {}
        if query_mode == "date":
            if start:
                params["start_date"] = start.isoformat()
            if end:
                params["end_date"] = end.isoformat()
        elif query_mode == "datetime":
            if start:
                params["start_datetime"] = datetime.combine(start, datetime_time.min, timezone.utc).isoformat()
            if end:
                end_dt = (
                    datetime.now(timezone.utc)
                    if end == date.today()
                    else datetime.combine(end, datetime_time.max, timezone.utc)
                )
                params["end_datetime"] = end_dt.isoformat()
        elif query_mode != "none":
            raise ValueError(f"Unknown query mode: {query_mode}")

        all_data = []
        url = f"{self.BASE_URL}/{endpoint}"
        retries = 0
        max_retries = 5
        while url:
            resp = requests.get(url, headers=self._headers, params=params, timeout=30)
            if resp.status_code == 429:
                retries += 1
                if retries > max_retries:
                    resp.raise_for_status()
                retry_after = int(resp.headers.get("Retry-After", 60))
                time.sleep(min(retry_after, 120))
                continue
            resp.raise_for_status()
            retries = 0
            body = resp.json()
            if response_mode == "single":
                return [body]
            all_data.extend(body.get("data", []))
            next_token = body.get("next_token")
            if next_token:
                params = {"next_token": next_token}
            else:
                url = None
        return all_data

    def _fetch_cached(self, endpoint, start=None, end=None, *, query_mode="date", response_mode="collection"):
        key = f"api_{endpoint}_{start}_{end}_{query_mode}_{response_mode}"
        if key not in st.session_state:
            st.session_state[key] = self._fetch(
                endpoint,
                start,
                end,
                query_mode=query_mode,
                response_mode=response_mode,
            )
        return st.session_state[key]

    # ------------------------------------------------------------------
    # Latest scores
    # ------------------------------------------------------------------
    def latest_scores(self, end_date: date) -> dict:
        start = end_date - timedelta(days=7)
        result = {}

        for ep, field, out_key in [
            ("daily_sleep", "score", "sleep_score"),
            ("daily_readiness", "score", "readiness_score"),
            ("daily_spo2", None, "spo2"),
            ("daily_cardiovascular_age", "vascular_age", "cardio_age"),
            ("daily_resilience", "level", "resilience_level"),
            ("vO2_max", "vo2_max", "vo2_max"),
        ]:
            try:
                data = self._fetch_cached(ep, start, end_date)
                if data:
                    last = data[-1]
                    if ep == "daily_spo2":
                        spo2_pct = last.get("spo2_percentage", {})
                        result["spo2"] = spo2_pct.get("average") if isinstance(spo2_pct, dict) else None
                    elif field:
                        result[out_key] = last.get(field)
            except Exception:
                result[out_key] = None

        # Activity
        try:
            act = self._fetch_cached("daily_activity", start, end_date)
            if act:
                last = act[-1]
                result["active_cal"] = last.get("active_calories")
                result["steps"] = last.get("steps")
        except Exception:
            pass

        # Stress
        try:
            stress = self._fetch_cached("daily_stress", start, end_date)
            if stress:
                for s in reversed(stress):
                    ds = s.get("day_summary")
                    if ds and ds != "":
                        result["stress_summary"] = ds
                        break
        except Exception:
            pass

        # VO2 max personal best
        try:
            vo2_all = self._fetch_cached("vO2_max", end_date - timedelta(days=365), end_date)
            if vo2_all:
                vo2_vals = [r.get("vo2_max") for r in vo2_all if r.get("vo2_max")]
                if vo2_vals:
                    result["vo2_max_pb"] = max(vo2_vals)
        except Exception:
            pass

        return result

    # ------------------------------------------------------------------
    # Trends
    # ------------------------------------------------------------------
    def scores_trend(self, start: date, end: date) -> pd.DataFrame:
        sleep = self._fetch_cached("daily_sleep", start, end)
        readiness = self._fetch_cached("daily_readiness", start, end)
        activity = self._fetch_cached("daily_activity", start, end)

        sleep_df = (
            pd.DataFrame(sleep)[["day", "score"]].rename(columns={"score": "sleep_score"})
            if sleep
            else pd.DataFrame(columns=["day", "sleep_score"])
        )
        read_df = (
            pd.DataFrame(readiness)[["day", "score"]].rename(columns={"score": "readiness_score"})
            if readiness
            else pd.DataFrame(columns=["day", "readiness_score"])
        )
        act_df = pd.DataFrame(activity)[["day", "steps"]] if activity else pd.DataFrame(columns=["day", "steps"])

        df = sleep_df.merge(read_df, on="day", how="outer").merge(act_df, on="day", how="outer")
        df["day"] = pd.to_datetime(df["day"])
        return df.sort_values("day").reset_index(drop=True)

    def sleep_duration_breakdown(self, start: date, end: date) -> pd.DataFrame:
        data = self._fetch_cached("sleep", start, end)
        records = []
        seen_days = set()
        # Sort by total_sleep desc to keep primary sleep per day
        sorted_data = sorted(
            [d for d in data if d.get("type") == "long_sleep"],
            key=lambda d: (d.get("day", ""), -(d.get("total_sleep_duration") or 0)),
        )
        for d in sorted_data:
            day = d.get("day")
            if day in seen_days:
                continue
            seen_days.add(day)
            records.append(
                {
                    "day": day,
                    "deep": (d.get("deep_sleep_duration") or 0) / 3600.0,
                    "light": (d.get("light_sleep_duration") or 0) / 3600.0,
                    "rem": (d.get("rem_sleep_duration") or 0) / 3600.0,
                    "awake": (d.get("awake_time") or 0) / 3600.0,
                }
            )
        df = pd.DataFrame(records)
        if not df.empty:
            df["day"] = pd.to_datetime(df["day"])
            df = df.sort_values("day")
        return df

    def sleep_contributors_latest(self, end_date: date) -> pd.DataFrame:
        data = self._fetch_cached("daily_sleep", end_date - timedelta(days=7), end_date)
        if not data:
            return pd.DataFrame()
        last = data[-1]
        c = last.get("contributors", {})
        return pd.DataFrame(
            [
                {
                    "Deep Sleep": c.get("deep_sleep"),
                    "Efficiency": c.get("efficiency"),
                    "Latency": c.get("latency"),
                    "REM Sleep": c.get("rem_sleep"),
                    "Restfulness": c.get("restfulness"),
                    "Timing": c.get("timing"),
                    "Total Sleep": c.get("total_sleep"),
                }
            ]
        )

    def steps_30d(self, end_date: date) -> pd.DataFrame:
        start = end_date - timedelta(days=30)
        data = self._fetch_cached("daily_activity", start, end_date)
        if not data:
            return pd.DataFrame(columns=["day", "steps"])
        df = pd.DataFrame(data)[["day", "steps"]]
        df["day"] = pd.to_datetime(df["day"])
        return df.sort_values("day")

    def spo2_trend(self, start: date, end: date) -> pd.DataFrame:
        data = self._fetch_cached("daily_spo2", start, end)
        records = []
        for d in data:
            spo2_pct = d.get("spo2_percentage", {})
            avg = spo2_pct.get("average") if isinstance(spo2_pct, dict) else None
            if avg and avg > 0:
                records.append({"day": d["day"], "spo2": avg})
        df = pd.DataFrame(records)
        if not df.empty:
            df["day"] = pd.to_datetime(df["day"])
        return df

    def hrv_vs_readiness(self, start: date, end: date) -> pd.DataFrame:
        sleep = self._fetch_cached("sleep", start, end)
        readiness = self._fetch_cached("daily_readiness", start, end)

        # Build primary sleep per day
        hrv_by_day = {}
        for s in sorted(sleep, key=lambda x: -(x.get("total_sleep_duration") or 0)):
            if s.get("type") == "long_sleep" and s.get("day") not in hrv_by_day:
                hrv_by_day[s["day"]] = s.get("average_hrv")

        records = []
        for r in readiness:
            day = r["day"]
            prev_day = (pd.Timestamp(day) - timedelta(days=1)).strftime("%Y-%m-%d")
            if prev_day in hrv_by_day:
                records.append({"day": day, "hrv": hrv_by_day[prev_day], "readiness": r.get("score")})

        df = pd.DataFrame(records)
        if not df.empty:
            df["day"] = pd.to_datetime(df["day"])
        return df

    def weekly_trends(self, start: date, end: date) -> dict[str, pd.DataFrame]:
        result = {}
        for ep, field, key in [
            ("daily_sleep", "score", "sleep"),
            ("daily_readiness", "score", "readiness"),
            ("daily_activity", "steps", "steps"),
        ]:
            data = self._fetch_cached(ep, start, end)
            if data:
                df = pd.DataFrame(data)
                df["day"] = pd.to_datetime(df["day"])
                df["week"] = df["day"].dt.to_period("W").dt.start_time
                result[key] = df.groupby("week")[field].mean().reset_index()
                result[key].columns = ["week", "value"]
            else:
                result[key] = pd.DataFrame(columns=["week", "value"])

        # HRV from sleep
        sleep = self._fetch_cached("sleep", start, end)
        if sleep:
            primary = {}
            for s in sorted(sleep, key=lambda x: -(x.get("total_sleep_duration") or 0)):
                if s.get("type") == "long_sleep" and s.get("day") not in primary:
                    primary[s["day"]] = s.get("average_hrv")
            hrv_df = pd.DataFrame(list(primary.items()), columns=["day", "average_hrv"])
            hrv_df["day"] = pd.to_datetime(hrv_df["day"])
            hrv_df["week"] = hrv_df["day"].dt.to_period("W").dt.start_time
            result["hrv"] = hrv_df.groupby("week")["average_hrv"].mean().reset_index()
            result["hrv"].columns = ["week", "value"]
        else:
            result["hrv"] = pd.DataFrame(columns=["week", "value"])
        return result

    def sync_status(self) -> pd.DataFrame:
        return pd.DataFrame(columns=["endpoint", "last_sync_date", "updated_at", "status"])

    # ------------------------------------------------------------------
    # Sleep page
    # ------------------------------------------------------------------
    def available_nights(self, start: date, end: date) -> list[date]:
        data = self._fetch_cached("sleep", start, end)
        nights = sorted({d["day"] for d in data if d.get("type") == "long_sleep"}, reverse=True)
        return [date.fromisoformat(n) for n in nights]

    def sleep_session(self, night: date) -> dict | None:
        data = self._fetch_cached("sleep", night - timedelta(days=1), night + timedelta(days=1))
        sessions = [d for d in data if d.get("type") == "long_sleep" and d.get("day") == night.isoformat()]
        if not sessions:
            return None
        s = max(sessions, key=lambda x: x.get("total_sleep_duration") or 0)
        return {
            "total_sleep": s.get("total_sleep_duration"),
            "efficiency": s.get("efficiency"),
            "average_hrv": s.get("average_hrv"),
            "lowest_heart_rate": s.get("lowest_heart_rate"),
            "latency": s.get("latency"),
            "average_breath": s.get("average_breath"),
            "bedtime_start": s.get("bedtime_start"),
            "bedtime_end": s.get("bedtime_end"),
            "deep_sleep": s.get("deep_sleep_duration"),
            "light_sleep": s.get("light_sleep_duration"),
            "rem_sleep": s.get("rem_sleep_duration"),
            "awake_time": s.get("awake_time"),
            "heart_rate": s.get("heart_rate"),
            "hrv": s.get("hrv"),
            "sleep_phase_5_min": s.get("sleep_phase_5_min"),
            "average_heart_rate": s.get("average_heart_rate"),
        }

    def sleep_phases_pie(self, night: date) -> dict:
        s = self.sleep_session(night)
        if not s:
            return {}
        return {
            "deep": (s.get("deep_sleep") or 0) / 60.0,
            "light": (s.get("light_sleep") or 0) / 60.0,
            "rem": (s.get("rem_sleep") or 0) / 60.0,
            "awake": (s.get("awake_time") or 0) / 60.0,
        }

    def sleep_phases_stacked(self, start: date, end: date) -> pd.DataFrame:
        return self.sleep_duration_breakdown(start, end)

    def sleep_hrv_trend(self, start: date, end: date) -> pd.DataFrame:
        data = self._fetch_cached("sleep", start, end)
        primary = {}
        for s in sorted(data, key=lambda x: -(x.get("total_sleep_duration") or 0)):
            if s.get("type") == "long_sleep" and s.get("day") not in primary:
                primary[s["day"]] = s.get("average_hrv")
        df = pd.DataFrame(list(primary.items()), columns=["day", "hrv"])
        if not df.empty:
            df["day"] = pd.to_datetime(df["day"])
            df = df.sort_values("day")
        return df

    def sleep_resting_hr_trend(self, start: date, end: date) -> pd.DataFrame:
        data = self._fetch_cached("sleep", start, end)
        primary = {}
        for s in sorted(data, key=lambda x: -(x.get("total_sleep_duration") or 0)):
            if s.get("type") == "long_sleep" and s.get("day") not in primary:
                primary[s["day"]] = s.get("lowest_heart_rate")
        df = pd.DataFrame(list(primary.items()), columns=["day", "hr"])
        if not df.empty:
            df["day"] = pd.to_datetime(df["day"])
            df = df.sort_values("day")
        return df

    def sleep_efficiency_trend(self, start: date, end: date) -> pd.DataFrame:
        data = self._fetch_cached("sleep", start, end)
        primary = {}
        for s in sorted(data, key=lambda x: -(x.get("total_sleep_duration") or 0)):
            if s.get("type") == "long_sleep" and s.get("day") not in primary:
                primary[s["day"]] = s.get("efficiency")
        df = pd.DataFrame(list(primary.items()), columns=["day", "efficiency"])
        if not df.empty:
            df["day"] = pd.to_datetime(df["day"])
            df = df.sort_values("day")
        return df

    def sleep_contributors_table(self, start: date, end: date) -> pd.DataFrame:
        data = self._fetch_cached("daily_sleep", start, end)
        records = []
        for d in data:
            c = d.get("contributors", {})
            records.append(
                {
                    "Date": d["day"],
                    "Deep Sleep": c.get("deep_sleep"),
                    "Efficiency": c.get("efficiency"),
                    "Latency": c.get("latency"),
                    "REM Sleep": c.get("rem_sleep"),
                    "Restfulness": c.get("restfulness"),
                    "Timing": c.get("timing"),
                    "Total Sleep": c.get("total_sleep"),
                }
            )
        return pd.DataFrame(records).sort_values("Date", ascending=False) if records else pd.DataFrame()

    def sleep_latency_trend(self, start: date, end: date) -> pd.DataFrame:
        data = self._fetch_cached("sleep", start, end)
        primary = {}
        for s in sorted(data, key=lambda x: -(x.get("total_sleep_duration") or 0)):
            if s.get("type") == "long_sleep" and s.get("day") not in primary:
                primary[s["day"]] = (s.get("latency") or 0) / 60.0
        df = pd.DataFrame(list(primary.items()), columns=["day", "latency_min"])
        if not df.empty:
            df["day"] = pd.to_datetime(df["day"])
            df = df.sort_values("day")
        return df

    def sleep_breathing_trend(self, start: date, end: date) -> pd.DataFrame:
        data = self._fetch_cached("sleep", start, end)
        primary = {}
        for s in sorted(data, key=lambda x: -(x.get("total_sleep_duration") or 0)):
            if s.get("type") == "long_sleep" and s.get("day") not in primary:
                primary[s["day"]] = s.get("average_breath")
        df = pd.DataFrame(list(primary.items()), columns=["day", "breath"])
        if not df.empty:
            df["day"] = pd.to_datetime(df["day"])
            df = df.sort_values("day")
        return df

    def optimal_bedtime(self, end_date: date) -> dict:
        data = self._fetch_cached("sleep_time", end_date - timedelta(days=7), end_date)
        if not data:
            return {}
        last = data[-1]
        bt = last.get("optimal_bedtime", {}) or {}
        return {
            "optimal_bedtime_start": bt.get("start_offset"),
            "optimal_bedtime_end": bt.get("end_offset"),
            "recommendation": last.get("recommendation"),
        }

    def nap_frequency(self, start: date, end: date) -> pd.DataFrame:
        data = self._fetch_cached("sleep", start, end)
        naps = {}
        for d in data:
            if d.get("type") in ("late_nap", "sleep"):
                day = d["day"]
                naps[day] = naps.get(day, 0) + 1
        df = pd.DataFrame(list(naps.items()), columns=["day", "naps"])
        if not df.empty:
            df["day"] = pd.to_datetime(df["day"])
            df = df.sort_values("day")
        return df

    # ------------------------------------------------------------------
    # Readiness page
    # ------------------------------------------------------------------
    def readiness_latest(self, end_date: date) -> dict:
        data = self._fetch_cached("daily_readiness", end_date - timedelta(days=7), end_date)
        if not data:
            return {}
        last = data[-1]
        c = last.get("contributors", {})
        return {
            "score": last.get("score"),
            "temperature_deviation": last.get("temperature_deviation"),
            "Activity Balance": c.get("activity_balance"),
            "Body Temp": c.get("body_temperature"),
            "HRV Balance": c.get("hrv_balance"),
            "Prev Day Activity": c.get("previous_day_activity"),
            "Previous Night": c.get("previous_night"),
            "Recovery Index": c.get("recovery_index"),
            "Resting HR": c.get("resting_heart_rate"),
            "Sleep Balance": c.get("sleep_balance"),
            "Sleep Regularity": c.get("sleep_regularity"),
        }

    def readiness_trend(self, start: date, end: date) -> pd.DataFrame:
        data = self._fetch_cached("daily_readiness", start, end)
        if not data:
            return pd.DataFrame(columns=["day", "score"])
        df = pd.DataFrame(data)[["day", "score"]]
        df["day"] = pd.to_datetime(df["day"])
        return df.sort_values("day")

    def readiness_contributors_trend(self, start: date, end: date) -> pd.DataFrame:
        data = self._fetch_cached("daily_readiness", start, end)
        records = []
        for d in data:
            c = d.get("contributors", {})
            records.append(
                {
                    "day": d["day"],
                    "HRV Balance": c.get("hrv_balance"),
                    "Sleep Balance": c.get("sleep_balance"),
                    "Recovery Index": c.get("recovery_index"),
                    "Resting HR": c.get("resting_heart_rate"),
                    "Sleep Regularity": c.get("sleep_regularity"),
                }
            )
        df = pd.DataFrame(records)
        if not df.empty:
            df["day"] = pd.to_datetime(df["day"])
            df = df.sort_values("day")
        return df

    def readiness_temp_trend(self, start: date, end: date) -> pd.DataFrame:
        data = self._fetch_cached("daily_readiness", start, end)
        if not data:
            return pd.DataFrame(columns=["day", "temp"])
        df = pd.DataFrame(data)[["day", "temperature_deviation"]].rename(columns={"temperature_deviation": "temp"})
        df["day"] = pd.to_datetime(df["day"])
        return df.sort_values("day")

    # ------------------------------------------------------------------
    # Activity page
    # ------------------------------------------------------------------
    def activity_latest(self, end_date: date) -> dict:
        data = self._fetch_cached("daily_activity", end_date - timedelta(days=7), end_date)
        if not data:
            return {}
        last = data[-1]
        c = last.get("contributors", {})
        return {
            "score": last.get("score"),
            "active_calories": last.get("active_calories"),
            "total_calories": last.get("total_calories"),
            "steps": last.get("steps"),
            "distance_km": (last.get("equivalent_walking_distance") or 0) / 1000.0,
            "high_h": (last.get("high_activity_time") or 0) / 3600.0,
            "medium_h": (last.get("medium_activity_time") or 0) / 3600.0,
            "low_h": (last.get("low_activity_time") or 0) / 3600.0,
            "sedentary_h": (last.get("sedentary_time") or 0) / 3600.0,
            "resting_h": (last.get("resting_time") or 0) / 3600.0,
            "average_met_minutes": last.get("average_met_minutes"),
            "Daily Targets": c.get("meet_daily_targets"),
            "Move Hourly": c.get("move_every_hour"),
            "Recovery Time": c.get("recovery_time"),
            "Stay Active": c.get("stay_active"),
            "Training Freq": c.get("training_frequency"),
            "Training Volume": c.get("training_volume"),
            "target_calories": last.get("target_calories"),
            "target_meters": last.get("target_meters"),
        }

    def activity_trend(self, start: date, end: date) -> pd.DataFrame:
        data = self._fetch_cached("daily_activity", start, end)
        if not data:
            return pd.DataFrame()
        records = []
        for d in data:
            records.append(
                {
                    "day": d["day"],
                    "active_calories": d.get("active_calories"),
                    "total_calories": d.get("total_calories"),
                    "steps": d.get("steps"),
                    "score": d.get("score") if d.get("score") else None,
                    "distance_km": (d.get("equivalent_walking_distance") or 0) / 1000.0,
                    "met": d.get("average_met_minutes"),
                    "target_calories": d.get("target_calories"),
                    "target_meters": d.get("target_meters"),
                }
            )
        df = pd.DataFrame(records)
        df["day"] = pd.to_datetime(df["day"])
        return df.sort_values("day")

    def workouts(self, start: date, end: date) -> pd.DataFrame:
        data = self._fetch_cached("workout", start, end)
        if not data:
            return pd.DataFrame(
                columns=[
                    "day",
                    "activity",
                    "calories",
                    "distance",
                    "start_datetime",
                    "end_datetime",
                    "intensity",
                    "source",
                ]
            )
        df = pd.DataFrame(data).reindex(columns=["day", "type", "mood", "start_datetime", "end_datetime"])
        return df.sort_values("day", ascending=False) if not df.empty else df

    # ------------------------------------------------------------------
    # Body page
    # ------------------------------------------------------------------
    def stress_latest(self, end_date: date) -> dict:
        data = self._fetch_cached("daily_stress", end_date - timedelta(days=7), end_date)
        if not data:
            return {}
        last = data[-1]
        return {
            "day_summary": last.get("day_summary"),
            "stress_high": last.get("stress_high"),
            "recovery_high": last.get("recovery_high"),
        }

    def stress_trend(self, start: date, end: date) -> pd.DataFrame:
        data = self._fetch_cached("daily_stress", start, end)
        records = [
            {
                "day": d["day"],
                "stress_h": (d.get("stress_high") or 0) / 3600.0,
                "recovery_h": (d.get("recovery_high") or 0) / 3600.0,
            }
            for d in data
        ]
        df = pd.DataFrame(records)
        if not df.empty:
            df["day"] = pd.to_datetime(df["day"])
            df = df.sort_values("day")
        return df

    def resilience_latest(self, end_date: date) -> dict:
        data = self._fetch_cached("daily_resilience", end_date - timedelta(days=7), end_date)
        if not data:
            return {}
        last = data[-1]
        c = last.get("contributors", {})
        return {
            "level": last.get("level"),
            "Sleep Recovery": c.get("sleep_recovery"),
            "Daytime Recovery": c.get("daytime_recovery"),
            "Stress": c.get("stress"),
        }

    def resilience_timeline(self, start: date, end: date) -> pd.DataFrame:
        data = self._fetch_cached("daily_resilience", start, end)
        if not data:
            return pd.DataFrame(columns=["day", "level"])
        df = pd.DataFrame(data)[["day", "level"]]
        df["day"] = pd.to_datetime(df["day"])
        return df.sort_values("day")

    def cardio_age_trend(self, start: date, end: date) -> pd.DataFrame:
        data = self._fetch_cached("daily_cardiovascular_age", start, end)
        if not data:
            return pd.DataFrame(columns=["day", "vascular_age"])
        df = pd.DataFrame(data)[["day", "vascular_age"]]
        df["day"] = pd.to_datetime(df["day"])
        return df.sort_values("day")

    def vo2_max_trend(self, start: date, end: date) -> pd.DataFrame:
        data = self._fetch_cached("vO2_max", start, end)
        if not data:
            return pd.DataFrame(columns=["day", "vo2_max"])
        df = pd.DataFrame(data)[["day", "vo2_max"]]
        df["day"] = pd.to_datetime(df["day"])
        return df.sort_values("day")

    def spo2_latest(self, end_date: date) -> dict:
        data = self._fetch_cached("daily_spo2", end_date - timedelta(days=7), end_date)
        if not data:
            return {}
        last = data[-1]
        spo2_pct = last.get("spo2_percentage", {})
        return {
            "spo2": spo2_pct.get("average") if isinstance(spo2_pct, dict) else None,
            "bdi": last.get("breathing_disturbance_index"),
        }

    # ------------------------------------------------------------------
    # Extended API pages
    # ------------------------------------------------------------------
    def _heart_rate_frame(self, start: date, end: date) -> pd.DataFrame:
        data = self._fetch_cached("heartrate", start, end, query_mode="datetime")
        if not data:
            return pd.DataFrame(columns=["timestamp", "bpm", "source"])
        df = pd.DataFrame(data)[["timestamp", "bpm", "source"]]
        df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
        return df.sort_values("timestamp")

    def heart_rate_summary(self, start: date, end: date) -> dict:
        df = self._heart_rate_frame(start, end)
        if df.empty:
            return {}
        return {
            "latest": int(df.iloc[-1]["bpm"]),
            "average": round(df["bpm"].mean(), 1),
            "minimum": int(df["bpm"].min()),
            "maximum": int(df["bpm"].max()),
        }

    def heart_rate_series(self, start: date, end: date) -> pd.DataFrame:
        df = self._heart_rate_frame(start, end)
        if len(df) <= 5000:
            return df
        bucket_minutes = max(1, ((end - start).days * 24 * 60 + 4999) // 5000)
        return (
            df.groupby([pd.Grouper(key="timestamp", freq=f"{bucket_minutes}min"), "source"], as_index=False)["bpm"]
            .mean()
            .dropna()
        )

    def heart_rate_daily(self, start: date, end: date) -> pd.DataFrame:
        df = self._heart_rate_frame(start, end)
        if df.empty:
            return pd.DataFrame(columns=["day", "minimum", "average", "maximum"])
        df["day"] = df["timestamp"].dt.date
        return df.groupby("day", as_index=False)["bpm"].agg(minimum="min", average="mean", maximum="max")

    def heart_rate_sources(self, start: date, end: date) -> pd.DataFrame:
        df = self._heart_rate_frame(start, end)
        return df.groupby("source", as_index=False).size().rename(columns={"size": "count"})

    def sessions(self, start: date, end: date) -> pd.DataFrame:
        data = self._fetch_cached("session", start, end)
        if not data:
            return pd.DataFrame(columns=["day", "type", "mood", "start_datetime", "duration_minutes"])
        df = pd.DataFrame(data)
        df["start_datetime"] = pd.to_datetime(df["start_datetime"])
        df["end_datetime"] = pd.to_datetime(df["end_datetime"])
        df["duration_minutes"] = (df["end_datetime"] - df["start_datetime"]).dt.total_seconds() / 60
        return df[["day", "type", "mood", "start_datetime", "duration_minutes"]].sort_values(
            "start_datetime", ascending=False
        )

    def tags(self, start: date, end: date) -> pd.DataFrame:
        rows = []
        for item in self._fetch_cached("tag", start, end):
            rows.append(
                {
                    "time": item.get("timestamp"),
                    "kind": "Tag",
                    "label": ", ".join(item.get("tags") or []) or item.get("text"),
                    "comment": item.get("text"),
                }
            )
        for item in self._fetch_cached("enhanced_tag", start, end):
            rows.append(
                {
                    "time": item.get("start_time"),
                    "kind": "Enhanced",
                    "label": item.get("custom_name") or item.get("tag_type_code"),
                    "comment": item.get("comment"),
                }
            )
        df = pd.DataFrame(rows, columns=["time", "kind", "label", "comment"])
        if not df.empty:
            df["time"] = pd.to_datetime(df["time"])
            df = df.sort_values("time", ascending=False)
        return df

    def rest_modes(self, start: date, end: date) -> pd.DataFrame:
        data = self._fetch_cached("rest_mode_period", start, end)
        if not data:
            return pd.DataFrame(columns=["start_day", "end_day", "start_time", "end_time", "episodes"])
        return (
            pd.DataFrame(data)
            .reindex(columns=["start_day", "end_day", "start_time", "end_time", "episodes"])
            .sort_values("start_day", ascending=False)
        )

    def battery_series(self, start: date, end: date) -> pd.DataFrame:
        data = self._fetch_cached("ring_battery_level", start, end, query_mode="datetime")
        if not data:
            return pd.DataFrame(columns=["timestamp", "level", "charging", "in_charger"])
        df = pd.DataFrame(data).reindex(columns=["timestamp", "level", "charging", "in_charger"])
        df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
        return df.sort_values("timestamp")

    def ring_configurations(self) -> pd.DataFrame:
        data = self._fetch_cached("ring_configuration", query_mode="none")
        return pd.DataFrame(data).reindex(
            columns=["color", "design", "firmware_version", "hardware_type", "set_up_at", "size"]
        )

    def personal_profile(self) -> dict:
        data = self._fetch_cached("personal_info", query_mode="none", response_mode="single")
        if not data:
            return {}
        return {k: data[0].get(k) for k in ("age", "weight", "height", "biological_sex")}

    def ring_summary(self, start: date, end: date) -> dict:
        battery = self.battery_series(start, end)
        configs = self.ring_configurations()
        current = configs.sort_values("set_up_at", na_position="first").iloc[-1] if not configs.empty else {}
        result = {
            "hardware_type": current.get("hardware_type"),
            "firmware_version": current.get("firmware_version"),
        }
        if not battery.empty:
            result.update(
                {
                    "latest_level": int(battery.iloc[-1]["level"]),
                    "minimum_level": int(battery["level"].min()),
                    "charging": bool(battery.iloc[-1]["charging"]),
                }
            )
        return result
