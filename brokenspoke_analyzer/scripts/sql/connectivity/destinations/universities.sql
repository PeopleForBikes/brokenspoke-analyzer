----------------------------------------
-- INPUTS
-- location: neighborhood
-- proj: :nb_output_srid psql var must be set before running this script,
-- :cluster_tolerance psql var must be set before running this script.
--       e.g. psql -v nb_output_srid=2163 -v cluster_tolerance=50 -f universities.sql
----------------------------------------
DROP TABLE IF EXISTS generated.neighborhood_universities;

CREATE TABLE generated.neighborhood_universities (
    id SERIAL PRIMARY KEY,
    blockid20 CHARACTER VARYING(15) [],
    osm_id BIGINT,
    college_name TEXT,
    pop_low_stress INT,
    pop_high_stress INT,
    pop_score FLOAT,
    geom_pt GEOMETRY (POINT, :nb_output_srid),
    geom_poly GEOMETRY (MULTIPOLYGON, :nb_output_srid)
);

-- insert polygons
INSERT INTO generated.neighborhood_universities (
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
WHERE amenity = 'university';

-- set points on polygons
UPDATE generated.neighborhood_universities
SET geom_pt = ST_Centroid(geom_poly);

-- index
CREATE INDEX sidx_neighborhood_universities_geomply
ON neighborhood_universities USING gist (
    geom_poly
);
ANALYZE neighborhood_universities (geom_poly);

-- insert points
INSERT INTO generated.neighborhood_universities (
    osm_id, college_name, geom_pt
)
SELECT
    osm_id,
    name,
    way
FROM neighborhood_osm_full_point
WHERE
    amenity = 'university'
    AND NOT EXISTS (
        SELECT 1
        FROM neighborhood_universities AS s
        WHERE ST_Intersects(s.geom_poly, neighborhood_osm_full_point.way)
    );

-- index
CREATE INDEX sidx_neighborhood_universities_geompt
ON neighborhood_universities USING gist (
    geom_pt
);
ANALYZE generated.neighborhood_universities (geom_pt);

-- set blockid20
UPDATE generated.neighborhood_universities
SET blockid20 = array((
    SELECT cb.geoid20
    FROM neighborhood_census_blocks AS cb
    WHERE
        ST_Intersects(neighborhood_universities.geom_poly, cb.geom)
        OR ST_Intersects(neighborhood_universities.geom_pt, cb.geom)
));

-- block index
CREATE INDEX IF NOT EXISTS aidx_neighborhood_universities_blockid20
ON neighborhood_universities USING gin (
    blockid20
);
ANALYZE generated.neighborhood_universities (blockid20);
