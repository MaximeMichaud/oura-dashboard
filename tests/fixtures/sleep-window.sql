-- Synthetic nights for scripts/validate-sleep-window.mjs. Use only a disposable database.
-- These fixed dates exercise both DST transitions and shifts longer than 99999 hours.
INSERT INTO sleep (id, day, type, bedtime_start, bedtime_end, total_sleep, sleep_phase_5_min)
SELECT
    'ci-window-' || day, day, 'long_sleep', bedtime, wake,
    EXTRACT(EPOCH FROM wake - bedtime)::integer,
    repeat('2', (EXTRACT(EPOCH FROM wake - bedtime) / 300)::integer)
FROM (VALUES
    (DATE '2026-11-01', TIMESTAMPTZ '2026-10-31 18:00-04', TIMESTAMPTZ '2026-11-01 12:00-05'),
    (DATE '2026-03-07', TIMESTAMPTZ '2026-03-06 22:00-05', TIMESTAMPTZ '2026-03-07 08:00-05'),
    (DATE '2026-10-31', TIMESTAMPTZ '2026-10-30 22:00-04', TIMESTAMPTZ '2026-10-31 08:00-04'),
    (DATE '2015-06-16', TIMESTAMPTZ '2015-06-15 22:00-04', TIMESTAMPTZ '2015-06-16 08:00-04'),
    (DATE '2026-11-13', TIMESTAMPTZ '2026-11-12 22:00-05', TIMESTAMPTZ '2026-11-13 07:00-05')
) AS nights(day, bedtime, wake)
ON CONFLICT (id) DO NOTHING;
