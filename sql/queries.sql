-- Queries used in the notebook (SQLite).
-- Tables: schedule, rooms

-- name: classes_per_day
SELECT
    day,
    COUNT(*)                     AS classes,
    SUM(duration_hours)          AS room_hours,
    COUNT(DISTINCT class_group)  AS class_groups
FROM schedule
GROUP BY day
ORDER BY CASE day WHEN 'Mon' THEN 1 WHEN 'Tue' THEN 2 WHEN 'Wed' THEN 3
                  WHEN 'Thu' THEN 4 WHEN 'Fri' THEN 5 ELSE 6 END;

-- name: classes_per_program
SELECT
    program,
    COUNT(*)                     AS classes,
    SUM(duration_hours)          AS room_hours
FROM schedule
GROUP BY program
ORDER BY room_hours DESC;

-- name: classes_by_start_time
SELECT
    start_time,
    COUNT(*) AS classes
FROM schedule
WHERE day <> 'Sat'
GROUP BY start_time
ORDER BY start_time;

-- name: busiest_slots
-- Build every 30-minute slot from 06:30 to 18:00, then count classes running in each one.
WITH RECURSIVE slots(t) AS (
    SELECT 390
    UNION ALL
    SELECT t + 30 FROM slots WHERE t < 1080
),
classes AS (
    SELECT day,
           CAST(substr(start_time, 1, 2) AS INT) * 60 + CAST(substr(start_time, 4, 2) AS INT) AS s,
           CAST(substr(end_time, 1, 2) AS INT) * 60 + CAST(substr(end_time, 4, 2) AS INT)     AS e
    FROM schedule
)
SELECT
    c.day,
    printf('%02d:%02d', sl.t / 60, sl.t % 60) AS slot,
    COUNT(*)                                  AS rooms_in_use
FROM slots sl
JOIN classes c ON c.s <= sl.t AND c.e > sl.t
GROUP BY c.day, sl.t
ORDER BY rooms_in_use DESC
LIMIT 10;

-- name: overtime_classes
-- Ends after 17:30. The late-night Saturday row is left out (likely input error).
SELECT day, start_time, end_time, COUNT(*) AS classes
FROM schedule
WHERE end_time > '17:30' AND start_time < '18:00'
GROUP BY day, start_time, end_time
ORDER BY CASE day WHEN 'Mon' THEN 1 WHEN 'Tue' THEN 2 WHEN 'Wed' THEN 3
                  WHEN 'Thu' THEN 4 WHEN 'Fri' THEN 5 ELSE 6 END, start_time;

-- name: utilization_by_floor
-- 55 hours = Monday to Friday, 06:30 to 17:30. Overtime hours are counted here,
-- so this runs slightly higher than the Python version, which only counts operating hours.
SELECT
    r.floor,
    COUNT(DISTINCT r.room_id)                                                   AS rooms,
    SUM(s.duration_hours)                                                       AS booked_hours,
    ROUND(SUM(s.duration_hours) * 100.0 / (COUNT(DISTINCT r.room_id) * 55), 1)  AS utilization_pct
FROM rooms r
LEFT JOIN schedule s ON s.room_id = r.room_id AND s.day <> 'Sat'
GROUP BY r.floor;

-- ------------------------------------------------------------------
-- Window functions
-- ------------------------------------------------------------------

-- name: room_rank_by_floor
-- Rank rooms by booked hours inside each floor, and compare each room with its floor average.
WITH booked AS (
    SELECT r.room_id, r.floor, COALESCE(SUM(s.duration_hours), 0) AS booked_hours
    FROM rooms r
    LEFT JOIN schedule s ON s.room_id = r.room_id AND s.day <> 'Sat'
    GROUP BY r.room_id, r.floor
)
SELECT
    floor,
    room_id,
    booked_hours,
    RANK() OVER (PARTITION BY floor ORDER BY booked_hours DESC)          AS rank_in_floor,
    ROUND(booked_hours - AVG(booked_hours) OVER (PARTITION BY floor), 1) AS vs_floor_avg
FROM booked
ORDER BY floor, rank_in_floor;

-- name: peak_slot_per_day
-- The busiest 30-minute slot of each day (ties: the earliest).
WITH RECURSIVE slots(t) AS (
    SELECT 390 UNION ALL SELECT t + 30 FROM slots WHERE t < 1080
),
classes AS (
    SELECT day,
           CAST(substr(start_time, 1, 2) AS INT) * 60 + CAST(substr(start_time, 4, 2) AS INT) AS s,
           CAST(substr(end_time, 1, 2) AS INT) * 60 + CAST(substr(end_time, 4, 2) AS INT)     AS e
    FROM schedule
    WHERE start_time < '18:00'
),
per_slot AS (
    SELECT c.day, sl.t, COUNT(*) AS rooms_in_use
    FROM slots sl JOIN classes c ON c.s <= sl.t AND c.e > sl.t
    GROUP BY c.day, sl.t
),
ranked AS (
    SELECT day, t, rooms_in_use,
           ROW_NUMBER() OVER (PARTITION BY day ORDER BY rooms_in_use DESC, t) AS rn
    FROM per_slot
)
SELECT day, printf('%02d:%02d', t / 60, t % 60) AS busiest_slot, rooms_in_use
FROM ranked
WHERE rn = 1
ORDER BY CASE day WHEN 'Mon' THEN 1 WHEN 'Tue' THEN 2 WHEN 'Wed' THEN 3
                  WHEN 'Thu' THEN 4 WHEN 'Fri' THEN 5 ELSE 6 END;

-- name: overtime_share_by_program
-- Which study programs have the most classes ending after 17:30, as a share of their weekday classes.
SELECT
    program,
    COUNT(*)                                                                AS weekday_classes,
    SUM(CASE WHEN end_time > '17:30' THEN 1 ELSE 0 END)                     AS overtime_classes,
    ROUND(100.0 * SUM(CASE WHEN end_time > '17:30' THEN 1 ELSE 0 END) / COUNT(*), 1) AS overtime_pct,
    SUM(SUM(CASE WHEN end_time > '17:30' THEN 1 ELSE 0 END)) OVER ()        AS overtime_total
FROM schedule
WHERE day <> 'Sat'
GROUP BY program
HAVING overtime_classes > 0
ORDER BY overtime_classes DESC;

-- name: gaps_between_classes
-- Free time between consecutive classes in the same room (LAG), the windows that suit short bookings.
WITH ordered AS (
    SELECT room_id, day, start_time, end_time,
           LAG(end_time) OVER (PARTITION BY room_id, day ORDER BY start_time) AS prev_end
    FROM schedule
    WHERE day <> 'Sat'
)
SELECT
    room_id, day, prev_end AS free_from, start_time AS free_until,
    (CAST(substr(start_time, 1, 2) AS INT) * 60 + CAST(substr(start_time, 4, 2) AS INT)
     - CAST(substr(prev_end, 1, 2) AS INT) * 60 - CAST(substr(prev_end, 4, 2) AS INT)) AS gap_minutes
FROM ordered
WHERE prev_end IS NOT NULL AND start_time > prev_end
ORDER BY gap_minutes DESC
LIMIT 10;
