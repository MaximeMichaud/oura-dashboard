-- Synthetic data used only by CI browser validation.
BEGIN;

CREATE TEMP TABLE ci_days ON COMMIT DROP AS
SELECT offset_days, CURRENT_DATE - offset_days AS day
FROM generate_series(0, 89) AS offset_days;

INSERT INTO daily_sleep (
    day, score, contributors_deep_sleep, contributors_efficiency,
    contributors_latency, contributors_rem_sleep, contributors_restfulness,
    contributors_timing, contributors_total_sleep
)
SELECT
    day, 70 + offset_days % 25, 65 + offset_days % 30, 72 + offset_days % 24,
    68 + offset_days % 27, 66 + offset_days % 29, 64 + offset_days % 31,
    71 + offset_days % 25, 69 + offset_days % 28
FROM ci_days
ON CONFLICT (day) DO NOTHING;

INSERT INTO daily_readiness (
    day, score, temperature_deviation, temperature_trend_deviation,
    contributors_activity_balance, contributors_body_temperature,
    contributors_hrv_balance, contributors_previous_day_activity,
    contributors_previous_night, contributors_recovery_index,
    contributors_resting_heart_rate, contributors_sleep_balance,
    contributors_sleep_regularity
)
SELECT
    day, 68 + offset_days % 28, ((offset_days % 9) - 4) / 20.0,
    ((offset_days % 7) - 3) / 30.0, 65 + offset_days % 30,
    72 + offset_days % 24, 63 + offset_days % 32, 67 + offset_days % 29,
    70 + offset_days % 26, 66 + offset_days % 30, 69 + offset_days % 27,
    64 + offset_days % 31, 62 + offset_days % 33
FROM ci_days
ON CONFLICT (day) DO NOTHING;

INSERT INTO daily_activity (
    day, score, active_calories, total_calories, steps,
    equivalent_walking_distance, low_activity_time, medium_activity_time,
    high_activity_time, resting_time, sedentary_time, non_wear_time,
    average_met_minutes, high_activity_met_minutes, medium_activity_met_minutes,
    low_activity_met_minutes, sedentary_met_minutes, inactivity_alerts,
    target_calories, target_meters, meters_to_target,
    contributors_meet_daily_targets, contributors_move_every_hour,
    contributors_recovery_time, contributors_stay_active,
    contributors_training_frequency, contributors_training_volume
)
SELECT
    day, 67 + offset_days % 30, 250 + (offset_days * 17) % 500,
    1900 + (offset_days * 23) % 700, 5000 + (offset_days * 419) % 9000,
    3500 + (offset_days * 211) % 8000, 7200 + offset_days * 30,
    2400 + offset_days * 20, 600 + offset_days * 10, 28800,
    28000 - offset_days * 40, 0, 1.2 + (offset_days % 12) / 10.0,
    20 + offset_days % 50, 70 + offset_days % 90, 140 + offset_days % 120,
    400 + offset_days % 180, offset_days % 4, 450, 8000,
    GREATEST(0, 8000 - (3500 + (offset_days * 211) % 8000)),
    65 + offset_days % 30, 68 + offset_days % 28, 70 + offset_days % 26,
    63 + offset_days % 32, 66 + offset_days % 29, 64 + offset_days % 31
FROM ci_days
ON CONFLICT (day) DO NOTHING;

INSERT INTO daily_spo2 (day, spo2_percentage_average, breathing_disturbance_index)
SELECT day, 94.5 + (offset_days % 10) / 10.0, 1.0 + (offset_days % 12) / 4.0
FROM ci_days
ON CONFLICT (day) DO NOTHING;

INSERT INTO daily_stress (day, stress_high, recovery_high, day_summary)
SELECT
    day, 1800 + (offset_days % 12) * 300, 1200 + (offset_days % 10) * 240,
    (ARRAY['normal', 'restored', 'stressful'])[1 + offset_days % 3]
FROM ci_days
ON CONFLICT (day) DO NOTHING;

INSERT INTO daily_resilience (
    day, level, contributors_sleep_recovery,
    contributors_daytime_recovery, contributors_stress
)
SELECT
    day, (ARRAY['adequate', 'solid', 'strong'])[1 + offset_days % 3],
    45 + offset_days % 45, 40 + offset_days % 50, 42 + offset_days % 48
FROM ci_days
ON CONFLICT (day) DO NOTHING;

