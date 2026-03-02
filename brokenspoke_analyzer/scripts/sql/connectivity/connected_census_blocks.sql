----------------------------------------
-- INPUTS
-- location: neighborhood
----------------------------------------
-- set low_stress
UPDATE generated.neighborhood_connected_census_blocks
SET low_stress = TRUE
WHERE EXISTS (
    SELECT 1
    FROM neighborhood_census_blocks AS source,
        neighborhood_census_blocks AS target
    WHERE
        neighborhood_connected_census_blocks.source_blockid20 = source.geoid20
        AND neighborhood_connected_census_blocks.target_blockid20
        = target.geoid20
        AND source.road_ids && target.road_ids
)
OR (
    low_stress_cost IS NOT NULL
    AND CASE
        WHEN COALESCE(high_stress_cost, 0) = 0 THEN TRUE
        ELSE low_stress_cost::FLOAT / high_stress_cost <= 1.25
    END
);

-- indexes
CREATE UNIQUE INDEX idx_neighborhood_blockpairs
ON neighborhood_connected_census_blocks (
    source_blockid20, target_blockid20
);
CREATE INDEX IF NOT EXISTS idx_neighborhood_blockpairs_lstress
ON neighborhood_connected_census_blocks (
    source_blockid20, target_blockid20, low_stress
);
ANALYZE neighborhood_connected_census_blocks;
