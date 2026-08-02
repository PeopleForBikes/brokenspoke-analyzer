----------------------------------------
-- INPUTS
-- location: neighborhood
-- :nb_max_trip_distance, :thread_num and :thread_no psql vars must be set,
--      e.g. psql -v nb_max_trip_distance=2680 -v thread_num=8 -v thread_no=0 \
--              -f reachable_roads_high_stress_calc.sql
--
-- One search per block over the road network, seeded from
-- all the block's road verts via a 0-cost super-source (assigned id -1), giving the min cost to
-- each reachable road.
----------------------------------------
INSERT INTO generated.neighborhood_reachable_roads_high_stress (
    source_block,
    target_road,
    total_cost
)
SELECT
    cb.geoid20,
    v.road_id, -- noqa: AL08
    sheds.agg_cost
FROM neighborhood_census_blocks AS cb,
    neighborhood_ways_net_vert AS v,
    PGR_DRIVINGDISTANCE(
        '
            SELECT link_id AS id,
                   source_vert AS source,
                   target_vert AS target,
                   link_cost AS cost
            FROM   neighborhood_ways_net_link l
            WHERE  ST_DWithin(l.geom, ''' || ST_AsEWKT(cb.geom) || ''', ' || :nb_max_trip_distance + 100 || ')
            UNION ALL
            SELECT -row_number() OVER () AS id, -1 AS source, vert_id AS target, 0 AS cost
            FROM   generated.neighborhood_block_verts
            WHERE  geoid20 = ''' || cb.geoid20 || '''',
        -1,
        :nb_max_trip_distance,
        directed := true -- noqa: RF02
    ) AS sheds
WHERE
    ((HASHTEXT(cb.geoid20)::BIGINT % :thread_num) + :thread_num) % :thread_num
    = :thread_no
    AND EXISTS (
        SELECT 1
        FROM neighborhood_boundary AS b
        WHERE ST_Intersects(b.geom, cb.geom)
    )
    AND v.vert_id = sheds.node;
