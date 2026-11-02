----------------------------------------
-- INPUTS
-- location: neighborhood
----------------------------------------
UPDATE received.neighborhood_ways_intersections
SET legs = (
    SELECT COUNT(neighborhood_ways.road_id)
    FROM neighborhood_ways
    WHERE
        neighborhood_ways_intersections.int_id IN (
            neighborhood_ways.intersection_from,
            neighborhood_ways.intersection_to
        )
);
