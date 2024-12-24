----------------------------------------
-- INPUTS
-- location: neighborhood
----------------------------------------
UPDATE neighborhood_ways SET width_ft = NULL;

-- feet
UPDATE neighborhood_ways
SET width_ft = substring(osm.width FROM '\d+\.?\d?\d?')::FLOAT
FROM neighborhood_osm_full_line AS osm
WHERE
    neighborhood_ways.osm_id = osm.osm_id
    AND osm.width IS NOT NULL
    AND osm.width LIKE '% ft';

-- feet specified as X'Y" OR X'
UPDATE neighborhood_ways
SET
    width_ft = substring(osm.width FROM '(\d+)''')::FLOAT
    + coalesce(substring(osm.width FROM '(\d+)"')::FLOAT / 12, 0)
FROM neighborhood_osm_full_line AS osm
WHERE
    neighborhood_ways.osm_id = osm.osm_id
    AND osm.width IS NOT NULL
    AND (osm.width LIKE '%''%"' OR osm.width LIKE '%''');

-- meters
UPDATE neighborhood_ways
SET width_ft = 3.28084 * substring(osm.width FROM '\d+\.?\d?\d?')::FLOAT
FROM neighborhood_osm_full_line AS osm
WHERE
    neighborhood_ways.osm_id = osm.osm_id
    AND osm.width IS NOT NULL
    AND osm.width LIKE '% m';

-- no units (default=meters)
-- N.B. we weed out anything more than 20, since that's likely either bogus
-- or not in meters
UPDATE neighborhood_ways
SET width_ft = 3.28084 * substring(osm.width FROM '\d+\.?\d?\d?')::FLOAT
FROM neighborhood_osm_full_line AS osm
WHERE
    neighborhood_ways.osm_id = osm.osm_id
    AND neighborhood_ways.width_ft IS NULL
    AND osm.width IS NOT NULL
    AND substring(osm.width FROM '\d+\.?\d?\d?')::FLOAT < 20;
