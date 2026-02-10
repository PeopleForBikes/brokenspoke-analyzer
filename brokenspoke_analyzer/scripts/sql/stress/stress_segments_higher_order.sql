----------------------------------------
-- Stress ratings for:
--      motorway
--      trunk
--      primary
--      secondary
--      tertiary
--      (and all _links)
-- Input variables:
--      :class -> functional class to operate on
--      :default_speed -> assumed speed limit
--      :default_lanes -> assumed number of lanes
----------------------------------------
UPDATE neighborhood_ways SET ft_seg_stress = NULL, tf_seg_stress = NULL
WHERE functional_class IN (':class', ':class' || '_link');

-- ft direction
UPDATE neighborhood_ways
SET
    ft_seg_stress
    = CASE
        -- protected bike lane
        WHEN ft_bike_infra = 'track' THEN 1

        -- buffered bike lane
        WHEN ft_bike_infra = 'buffered_lane'
            THEN CASE
                -- speed limit > 25
                WHEN COALESCE(speed_limit, :default_speed) > 25 THEN 3
                WHEN COALESCE(speed_limit, :default_speed) <= 25
                    THEN CASE
                        WHEN COALESCE(ft_lanes, :default_lanes) > 1 THEN 3
                        ELSE 1
                    END
                ELSE 3
            END

        WHEN ft_bike_infra = 'lane'
            THEN CASE
                -- speed limit > 25
                WHEN
                    COALESCE(speed_limit, :default_speed) > 25
                    THEN 3
                WHEN COALESCE(speed_limit, :default_speed) <= 25
                    THEN CASE
                        WHEN
                            COALESCE(ft_lanes, :default_lanes) > 1
                            THEN 3
                        ELSE 1
                    END
                ELSE 3
            END

        ELSE                -- shared lane
            CASE
                WHEN COALESCE(speed_limit, :default_speed) <= 15
                    THEN CASE
                        WHEN COALESCE(ft_lanes, :default_lanes) = 1 THEN 1
                        ELSE 3
                    END
                ELSE 3
            END
    END,

    tf_seg_stress
    = CASE
        -- protected bike lane
        WHEN tf_bike_infra = 'track' THEN 1

        -- buffered bike lane
        WHEN tf_bike_infra = 'buffered_lane'
            THEN CASE
                -- speed limit > 25
                WHEN COALESCE(speed_limit, :default_speed) > 25 THEN 3
                WHEN COALESCE(speed_limit, :default_speed) <= 25
                    THEN CASE
                        WHEN COALESCE(tf_lanes, :default_lanes) > 1 THEN 3
                        ELSE 1
                    END
                ELSE 3
            END

        WHEN tf_bike_infra = 'lane'
            THEN CASE
                -- speed limit > 25
                WHEN
                    COALESCE(speed_limit, :default_speed) > 25
                    THEN 3
                WHEN COALESCE(speed_limit, :default_speed) <= 25
                    THEN CASE
                        WHEN
                            COALESCE(tf_lanes, :default_lanes) > 1
                            THEN 3
                        ELSE 1
                    END
                ELSE 3
            END
        ELSE                -- shared lane
            CASE
                WHEN COALESCE(speed_limit, :default_speed) <= 15
                    THEN CASE
                        WHEN COALESCE(tf_lanes, :default_lanes) = 1 THEN 1
                        ELSE 3
                    END
                ELSE 3
            END
    END
WHERE functional_class IN (':class', ':class' || '_link');
