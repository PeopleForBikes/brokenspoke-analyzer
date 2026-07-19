CREATE FUNCTION low_order_segment_stress(
    bike_infra text,
    speed_limit integer,
    lanes integer
)
RETURNS integer
LANGUAGE sql
IMMUTABLE
AS $$
WITH params AS (
    SELECT CASE
        WHEN one_way THEN 2
        ELSE 4
    END AS lane_threshold
)
SELECT CASE
    -- protected bike lane
    WHEN bike_infra = 'track' THEN 1
    -- conventional or buffered bike lane
    WHEN bike_infra = 'lane' OR bike_infra = 'buffered_lane' 
        THEN CASE
            WHEN speed_limit > 25 THEN 3
            ELSE 1
        END
    -- shared lane
    ELSE
        CASE
            WHEN speed_limit <= 25 AND lanes = 1 THEN 1
            ELSE 3
        END
END;
$$;
