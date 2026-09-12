----------------------------------------
-- INPUTS
-- location: neighborhood
----------------------------------------
DROP TABLE IF EXISTS generated.neighborhood_reachable_roads_low_stress;

-- Keyed source_block -> target_road: one row per (block, reachable road) with the
-- minimum low-stress cost from the block (over all of its roads) to that road.
CREATE TABLE generated.neighborhood_reachable_roads_low_stress (
    source_block VARCHAR(15),
    target_road INT,
    total_cost INT
);
