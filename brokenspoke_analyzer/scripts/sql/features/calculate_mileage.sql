-- Create a new table to store the total mileage by feature type
CREATE TABLE IF NOT EXISTS mileage (
    feature_type VARCHAR(50),
    total_mileage FLOAT
);

-- Insert the calculated total mileage into the new table
INSERT INTO mileage (feature_type, total_mileage)
SELECT
    neighborhood_ways.ft_bike_infra AS feature_type,
    SUM(ST_Length(neighborhood_ways.geom) / 1609.34) AS total_mileage
FROM
    neighborhood_ways
WHERE
    neighborhood_ways.ft_bike_infra IN
    ('sharrow', 'buffered_lane', 'lane', 'track')
GROUP BY
    neighborhood_ways.ft_bike_infra
UNION ALL
SELECT
    neighborhood_ways.tf_bike_infra AS feature_type,
    SUM(ST_Length(neighborhood_ways.geom) / 1609.34) AS total_mileage
FROM
    neighborhood_ways
WHERE
    neighborhood_ways.tf_bike_infra IN
    ('sharrow', 'buffered_lane', 'lane', 'track')
GROUP BY
    neighborhood_ways.tf_bike_infra;
