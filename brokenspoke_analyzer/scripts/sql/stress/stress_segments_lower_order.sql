----------------------------------------
-- Stress ratings for:
--      residential
--      unclassified
-- Input variables:
--      :class -> functional class to operate on
--      :default_speed -> assumed speed limit
--      :default_lanes -> assumed number of lanes
----------------------------------------
UPDATE received.neighborhood_ways SET ft_seg_stress = NULL, tf_seg_stress = NULL
WHERE functional_class = ':class';

UPDATE received.neighborhood_ways
SET
    ft_seg_stress
    = CASE
        WHEN COALESCE(speed_limit, :default_speed) <= 25 THEN 1
        ELSE 3
    END,
    tf_seg_stress
    = CASE
        WHEN COALESCE(speed_limit, :default_speed) <= 25 THEN 1
        ELSE 3
    END
WHERE functional_class = ':class';
