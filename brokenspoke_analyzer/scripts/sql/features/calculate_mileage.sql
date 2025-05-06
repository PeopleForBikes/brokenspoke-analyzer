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
INSERT INTO mileage (feature_type, total_mileage)

SELECT
    all_features.feature_type,
    SUM(ST_Length(all_features.geom) / 1609.34) AS total_mileage
FROM (
    SELECT
        neighborhood_ways.geom,
        features.feature_type
    FROM neighborhood_ways,
        LATERAL (
            VALUES
            (neighborhood_ways.ft_bike_infra),
            (neighborhood_ways.tf_bike_infra)
        ) AS features (feature_type)
    WHERE features.feature_type IN ('sharrow', 'buffered_lane', 'lane', 'track')
) AS all_features
GROUP BY all_features.feature_type;
