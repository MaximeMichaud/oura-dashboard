"""PostgreSQL data provider - reads from the existing oura database."""
from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st

from components.db import get_engine, query_df


class PostgresProvider:
    """Reads data from PostgreSQL (same DB as Grafana)."""

    def test_connection(self):
        from sqlalchemy import text
        with get_engine().connect() as conn:
            conn.execute(text("SELECT 1"))

    # ------------------------------------------------------------------
    # Latest single values
    # ------------------------------------------------------------------
    @st.cache_data(ttl=300, show_spinner=False)
    def latest_scores(_self, end_date: date) -> dict:
        """Latest daily scores for overview stat cards."""
        sql = """
        SELECT
            (SELECT score FROM daily_sleep WHERE day <= :end ORDER BY day DESC LIMIT 1) AS sleep_score,
            (SELECT score FROM daily_readiness WHERE day <= :end ORDER BY day DESC LIMIT 1) AS readiness_score,
            (SELECT active_calories FROM daily_activity WHERE day <= :end ORDER BY day DESC LIMIT 1) AS active_cal,
            (SELECT steps FROM daily_activity WHERE day <= :end ORDER BY day DESC LIMIT 1) AS steps,
            (SELECT day_summary FROM daily_stress WHERE day_summary IS NOT NULL AND day_summary <> ''
                AND day <= :end ORDER BY day DESC LIMIT 1) AS stress_summary,
            (SELECT level FROM daily_resilience WHERE day <= :end ORDER BY day DESC LIMIT 1) AS resilience_level,
            (SELECT NULLIF(spo2_percentage_average, 0) FROM daily_spo2
                WHERE spo2_percentage_average > 0 AND day <= :end ORDER BY day DESC LIMIT 1) AS spo2,
            (SELECT vascular_age FROM daily_cardiovascular_age
                WHERE day <= :end ORDER BY day DESC LIMIT 1) AS cardio_age,
            (SELECT vo2_max FROM daily_vo2_max WHERE day <= :end ORDER BY day DESC LIMIT 1) AS vo2_max,
            (SELECT MAX(vo2_max) FROM daily_vo2_max) AS vo2_max_pb
        """
        df = query_df(sql, {"end": end_date})
        return df.iloc[0].to_dict() if not df.empty else {}

    # ------------------------------------------------------------------
    # Time-filtered trends
    # ------------------------------------------------------------------
    @st.cache_data(ttl=300, show_spinner=False)
    def scores_trend(_self, start: date, end: date) -> pd.DataFrame:
        return query_df("""
            SELECT a.day, s.score AS sleep_score, r.score AS readiness_score, a.steps
            FROM daily_activity a
            LEFT JOIN daily_sleep s ON s.day = a.day
            LEFT JOIN daily_readiness r ON r.day = a.day
            WHERE a.day >= :start AND a.day <= :end
            ORDER BY a.day
        """, {"start": start, "end": end})

    @st.cache_data(ttl=300, show_spinner=False)
    def sleep_duration_breakdown(_self, start: date, end: date) -> pd.DataFrame:
        return query_df("""
            SELECT day,
                   deep_sleep / 3600.0 AS deep,
                   light_sleep / 3600.0 AS light,
                   rem_sleep / 3600.0 AS rem,
                   awake_time / 3600.0 AS awake
            FROM sleep_primary
            WHERE day >= :start AND day <= :end
            ORDER BY day
        """, {"start": start, "end": end})

    @st.cache_data(ttl=300, show_spinner=False)
    def sleep_contributors_latest(_self, end_date: date) -> pd.DataFrame:
        return query_df("""
            SELECT contributors_deep_sleep AS "Deep Sleep",
                   contributors_efficiency AS "Efficiency",
                   contributors_latency AS "Latency",
                   contributors_rem_sleep AS "REM Sleep",
                   contributors_restfulness AS "Restfulness",
                   contributors_timing AS "Timing",
                   contributors_total_sleep AS "Total Sleep"
            FROM daily_sleep
            WHERE day <= :end
            ORDER BY day DESC LIMIT 1
        """, {"end": end_date})

    @st.cache_data(ttl=300, show_spinner=False)
    def steps_30d(_self, end_date: date) -> pd.DataFrame:
        from datetime import timedelta
        start = end_date - timedelta(days=30)
        return query_df("""
            SELECT day, steps FROM daily_activity
            WHERE day >= :start AND day <= :end ORDER BY day
        """, {"start": start, "end": end_date})

    @st.cache_data(ttl=300, show_spinner=False)
    def spo2_trend(_self, start: date, end: date) -> pd.DataFrame:
        return query_df("""
            SELECT day, NULLIF(spo2_percentage_average, 0) AS spo2
            FROM daily_spo2 WHERE day >= :start AND day <= :end ORDER BY day
        """, {"start": start, "end": end})

    @st.cache_data(ttl=300, show_spinner=False)
    def hrv_vs_readiness(_self, start: date, end: date) -> pd.DataFrame:
        return query_df("""
            SELECT dr.day, sp.average_hrv AS hrv, dr.score AS readiness
            FROM daily_readiness dr
            JOIN sleep_primary sp ON sp.day = dr.day - 1
            WHERE dr.day >= :start AND dr.day <= :end
            ORDER BY dr.day
        """, {"start": start, "end": end})

    @st.cache_data(ttl=300, show_spinner=False)
    def weekly_trends(_self, start: date, end: date) -> dict[str, pd.DataFrame]:
        result = {}
        for table, col, alias in [
            ("daily_sleep", "score", "sleep"),
            ("daily_readiness", "score", "readiness"),
            ("daily_activity", "steps", "steps"),
        ]:
            result[alias] = query_df(f"""
                SELECT date_trunc('week', day::timestamp) AS week,
                       AVG({col})::int AS value
                FROM {table}
                WHERE day >= :start AND day <= :end
                GROUP BY 1 ORDER BY 1
            """, {"start": start, "end": end})
        result["hrv"] = query_df("""
            SELECT date_trunc('week', day::timestamp) AS week,
                   AVG(average_hrv)::numeric(5,1) AS value
            FROM sleep_primary
            WHERE day >= :start AND day <= :end
            GROUP BY 1 ORDER BY 1
        """, {"start": start, "end": end})
        return result

    @st.cache_data(ttl=60, show_spinner=False)
    def sync_status(_self) -> pd.DataFrame:
        return query_df("""
            SELECT endpoint, last_sync_date, updated_at,
                   CASE WHEN now() - updated_at < interval '2 hours' THEN 'Fresh' ELSE 'Stale' END AS status
            FROM sync_log ORDER BY endpoint
        """)

    # ------------------------------------------------------------------
    # Sleep page
    # ------------------------------------------------------------------
    @st.cache_data(ttl=300, show_spinner=False)
    def available_nights(_self, start: date, end: date) -> list[date]:
        df = query_df("""
            SELECT DISTINCT day FROM sleep
            WHERE type = 'long_sleep' AND day >= :start AND day <= :end
            ORDER BY day DESC
        """, {"start": start, "end": end})
        return df["day"].tolist()

    @st.cache_data(ttl=300, show_spinner=False)
    def sleep_session(_self, night: date) -> dict | None:
        df = query_df("""
            SELECT * FROM sleep
            WHERE type = 'long_sleep' AND day = :night
            ORDER BY total_sleep DESC LIMIT 1
        """, {"night": night})
        return df.iloc[0].to_dict() if not df.empty else None

    @st.cache_data(ttl=300, show_spinner=False)
    def sleep_phases_pie(_self, night: date) -> dict:
        df = query_df("""
            SELECT deep_sleep/60.0 AS deep, light_sleep/60.0 AS light,
                   rem_sleep/60.0 AS rem, awake_time/60.0 AS awake
            FROM sleep WHERE type='long_sleep' AND day = :night
            ORDER BY total_sleep DESC LIMIT 1
        """, {"night": night})
        return df.iloc[0].to_dict() if not df.empty else {}

    @st.cache_data(ttl=300, show_spinner=False)
    def sleep_phases_stacked(_self, start: date, end: date) -> pd.DataFrame:
        return query_df("""
            SELECT day,
                   deep_sleep / 3600.0 AS deep,
                   light_sleep / 3600.0 AS light,
                   rem_sleep / 3600.0 AS rem,
                   awake_time / 3600.0 AS awake
            FROM sleep_primary
            WHERE day >= :start AND day <= :end
            ORDER BY day
        """, {"start": start, "end": end})

    @st.cache_data(ttl=300, show_spinner=False)
    def sleep_hrv_trend(_self, start: date, end: date) -> pd.DataFrame:
        return query_df("""
            SELECT day, average_hrv AS hrv
            FROM sleep_primary
            WHERE day >= :start AND day <= :end
            ORDER BY day
        """, {"start": start, "end": end})

    @st.cache_data(ttl=300, show_spinner=False)
    def sleep_resting_hr_trend(_self, start: date, end: date) -> pd.DataFrame:
        return query_df("""
            SELECT day, lowest_heart_rate AS hr
            FROM sleep_primary
            WHERE day >= :start AND day <= :end
            ORDER BY day
        """, {"start": start, "end": end})

    @st.cache_data(ttl=300, show_spinner=False)
    def sleep_efficiency_trend(_self, start: date, end: date) -> pd.DataFrame:
        return query_df("""
            SELECT day, efficiency
            FROM sleep_primary
            WHERE day >= :start AND day <= :end
            ORDER BY day
        """, {"start": start, "end": end})

    @st.cache_data(ttl=300, show_spinner=False)
    def sleep_contributors_table(_self, start: date, end: date) -> pd.DataFrame:
        return query_df("""
            SELECT day::text AS "Date",
                   contributors_deep_sleep AS "Deep Sleep",
                   contributors_efficiency AS "Efficiency",
                   contributors_latency AS "Latency",
                   contributors_rem_sleep AS "REM Sleep",
                   contributors_restfulness AS "Restfulness",
                   contributors_timing AS "Timing",
                   contributors_total_sleep AS "Total Sleep"
            FROM daily_sleep
            WHERE day >= :start AND day <= :end
            ORDER BY day DESC
        """, {"start": start, "end": end})

    @st.cache_data(ttl=300, show_spinner=False)
    def sleep_latency_trend(_self, start: date, end: date) -> pd.DataFrame:
        return query_df("""
            SELECT day, latency / 60.0 AS latency_min
            FROM sleep_primary
            WHERE day >= :start AND day <= :end
            ORDER BY day
        """, {"start": start, "end": end})

    @st.cache_data(ttl=300, show_spinner=False)
    def sleep_breathing_trend(_self, start: date, end: date) -> pd.DataFrame:
        return query_df("""
            SELECT day, average_breath AS breath
            FROM sleep_primary
            WHERE day >= :start AND day <= :end
            ORDER BY day
        """, {"start": start, "end": end})

    @st.cache_data(ttl=300, show_spinner=False)
    def optimal_bedtime(_self, end_date: date) -> dict:
        df = query_df("""
            SELECT optimal_bedtime_start, optimal_bedtime_end, recommendation
            FROM sleep_time WHERE day <= :end ORDER BY day DESC LIMIT 1
        """, {"end": end_date})
        return df.iloc[0].to_dict() if not df.empty else {}

    @st.cache_data(ttl=300, show_spinner=False)
    def nap_frequency(_self, start: date, end: date) -> pd.DataFrame:
        return query_df("""
            SELECT day, count(*) AS naps
            FROM sleep WHERE type IN ('late_nap', 'sleep')
            AND day >= :start AND day <= :end
            GROUP BY day ORDER BY day
        """, {"start": start, "end": end})

    # ------------------------------------------------------------------
    # Readiness page
    # ------------------------------------------------------------------
    @st.cache_data(ttl=300, show_spinner=False)
    def readiness_latest(_self, end_date: date) -> dict:
        df = query_df("""
            SELECT score, temperature_deviation,
                   contributors_activity_balance AS "Activity Balance",
                   contributors_body_temperature AS "Body Temp",
                   contributors_hrv_balance AS "HRV Balance",
                   contributors_previous_day_activity AS "Prev Day Activity",
                   contributors_previous_night AS "Previous Night",
                   contributors_recovery_index AS "Recovery Index",
                   contributors_resting_heart_rate AS "Resting HR",
                   contributors_sleep_balance AS "Sleep Balance",
                   contributors_sleep_regularity AS "Sleep Regularity"
            FROM daily_readiness WHERE day <= :end ORDER BY day DESC LIMIT 1
        """, {"end": end_date})
        return df.iloc[0].to_dict() if not df.empty else {}

    @st.cache_data(ttl=300, show_spinner=False)
    def readiness_trend(_self, start: date, end: date) -> pd.DataFrame:
        return query_df("""
            SELECT day, score FROM daily_readiness
            WHERE day >= :start AND day <= :end ORDER BY day
        """, {"start": start, "end": end})

    @st.cache_data(ttl=300, show_spinner=False)
    def readiness_contributors_trend(_self, start: date, end: date) -> pd.DataFrame:
        return query_df("""
            SELECT day,
                   contributors_hrv_balance AS "HRV Balance",
                   contributors_sleep_balance AS "Sleep Balance",
                   contributors_recovery_index AS "Recovery Index",
                   contributors_resting_heart_rate AS "Resting HR",
                   contributors_sleep_regularity AS "Sleep Regularity"
            FROM daily_readiness
            WHERE day >= :start AND day <= :end ORDER BY day
        """, {"start": start, "end": end})

    @st.cache_data(ttl=300, show_spinner=False)
    def readiness_temp_trend(_self, start: date, end: date) -> pd.DataFrame:
        return query_df("""
            SELECT day, temperature_deviation AS temp
            FROM daily_readiness
            WHERE day >= :start AND day <= :end ORDER BY day
        """, {"start": start, "end": end})

    # ------------------------------------------------------------------
    # Activity page
    # ------------------------------------------------------------------
    @st.cache_data(ttl=300, show_spinner=False)
    def activity_latest(_self, end_date: date) -> dict:
        df = query_df("""
            SELECT score, active_calories, total_calories, steps,
                   equivalent_walking_distance / 1000.0 AS distance_km,
                   high_activity_time / 3600.0 AS high_h,
                   medium_activity_time / 3600.0 AS medium_h,
                   low_activity_time / 3600.0 AS low_h,
                   sedentary_time / 3600.0 AS sedentary_h,
                   resting_time / 3600.0 AS resting_h,
                   average_met_minutes,
                   contributors_meet_daily_targets AS "Daily Targets",
                   contributors_move_every_hour AS "Move Hourly",
                   contributors_recovery_time AS "Recovery Time",
                   contributors_stay_active AS "Stay Active",
                   contributors_training_frequency AS "Training Freq",
                   contributors_training_volume AS "Training Volume",
                   target_calories, target_meters
            FROM daily_activity WHERE day <= :end ORDER BY day DESC LIMIT 1
        """, {"end": end_date})
        return df.iloc[0].to_dict() if not df.empty else {}

    @st.cache_data(ttl=300, show_spinner=False)
    def activity_trend(_self, start: date, end: date) -> pd.DataFrame:
        return query_df("""
            SELECT day, active_calories, total_calories, steps,
                   NULLIF(score, 0) AS score,
                   equivalent_walking_distance / 1000.0 AS distance_km,
                   average_met_minutes AS met,
                   target_calories, target_meters
            FROM daily_activity
            WHERE day >= :start AND day <= :end ORDER BY day
        """, {"start": start, "end": end})

    @st.cache_data(ttl=300, show_spinner=False)
    def workouts(_self, start: date, end: date) -> pd.DataFrame:
        return query_df("""
            SELECT day, activity, calories, distance,
                   start_datetime, end_datetime, intensity, source
            FROM workout
            WHERE day >= :start AND day <= :end
            ORDER BY day DESC, start_datetime DESC
        """, {"start": start, "end": end})

    # ------------------------------------------------------------------
    # Body page
    # ------------------------------------------------------------------
    @st.cache_data(ttl=300, show_spinner=False)
    def stress_latest(_self, end_date: date) -> dict:
        df = query_df("""
            SELECT day_summary, stress_high, recovery_high
            FROM daily_stress
            WHERE day <= :end ORDER BY day DESC LIMIT 1
        """, {"end": end_date})
        return df.iloc[0].to_dict() if not df.empty else {}

    @st.cache_data(ttl=300, show_spinner=False)
    def stress_trend(_self, start: date, end: date) -> pd.DataFrame:
        return query_df("""
            SELECT day, stress_high / 3600.0 AS stress_h,
                   recovery_high / 3600.0 AS recovery_h
            FROM daily_stress
            WHERE day >= :start AND day <= :end ORDER BY day
        """, {"start": start, "end": end})

    @st.cache_data(ttl=300, show_spinner=False)
    def resilience_latest(_self, end_date: date) -> dict:
        df = query_df("""
            SELECT level,
                   contributors_sleep_recovery AS "Sleep Recovery",
                   contributors_daytime_recovery AS "Daytime Recovery",
                   contributors_stress AS "Stress"
            FROM daily_resilience WHERE day <= :end ORDER BY day DESC LIMIT 1
        """, {"end": end_date})
        return df.iloc[0].to_dict() if not df.empty else {}

    @st.cache_data(ttl=300, show_spinner=False)
    def resilience_timeline(_self, start: date, end: date) -> pd.DataFrame:
        return query_df("""
            SELECT day, level FROM daily_resilience
            WHERE day >= :start AND day <= :end ORDER BY day
        """, {"start": start, "end": end})

    @st.cache_data(ttl=300, show_spinner=False)
    def cardio_age_trend(_self, start: date, end: date) -> pd.DataFrame:
        return query_df("""
            SELECT day, vascular_age FROM daily_cardiovascular_age
            WHERE day >= :start AND day <= :end ORDER BY day
        """, {"start": start, "end": end})

    @st.cache_data(ttl=300, show_spinner=False)
    def vo2_max_trend(_self, start: date, end: date) -> pd.DataFrame:
        return query_df("""
            SELECT day, vo2_max FROM daily_vo2_max
            WHERE day >= :start AND day <= :end ORDER BY day
        """, {"start": start, "end": end})

    @st.cache_data(ttl=300, show_spinner=False)
    def spo2_latest(_self, end_date: date) -> dict:
        df = query_df("""
            SELECT NULLIF(spo2_percentage_average, 0) AS spo2,
                   breathing_disturbance_index AS bdi
            FROM daily_spo2 WHERE day <= :end ORDER BY day DESC LIMIT 1
        """, {"end": end_date})
        return df.iloc[0].to_dict() if not df.empty else {}
