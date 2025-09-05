DROP TABLE IF EXISTS generated.neighborhood_connected_census_blocks;

CREATE TABLE generated.neighborhood_connected_census_blocks (
    id SERIAL PRIMARY KEY,
    source_blockid10 VARCHAR(15),
    target_blockid10 VARCHAR(15),
    low_stress BOOLEAN,
    low_stress_cost INT,
    high_stress BOOLEAN,
    high_stress_cost INT
);
