----------------------------------------
-- INPUTS
-- location: neighborhood
----------------------------------------
CREATE INDEX IF NOT EXISTS idx_neighborhood_rchblrdslowstrss_b
ON generated.neighborhood_reachable_roads_low_stress (
    source_block, target_road
);
ANALYZE generated.neighborhood_reachable_roads_low_stress;
