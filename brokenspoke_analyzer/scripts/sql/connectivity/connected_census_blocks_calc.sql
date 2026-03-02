----------------------------------------
-- INPUTS
-- location: neighborhood
-- :nb_max_trip_distance and :block_id psql vars must be set before running this script,
--      e.g. psql -v nb_max_trip_distance=2680 -v block_id=1 -f connected_census_blocks_calc.sql
----------------------------------------
INSERT INTO generated.neighborhood_connected_census_blocks (
    source_blockid20, target_blockid20,
    low_stress, low_stress_cost, high_stress, high_stress_cost
)
SELECT
    source.geoid20, -- noqa: AL08
    target.geoid20, -- noqa: AL08
    FALSE, -- noqa: AL03
    (
        SELECT MIN(ls.total_cost)
        FROM neighborhood_reachable_roads_low_stress AS ls
        WHERE
            ls.base_road = ANY(source.road_ids)
            AND ls.target_road = ANY(target.road_ids)
    ) AS min_ls_total_cost,
    TRUE, -- noqa: AL03
    (
        SELECT MIN(hs.total_cost)
        FROM neighborhood_reachable_roads_high_stress AS hs
        WHERE
            hs.base_road = ANY(source.road_ids)
            AND hs.target_road = ANY(target.road_ids)
    ) AS min_hs_total_cost
FROM neighborhood_census_blocks AS source,
    neighborhood_census_blocks AS target,
    neighborhood_boundary
WHERE
    ST_Intersects(source.geom, neighborhood_boundary.geom)
    AND source.geoid20 = :block_id
    AND ST_DWithin(source.geom, target.geom, :nb_max_trip_distance);
