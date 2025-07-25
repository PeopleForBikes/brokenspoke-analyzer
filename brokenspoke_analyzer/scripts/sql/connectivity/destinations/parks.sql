----------------------------------------
-- INPUTS
-- location: neighborhood
-- proj: :nb_output_srid psql var must be set before running this script,
-- :cluster_tolerance psql var must be set before running this script.
--       e.g. psql -v nb_output_srid=2163 cluster_tolerance=50 -f parks.sql
----------------------------------------
DROP TABLE IF EXISTS generated.neighborhood_parks;

CREATE TABLE generated.neighborhood_parks (
    id SERIAL PRIMARY KEY,
    blockid20 CHARACTER VARYING(15) [],
    osm_id BIGINT,
    park_name TEXT,
    pop_low_stress INT,
    pop_high_stress INT,
    pop_score FLOAT,
    geom_pt GEOMETRY (POINT, :nb_output_srid),
    geom_poly GEOMETRY (MULTIPOLYGON, :nb_output_srid)
);

-- insert polygons
INSERT INTO generated.neighborhood_parks (
    geom_poly
)
SELECT
    ST_Multi(
        ST_Buffer(
            ST_CollectionExtract(
                unnest(ST_ClusterWithin(way, :cluster_tolerance)), 3
            ),
            0
        )
    )
FROM neighborhood_osm_full_polygon
WHERE
    amenity = 'park'
    OR leisure = 'park'
    OR leisure = 'nature_reserve'
    OR leisure = 'playground';

-- set points on polygons
UPDATE generated.neighborhood_parks
SET geom_pt = ST_Centroid(geom_poly);

-- index
CREATE INDEX sidx_neighborhood_parks_geomply ON neighborhood_parks USING gist (
    geom_poly
);
ANALYZE neighborhood_parks (geom_poly);

-- insert points
INSERT INTO generated.neighborhood_parks (
    osm_id, park_name, geom_pt
)
SELECT
    osm_id,
    name,
    way
FROM neighborhood_osm_full_point
WHERE (
    amenity = 'park'
    OR leisure = 'park'
    OR leisure = 'nature_reserve'
    OR leisure = 'playground'
)
AND NOT EXISTS (
    SELECT 1
    FROM neighborhood_parks AS s
    WHERE ST_Intersects(s.geom_poly, neighborhood_osm_full_point.way)
);

-- index
CREATE INDEX sidx_neighborhood_parks_geompt ON neighborhood_parks USING gist (
    geom_pt
);
ANALYZE generated.neighborhood_parks (geom_pt);

-- set blockid20
UPDATE generated.neighborhood_parks
SET blockid20 = array((
    SELECT cb.geoid20
    FROM neighborhood_census_blocks AS cb
    WHERE
        ST_Intersects(neighborhood_parks.geom_poly, cb.geom)
        OR ST_Intersects(neighborhood_parks.geom_pt, cb.geom)
));

-- block index
CREATE INDEX IF NOT EXISTS aidx_neighborhood_parks_blockid20
ON neighborhood_parks USING gin (
    blockid20
);
ANALYZE generated.neighborhood_parks (blockid20);
