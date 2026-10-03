----------------------------------------
-- Stress ratings for:
--      residential
--      unclassified
-- Input variables:
--      :class -> functional class to operate on
--      :default_speed -> assumed speed limit
--      :default_lanes -> assumed number of lanes
----------------------------------------
UPDATE received.neighborhood_ways
SET
    ft_seg_stress = low_order_segment_stress(
        ft_bike_infra,
        coalesce(speed_limit, :default_speed),
        coalesce(ft_lanes, :default_lanes)
    ),
    tf_seg_stress = low_order_segment_stress(
        tf_bike_infra,
        coalesce(speed_limit, :default_speed),
        coalesce(tf_lanes, :default_lanes)
    )
WHERE functional_class = ':class';
