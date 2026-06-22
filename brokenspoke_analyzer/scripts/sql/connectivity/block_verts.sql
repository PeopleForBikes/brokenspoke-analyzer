----------------------------------------
-- INPUTS
-- location: neighborhood
--
-- Transient seed table for the per-block reachability search. Maps each census
-- block to the network vertices of its road_ids. The boundary filter is required to
-- exactly match the filter used in the reachable roads calculation.
----------------------------------------
DROP TABLE IF EXISTS generated.neighborhood_block_verts;

CREATE TABLE generated.neighborhood_block_verts AS
SELECT
    cb.geoid20,
    v.vert_id
FROM neighborhood_census_blocks AS cb
CROSS JOIN LATERAL unnest(cb.road_ids) AS rid (road_id)
INNER JOIN neighborhood_ways_net_vert AS v ON rid.road_id = v.road_id
INNER JOIN neighborhood_ways AS w ON rid.road_id = w.road_id
WHERE EXISTS (
    SELECT 1
    FROM neighborhood_boundary AS b
    WHERE ST_Intersects(b.geom, w.geom)
);

CREATE INDEX idx_neighborhood_block_verts_geoid
ON generated.neighborhood_block_verts (geoid20);
ANALYZE generated.neighborhood_block_verts;