INSERT INTO daily_cardiovascular_age (day, vascular_age)
SELECT day, 30 + offset_days % 5
FROM ci_days
ON CONFLICT (day) DO NOTHING;

INSERT INTO daily_vo2_max (day, vo2_max)
SELECT day, 40.0 + (offset_days % 15) / 2.0
FROM ci_days
ON CONFLICT (day) DO NOTHING;

WITH samples AS (
    SELECT
        jsonb_agg(50 + sample % 16 ORDER BY sample) AS heart_rate,
        jsonb_agg(35 + sample % 30 ORDER BY sample) AS hrv
    FROM generate_series(1, 96) AS sample
)
INSERT INTO sleep (
    id, day, bedtime_start, bedtime_end, duration, total_sleep, awake_time,
    light_sleep, deep_sleep, rem_sleep, restless_periods, efficiency, latency,
    type, average_breath, average_heart_rate, average_hrv, lowest_heart_rate,
    heart_rate, hrv, sleep_phase_5_min
)
SELECT
    'ci-sleep-' || offset_days, day,
    day::timestamp AT TIME ZONE 'UTC' - INTERVAL '1 hour',
    day::timestamp AT TIME ZONE 'UTC' + INTERVAL '7 hours',
    28800, 27000, 1800, 14000, 6500, 6500, 12 + offset_days % 8,
    88 + offset_days % 8, 300 + offset_days % 600, 'long_sleep',
    13.5 + (offset_days % 8) / 10.0, 54 + offset_days % 8,
    42 + offset_days % 20, 45 + offset_days % 6,
    samples.heart_rate, samples.hrv,
    repeat('2', 40) || repeat('1', 20) || repeat('3', 24) || repeat('4', 12)
FROM ci_days
CROSS JOIN samples
ON CONFLICT (id) DO NOTHING;

INSERT INTO sleep (
    id, day, bedtime_start, bedtime_end, duration, total_sleep,
    awake_time, light_sleep, deep_sleep, rem_sleep, efficiency, latency, type
)
SELECT
    'ci-nap-' || offset_days, day,
    day::timestamp AT TIME ZONE 'UTC' + INTERVAL '15 hours',
    day::timestamp AT TIME ZONE 'UTC' + INTERVAL '15 hours 40 minutes',
    2400, 2100, 300, 1200, 300, 600, 88, 180, 'late_nap'
FROM ci_days
WHERE offset_days < 30 AND offset_days % 3 = 0
ON CONFLICT (id) DO NOTHING;

INSERT INTO sleep_time (
    id, day, optimal_bedtime_start, optimal_bedtime_end,
    optimal_bedtime_tz, recommendation, status
)
SELECT
    'ci-sleep-time-' || offset_days, day, -2700, 1800, 0,
    'follow_optimal_bedtime', 'optimal_found'
FROM ci_days
ON CONFLICT (id) DO NOTHING;

INSERT INTO workout (
    id, day, activity, calories, distance, start_datetime,
    end_datetime, intensity, label, source
)
SELECT
    'ci-workout-' || offset_days, day,
    (ARRAY['walking', 'running', 'cycling'])[1 + offset_days % 3],
    180 + offset_days * 8, 3000 + offset_days * 250,
    day::timestamp AT TIME ZONE 'UTC' + INTERVAL '12 hours',
    day::timestamp AT TIME ZONE 'UTC' + INTERVAL '12 hours 45 minutes',
    (ARRAY['easy', 'moderate', 'hard'])[1 + offset_days % 3],
    'CI workout', 'manual'
FROM ci_days
WHERE offset_days < 20
ON CONFLICT (id) DO NOTHING;

WITH points AS (
    SELECT
        sample_time,
        row_number() OVER (ORDER BY sample_time) AS sample_number
    FROM generate_series(
        date_trunc('hour', now()) - INTERVAL '30 days',
        date_trunc('hour', now()),
        INTERVAL '30 minutes'
    ) AS sample_time
)
INSERT INTO heartrate (timestamp, producer_timestamp, timestamp_unix, bpm, source)
SELECT
    sample_time, EXTRACT(epoch FROM sample_time)::bigint * 1000,
    EXTRACT(epoch FROM sample_time)::bigint,
    48 + sample_number % 70,
    (ARRAY['awake', 'rest', 'workout'])[1 + sample_number % 3]
