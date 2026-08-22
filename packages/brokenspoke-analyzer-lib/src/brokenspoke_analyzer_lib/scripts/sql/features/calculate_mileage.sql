-- Create a new table to store the total mileage by feature type
CREATE TABLE IF NOT EXISTS mileage (
    feature_type VARCHAR(50),
    total_mileage FLOAT
);

-- Insert the calculated total mileage into the new table
-- Uses LATERAL so that for each row in neighborhood_ways,
-- we produce two rows — one for ft_bike_infra, and one for tf_bike_infra
-- if both are not NULL, otherwise just one row or now rows if both are NULL -
-- and place them in a column called feature_type
-- Only the length inside the city boundary is counted.
INSERT INTO mileage (feature_type, total_mileage)

WITH boundary AS (
    SELECT ST_Union(geom) AS geom FROM neighborhood_boundary
)

SELECT
    all_features.feature_type,
    SUM(
        ST_Length(ST_Intersection(all_features.geom, boundary.geom)) / 1609.34
    ) AS total_mileage
FROM (
    SELECT
        neighborhood_ways.geom,
        features.feature_type
    FROM neighborhood_ways,
        LATERAL (
            VALUES
            (neighborhood_ways.ft_bike_infra),
            (neighborhood_ways.tf_bike_infra),
            (
                CASE
                    WHEN
                        (
                            neighborhood_ways.functional_class = 'path'
                            AND neighborhood_ways.xwalk IS NULL
                            -- A path detected as a protected bike lane is
                            -- counted as 'track' only.
                            AND neighborhood_ways.ft_bike_infra
                            IS DISTINCT FROM 'track'
                            AND neighborhood_ways.tf_bike_infra
                            IS DISTINCT FROM 'track'
                        )
                        THEN 'path'
                END
            )
        ) AS features (feature_type)
    -- Sharrows are left out because they are not tagged consistently in OSM.
    WHERE
        features.feature_type IN ('buffered_lane', 'lane', 'track', 'path')
) AS all_features
INNER JOIN boundary ON ST_Intersects(all_features.geom, boundary.geom)
GROUP BY all_features.feature_type;
