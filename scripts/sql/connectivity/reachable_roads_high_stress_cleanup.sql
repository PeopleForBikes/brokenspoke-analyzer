CREATE UNIQUE INDEX IF NOT EXISTS idx_neighborhood_rchblrdshistrss_b ON generated.neighborhood_reachable_roads_high_stress (base_road, target_road);
CREATE INDEX IF NOT EXISTS idx_neighborhood_rchblrdshistrss_t ON generated.neighborhood_reachable_roads_high_stress (target_road);
-- VACUUM ANALYZE generated.neighborhood_reachable_roads_high_stress;
