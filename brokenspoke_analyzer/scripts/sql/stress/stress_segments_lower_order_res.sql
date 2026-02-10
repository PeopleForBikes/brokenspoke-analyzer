----------------------------------------
-- Stress ratings for:
--      residential
-- Input variables:
--      :class -> functional class to operate on
--      :default_lanes -> assumed number of lanes
--      :state_default -> state default residential speed
--      :city_default -> city default residential speed
----------------------------------------
UPDATE received.neighborhood_ways SET ft_seg_stress = NULL, tf_seg_stress = NULL
WHERE functional_class = ':class';

UPDATE received.neighborhood_ways
SET
    ft_seg_stress
    = CASE
        WHEN COALESCE(speed_limit, :city_default, :state_default) <= 25 THEN 1
        ELSE 3
    END,
    tf_seg_stress
    = CASE
        WHEN COALESCE(speed_limit, :city_default, :state_default) <= 25 THEN 1
        ELSE 3
    END
WHERE functional_class = ':class';
