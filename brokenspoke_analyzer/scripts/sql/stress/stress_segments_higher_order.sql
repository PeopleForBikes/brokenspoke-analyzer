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
--      :default_parking -> assumed parking 1/0
--      :default_parking_width -> assumed parking lane width
--      :default_facility_width -> assumed width of bike facility
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
      
        -- bike lane with no parking
        WHEN ft_bike_infra = 'lane' AND COALESCE(ft_park, :default_parking) = 0
            THEN CASE
                WHEN COALESCE(speed_limit, :default_speed) > 20 THEN 3
                WHEN COALESCE(speed_limit, :default_speed) <= 20
                    THEN CASE
                        WHEN COALESCE(ft_lanes, :default_lanes) > 1 THEN 3
                        ELSE 1
                    END
                ELSE 3
            END
        
        WHEN ft_bike_infra = 'lane' AND COALESCE(ft_park, :default_parking) = 1
            THEN CASE
                -- treat as conventional lane
                WHEN COALESCE(ft_bike_infra_width, :default_facility_width)
                    + :default_parking_width >= 12
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
                ELSE 3 -- less than 12 ft
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
      
        -- bike lane with no parking
        WHEN tf_bike_infra = 'lane' AND COALESCE(tf_park, :default_parking) = 0
            THEN CASE
                WHEN COALESCE(speed_limit, :default_speed) > 20 THEN 3
                WHEN COALESCE(speed_limit, :default_speed) <= 20
                    THEN CASE
                        WHEN COALESCE(tf_lanes, :default_lanes) > 1 THEN 3
                        ELSE 1
                    END
                ELSE 3
            END
        
        WHEN tf_bike_infra = 'lane' AND COALESCE(ft_park, :default_parking) = 1
            THEN CASE
                -- treat as conventional lane
                WHEN COALESCE(tf_bike_infra_width, :default_facility_width)
                    + :default_parking_width >= 12
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
                ELSE 3 -- less than 12 ft
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
