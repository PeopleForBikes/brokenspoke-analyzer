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
        neighborhood_connected_census_blocks.source_blockid10 = source.blockid10
        AND neighborhood_connected_census_blocks.target_blockid10
        = target.blockid10
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
    source_blockid10, target_blockid10
);
CREATE INDEX IF NOT EXISTS idx_neighborhood_blockpairs_lstress
ON neighborhood_connected_census_blocks (
    low_stress
) WHERE low_stress IS TRUE;
CREATE INDEX IF NOT EXISTS idx_neighborhood_blockpairs_hstress
ON neighborhood_connected_census_blocks (
    high_stress
) WHERE high_stress IS TRUE;
ANALYZE neighborhood_connected_census_blocks;
