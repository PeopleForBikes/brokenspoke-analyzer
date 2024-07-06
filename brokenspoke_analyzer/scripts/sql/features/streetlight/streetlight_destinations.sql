----------------------------------------
-- INPUTS
-- location: neighborhood
-- Prepares a table to be exported to StreetLightData
----------------------------------------
DROP TABLE IF EXISTS neighborhood_streetlight_destinations;
CREATE TABLE generated.neighborhood_streetlight_destinations (
    id SERIAL PRIMARY KEY,
    geom GEOMETRY (MULTIPOLYGON, 4326),
    name TEXT,
    blockid10 TEXT,
    is_pass INT
);

INSERT INTO neighborhood_streetlight_destinations (
    blockid10,
    name,
    geom,
    is_pass
)
-- noqa: disable=AL08
SELECT
    blocks.blockid10,
    blocks.blockid10,
    -- Transform to 4326, this is what StreetLightData expects
    ST_Transform(blocks.geom, 4326), -- noqa: AL03
    0 -- noqa: AL03
FROM neighborhood_census_blocks AS blocks,
    neighborhood_boundary AS b
WHERE ST_Intersects(blocks.geom, b.geom);
-- noqa: enable=all