FROM points
ON CONFLICT (timestamp) DO NOTHING;

WITH points AS (
    SELECT
        sample_time,
        row_number() OVER (ORDER BY sample_time) AS sample_number
    FROM generate_series(
        date_trunc('hour', now()) - INTERVAL '30 days',
        date_trunc('hour', now()),
        INTERVAL '6 hours'
    ) AS sample_time
)
INSERT INTO ring_battery_level (
    timestamp, producer_timestamp, timestamp_unix, charging, in_charger, level
)
SELECT
    sample_time, EXTRACT(epoch FROM sample_time)::bigint * 1000,
    EXTRACT(epoch FROM sample_time)::bigint,
    sample_number % 16 < 2, sample_number % 16 < 2,
    10 + (sample_number * 7) % 90
FROM points
ON CONFLICT (timestamp) DO NOTHING;

INSERT INTO ring_configuration (
    id, color, design, firmware_version, hardware_type, set_up_at, size
) VALUES (
    'ci-ring', 'silver', 'heritage', 'ci-1.0.0', 'gen4', now() - INTERVAL '1 year', 9
)
ON CONFLICT (id) DO NOTHING;

INSERT INTO personal_info (id, age, weight, height, biological_sex)
VALUES ('ci-profile', 35, 72.0, 1.75, 'other')
ON CONFLICT (id) DO NOTHING;

INSERT INTO session (
    id, day, start_datetime, end_datetime, type, mood
)
SELECT
    'ci-session-' || offset_days, day,
    day::timestamp AT TIME ZONE 'UTC' + INTERVAL '18 hours',
    day::timestamp AT TIME ZONE 'UTC' + INTERVAL '18 hours 15 minutes',
    (ARRAY['meditation', 'breathing'])[1 + offset_days % 2],
    (ARRAY['good', 'neutral'])[1 + offset_days % 2]
FROM ci_days
WHERE offset_days < 12
ON CONFLICT (id) DO NOTHING;

INSERT INTO tag (id, day, timestamp, text, tags)
SELECT
    'ci-tag-' || offset_days, day,
    day::timestamp AT TIME ZONE 'UTC' + INTERVAL '10 hours',
    'Synthetic CI tag', '["ci"]'::jsonb
FROM ci_days
WHERE offset_days < 12
ON CONFLICT (id) DO NOTHING;

INSERT INTO enhanced_tag (
    id, tag_type_code, start_time, end_time, start_day, end_day, comment, custom_name
)
SELECT
    'ci-enhanced-tag-' || offset_days, 'ci_tag',
    day::timestamp AT TIME ZONE 'UTC' + INTERVAL '14 hours',
    day::timestamp AT TIME ZONE 'UTC' + INTERVAL '15 hours',
    day, day, 'Synthetic CI enhanced tag', 'CI event'
FROM ci_days
WHERE offset_days < 8
ON CONFLICT (id) DO NOTHING;

INSERT INTO rest_mode_period (
    id, start_day, end_day, start_time, end_time, episodes
) VALUES (
    'ci-rest-mode', CURRENT_DATE - 20, CURRENT_DATE - 18,
    now() - INTERVAL '20 days', now() - INTERVAL '18 days', '[]'::jsonb
)
ON CONFLICT (id) DO NOTHING;

INSERT INTO sync_log (
    endpoint, last_sync_date, record_count, updated_at,
    last_error, consecutive_failures, last_success_at
)
SELECT endpoint, CURRENT_DATE, 90, now(), NULL, 0, now()
FROM unnest(ARRAY[
    'sleep', 'daily_sleep', 'daily_readiness', 'daily_activity', 'daily_spo2',
    'daily_stress', 'daily_resilience', 'daily_cardiovascular_age',
    'daily_vo2_max', 'workout', 'sleep_time', 'heartrate',
    'ring_battery_level', 'ring_configuration', 'session', 'tag',
    'enhanced_tag', 'rest_mode_period', 'personal_info'
]) AS endpoint
ON CONFLICT (endpoint) DO UPDATE SET
    last_sync_date = EXCLUDED.last_sync_date,
    record_count = EXCLUDED.record_count,
    updated_at = EXCLUDED.updated_at,
    last_error = NULL,
    consecutive_failures = 0,
    last_success_at = EXCLUDED.last_success_at;

REFRESH MATERIALIZED VIEW sleep_primary;

COMMIT;
