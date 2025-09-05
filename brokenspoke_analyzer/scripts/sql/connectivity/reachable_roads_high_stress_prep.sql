----------------------------------------
-- INPUTS
-- location: neighborhood
----------------------------------------
DROP TABLE IF EXISTS generated.neighborhood_reachable_roads_high_stress;

CREATE TABLE generated.neighborhood_reachable_roads_high_stress (
    base_road INT,
    target_road INT,
    total_cost INT
);

CREATE INDEX IF NOT EXISTS tsidx_neighborhood_ways_net_link_geoms ON
neighborhood_ways_net_link USING gist (geom);
