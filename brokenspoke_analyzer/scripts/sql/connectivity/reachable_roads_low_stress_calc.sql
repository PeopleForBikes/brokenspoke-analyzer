----------------------------------------
-- INPUTS
-- location: neighborhood
-- :nb_max_trip_distance psql var must be set before running this script,
--      e.g. psql -v nb_max_trip_distance=2680 -v road_id=1 -f reachable_roads_low_stress_calc.sql
----------------------------------------
INSERT INTO generated.neighborhood_reachable_roads_low_stress (
    base_road,
    target_road,
    total_cost
)
SELECT
    r1.road_id,
    v2.road_id, -- noqa: AL08
    sheds.agg_cost
FROM neighborhood_ways AS r1,
    neighborhood_ways_net_vert AS v1,
    neighborhood_ways_net_vert AS v2,
    -- WHERE clause for neighborhood_ways_net_link based on road_id?
    PGR_DRIVINGDISTANCE(
        '
            SELECT  link_id AS id,
                    source_vert AS source,
                    target_vert AS target,
                    link_cost AS cost
            FROM    neighborhood_ways_net_link
            WHERE   link_stress = 1',
        v1.vert_id,
        :nb_max_trip_distance,
        directed := true -- noqa: RF02
    ) AS sheds
WHERE
    r1.road_id = :road_id
    AND
    EXISTS (
        SELECT 1
        FROM neighborhood_boundary AS b
        WHERE ST_Intersects(b.geom, r1.geom)
    )
    AND r1.road_id = v1.road_id
    AND v2.vert_id = sheds.node;
