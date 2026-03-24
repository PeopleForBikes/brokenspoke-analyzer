----------------------------------------
-- INPUTS
-- location: neighborhood
-- proj: :nb_output_srid psql var must be set before running this script,
-- :cluster_tolerance psql var must be set before running this script.
--       e.g. psql -v nb_output_srid=2163 cluster_tolerance=50 -f retail.sql
----------------------------------------
DROP TABLE IF EXISTS generated.neighborhood_retail;

CREATE TABLE generated.neighborhood_retail (
    id SERIAL PRIMARY KEY,
    blockid20 CHARACTER VARYING(15) [],
    pop_low_stress INT,
    pop_high_stress INT,
    pop_score FLOAT,
    geom_pt GEOMETRY (POINT, :nb_output_srid),
    geom_poly GEOMETRY (MULTIPOLYGON, :nb_output_srid)
);

-- insert
INSERT INTO generated.neighborhood_retail (
    geom_poly
)
SELECT
    ST_Multi(
        ST_Buffer(
            ST_CollectionExtract(
                unnest(
                    ST_ClusterWithin(
                        (
                            SELECT array_agg(geom)
                            FROM (
                                SELECT way AS geom
                                FROM neighborhood_osm_full_polygon
                                WHERE
                                    landuse = 'retail'
                                    OR building = 'retail'
                                    OR (
                                        shop IS NOT NULL
                                        AND shop NOT IN ('no', 'supermarket')
                                    )

                                UNION ALL

                                SELECT ST_Buffer(way, 10) AS geom
                                FROM neighborhood_osm_full_point
                                WHERE
                                    shop IS NOT NULL
                                    AND shop NOT IN ('no', 'supermarket')
                            ) AS combined
                        ),
                        :cluster_tolerance
                    )
                ),
                3
            ),
            0
        )
    );

-- set points on polygons
UPDATE generated.neighborhood_retail
SET geom_pt = ST_Centroid(geom_poly);

-- index
CREATE INDEX sidx_neighborhood_retail_geomply
ON neighborhood_retail USING gist (
    geom_poly
);
ANALYZE generated.neighborhood_retail (geom_poly);

-- set blockid20
UPDATE generated.neighborhood_retail
SET blockid20 = array((
    SELECT cb.geoid20
    FROM neighborhood_census_blocks AS cb
    WHERE ST_Intersects(neighborhood_retail.geom_poly, cb.geom)
));

-- block index
CREATE INDEX IF NOT EXISTS aidx_neighborhood_retail_blockid20
ON neighborhood_retail USING gin (
    blockid20
);
ANALYZE generated.neighborhood_retail (blockid20);
