----------------------------------------
-- INPUTS
-- location: neighborhood
----------------------------------------
DROP TABLE IF EXISTS generated.neighborhood_reachable_roads_high_stress;

-- Keyed source_block -> target_road: one row per (block, reachable road) with the
-- minimum high-stress cost from the block (over all of its roads) to that road.
CREATE TABLE generated.neighborhood_reachable_roads_high_stress (
    source_block VARCHAR(15),
    target_road INT,
    total_cost INT
);

CREATE INDEX IF NOT EXISTS tsidx_neighborhood_ways_net_link_geoms ON
neighborhood_ways_net_link USING gist (geom);
