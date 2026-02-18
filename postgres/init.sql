-- Oura Dashboard - PostgreSQL Schema
-- All tables are idempotent (IF NOT EXISTS)

CREATE TABLE IF NOT EXISTS sleep (
    id              TEXT PRIMARY KEY,
    day             DATE NOT NULL,
    bedtime_start   TIMESTAMPTZ,
    bedtime_end     TIMESTAMPTZ,
    duration        INTEGER,          -- seconds
    total_sleep     INTEGER,          -- seconds
    awake_time      INTEGER,          -- seconds
    light_sleep     INTEGER,          -- seconds
    deep_sleep      INTEGER,          -- seconds
    rem_sleep       INTEGER,          -- seconds
    restless_periods INTEGER,
    efficiency       INTEGER,         -- percent
    latency         INTEGER,          -- seconds
    type            TEXT,             -- long_sleep, late_nap, rest, sleep
    readiness_score_delta INTEGER,
    average_breath  REAL,
    average_heart_rate REAL,
    average_hrv     REAL,
    lowest_heart_rate INTEGER,
    heart_rate      JSONB,            -- 5-min interval HR
    hrv             JSONB,            -- 5-min interval HRV
    sleep_phase_5_min TEXT,           -- encoded sleep phases string
    movement_30_sec TEXT,             -- 30-sec movement classification (1=no motion, 2=restless, 3=tossing, 4=active)
    sleep_score_delta REAL,
    period          INTEGER,          -- sleep period identifier
    low_battery_alert BOOLEAN,
    updated_at      TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_sleep_day ON sleep(day);
CREATE INDEX IF NOT EXISTS idx_sleep_day_type ON sleep(day, type);

CREATE TABLE IF NOT EXISTS daily_sleep (
    day                     DATE PRIMARY KEY,
    score                   INTEGER,
    contributors_deep_sleep INTEGER,
    contributors_efficiency INTEGER,
    contributors_latency    INTEGER,
    contributors_rem_sleep  INTEGER,
    contributors_restfulness INTEGER,
    contributors_timing     INTEGER,
    contributors_total_sleep INTEGER,
    updated_at              TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS daily_readiness (
    day                              DATE PRIMARY KEY,
    score                            INTEGER,
    temperature_deviation            REAL,
    temperature_trend_deviation      REAL,
    contributors_activity_balance    INTEGER,
    contributors_body_temperature    INTEGER,
    contributors_hrv_balance         INTEGER,
    contributors_previous_day_activity INTEGER,
    contributors_previous_night      INTEGER,
    contributors_recovery_index      INTEGER,
    contributors_resting_heart_rate  INTEGER,
    contributors_sleep_balance       INTEGER,
    contributors_sleep_regularity    INTEGER,
    updated_at                       TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS daily_activity (
    day                                  DATE PRIMARY KEY,
    score                                INTEGER,
    active_calories                      INTEGER,
    total_calories                       INTEGER,
    steps                                INTEGER,
    equivalent_walking_distance          INTEGER,  -- meters
    low_activity_time                    INTEGER,  -- seconds
    medium_activity_time                 INTEGER,  -- seconds
    high_activity_time                   INTEGER,  -- seconds
    resting_time                         INTEGER,  -- seconds
    sedentary_time                       INTEGER,  -- seconds
    non_wear_time                        INTEGER,  -- seconds
    average_met_minutes                  REAL,
    high_activity_met_minutes            INTEGER,
    medium_activity_met_minutes          INTEGER,
    low_activity_met_minutes             INTEGER,
    sedentary_met_minutes                INTEGER,
    inactivity_alerts                    INTEGER,
    target_calories                      INTEGER,
    target_meters                        INTEGER,
    meters_to_target                     INTEGER,
    contributors_meet_daily_targets     INTEGER,
    contributors_move_every_hour        INTEGER,
    contributors_recovery_time          INTEGER,
    contributors_stay_active            INTEGER,
    contributors_training_frequency     INTEGER,
    contributors_training_volume        INTEGER,
    updated_at                           TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS daily_spo2 (
    day                         DATE PRIMARY KEY,
    spo2_percentage_average     REAL,
    breathing_disturbance_index REAL,
    updated_at                  TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS daily_stress (
    day                 DATE PRIMARY KEY,
    stress_high         INTEGER,  -- seconds
    recovery_high       INTEGER,  -- seconds
    day_summary         TEXT,     -- restored, normal, stressful
    updated_at          TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS daily_resilience (
    day                         DATE PRIMARY KEY,
    level                       TEXT,     -- limited, adequate, solid, strong, exceptional
    contributors_sleep_recovery REAL,
    contributors_daytime_recovery REAL,
    contributors_stress         REAL,
    updated_at                  TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS daily_cardiovascular_age (
    day                 DATE PRIMARY KEY,
    vascular_age        INTEGER,
    updated_at          TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS daily_vo2_max (
    day                 DATE PRIMARY KEY,
    vo2_max             REAL,
    updated_at          TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS workout (
    id              TEXT PRIMARY KEY,
    day             DATE NOT NULL,
    activity        TEXT,
    calories        REAL,
    distance        REAL,             -- meters
    start_datetime  TIMESTAMPTZ,
    end_datetime    TIMESTAMPTZ,
    intensity       TEXT,             -- easy, moderate, hard
    label           TEXT,
    source          TEXT,             -- manual, autodetected, confirmed, workout_heart_rate
    updated_at      TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_workout_day ON workout(day);

CREATE TABLE IF NOT EXISTS sleep_time (
    id                      TEXT PRIMARY KEY,
    day                     DATE NOT NULL,
    optimal_bedtime_start   INTEGER,  -- seconds offset from midnight (negative = before midnight)
    optimal_bedtime_end     INTEGER,  -- seconds offset from midnight
    optimal_bedtime_tz      INTEGER,  -- timezone offset in seconds
    recommendation          TEXT,     -- improve_efficiency, earlier_bedtime, later_bedtime, etc.
    status                  TEXT,     -- not_enough_nights, optimal_found, etc.
    updated_at              TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_sleep_time_day ON sleep_time(day);

CREATE TABLE IF NOT EXISTS sync_log (
    endpoint        TEXT PRIMARY KEY,
    last_sync_date  DATE NOT NULL,
    record_count    INTEGER DEFAULT 0,
    updated_at      TIMESTAMPTZ DEFAULT now()
);
