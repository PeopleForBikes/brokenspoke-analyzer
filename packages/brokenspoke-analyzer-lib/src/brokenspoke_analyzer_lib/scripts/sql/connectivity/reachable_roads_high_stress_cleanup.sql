CREATE UNIQUE INDEX IF NOT EXISTS idx_neighborhood_rchblrdshistrss_b
ON generated.neighborhood_reachable_roads_high_stress (
    source_block, target_road
);
ANALYZE generated.neighborhood_reachable_roads_high_stress;
