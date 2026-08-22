----------------------------------------
-- INPUTS
-- location: neighborhood
-- data downloaded from http://lehd.ces.census.gov/data/
-- or http://lehd.ces.census.gov/data/lodes/LODES8/
--     "ma_od_main_jt00_{year}".csv
--     ma_od_aux_jt00_{year}.csv
-- import to DB and check the block id to have 15 characters
-- also aggregate so 1 block has 1 number of total jobs
--     (total jobs comes from S000 field
--     as per https://lehd.ces.census.gov/doc/help/onthemap/LODESTechDoc.pdf
----------------------------------------

-- indexes
CREATE INDEX IF NOT EXISTS tidx_auxjtw ON state_od_aux_jt00 (w_geocode);
CREATE INDEX IF NOT EXISTS tidx_mainjtw ON state_od_main_jt00 (w_geocode);
ANALYZE state_od_aux_jt00 (w_geocode);
ANALYZE state_od_main_jt00 (w_geocode);

-- create combined table
DROP TABLE IF EXISTS generated.neighborhood_census_block_jobs;
CREATE TABLE generated.neighborhood_census_block_jobs (
    id SERIAL PRIMARY KEY,
    blockid20 VARCHAR(15),
    jobs INT
);

-- add blocks of interest
INSERT INTO generated.neighborhood_census_block_jobs (blockid20)
SELECT blocks.geoid20
FROM neighborhood_census_blocks AS blocks;

-- add main data
UPDATE generated.neighborhood_census_block_jobs
SET jobs = coalesce((
    SELECT sum(j.s000)
    FROM state_od_main_jt00 AS j
    WHERE j.w_geocode = neighborhood_census_block_jobs.blockid20
), 0);

-- add aux data
UPDATE generated.neighborhood_census_block_jobs
SET
    jobs = jobs
    + coalesce((
        SELECT sum(j.s000)
        FROM state_od_aux_jt00 AS j
        WHERE j.w_geocode = neighborhood_census_block_jobs.blockid20
    ), 0);

-- indexes
CREATE INDEX IF NOT EXISTS idx_neighborhood_blkjobs
ON neighborhood_census_block_jobs (
    blockid20
);
ANALYZE neighborhood_census_block_jobs (blockid20);
