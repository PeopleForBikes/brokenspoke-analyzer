----------------------------------------
-- INPUTS
-- location: neighborhood
----------------------------------------
UPDATE neighborhood_ways SET ft_bike_infra = NULL, tf_bike_infra = NULL;

-- noqa: disable=RF05
----------------------
-- ft direction
----------------------
UPDATE neighborhood_ways
SET
    ft_bike_infra = CASE

        -- both
        WHEN osm."cycleway:both" = 'shared_lane'
            THEN 'sharrow'
        WHEN osm."cycleway:both" = 'buffered_lane'
            THEN 'buffered_lane'
        WHEN
            osm."cycleway:both" = 'lane'
            AND osm."cycleway:buffer" IN ('yes', 'both', 'right', 'left')
            THEN 'buffered_lane'
        WHEN
            osm."cycleway:both" = 'lane'
            AND osm."cycleway:both:buffer" IN ('yes', 'both', 'right', 'left')
            THEN 'buffered_lane'
        WHEN osm."cycleway:both" = 'lane'
            THEN 'lane'
        WHEN osm."cycleway:both" = 'track'
            THEN 'track'
        WHEN
            (
                osm."cycleway:right" = 'track'
                AND (
                    osm."oneway:bicycle" = 'no'
                    OR osm."cycleway:right:oneway" = 'no'
                )
            )
            THEN 'track'
        WHEN
            (
                osm."cycleway:left" = 'track'
                AND (
                    osm."oneway:bicycle" = 'no'
                    OR osm."cycleway:left:oneway" = 'no'
                )
            )
            THEN 'track'
        WHEN (osm.cycleway = 'track' AND osm."oneway:bicycle" = 'no')
            THEN 'track'

            -- one-way=ft
        WHEN one_way_car = 'ft'
            THEN CASE
                WHEN osm."cycleway:left" = 'shared_lane'
                    THEN 'sharrow'
                WHEN
                    osm."cycleway:left" = 'lane'
                    AND (
                        osm."cycleway:left:oneway" != '-1'
                        OR osm."cycleway:left:oneway" IS NULL
                    )
                    AND osm."cycleway:buffer" IN (
                        'yes', 'both', 'right', 'left'
                    )
                    THEN 'buffered_lane'
                WHEN
                    osm."cycleway:left" = 'lane'
                    AND (
                        osm."cycleway:left:oneway" != '-1'
                        OR osm."cycleway:left:oneway" IS NULL
                    )
                    AND osm."cycleway:left:buffer" IN (
                        'yes', 'both', 'right', 'left'
                    )
                    THEN 'buffered_lane'
                WHEN
                    osm."cycleway:left" = 'lane'
                    AND (
                        osm."cycleway:left:oneway" != '-1'
                        OR osm."cycleway:left:oneway" IS NULL
                    )
                    THEN 'lane'
                WHEN
                    osm."cycleway:left" = 'track'
                    AND (
                        osm."cycleway:left:oneway" != '-1'
                        OR osm."cycleway:left:oneway" IS NULL
                    )
                    THEN 'track'

                -- stuff from two-way that also applies to one-way=ft
                WHEN osm.cycleway = 'shared_lane'
                    THEN 'sharrow'
                WHEN osm."cycleway:right" = 'shared_lane'
                    THEN 'sharrow'
                WHEN osm.cycleway = 'buffered_lane'
                    THEN 'buffered_lane'
                WHEN
                    osm."cycleway:right" = 'buffered_lane'
                    AND (
                        osm."cycleway:right:oneway" != '-1'
                        OR osm."cycleway:right:oneway" IS NULL
                    )
                    THEN 'buffered_lane'
                WHEN
                    osm.cycleway = 'lane'
                    AND osm."cycleway:buffer" IN (
                        'yes', 'both', 'right', 'left'
                    )
                    THEN 'buffered_lane'
                WHEN
                    osm."cycleway:right" = 'lane'
                    AND (
                        osm."cycleway:right:oneway" != '-1'
                        OR osm."cycleway:right:oneway" IS NULL
                    )
                    AND osm."cycleway:buffer" IN (
                        'yes', 'both', 'right', 'left'
                    )
                    THEN 'buffered_lane'
                WHEN
                    osm."cycleway:right" = 'lane'
                    AND (
                        osm."cycleway:right:oneway" != '-1'
                        OR osm."cycleway:right:oneway" IS NULL
                    )
                    AND osm."cycleway:right:buffer" IN (
                        'yes', 'both', 'right', 'left'
                    )
                    THEN 'buffered_lane'
                WHEN osm.cycleway = 'lane'
                    THEN 'lane'
                WHEN
                    osm."cycleway:right" = 'lane'
                    AND (
                        osm."cycleway:right:oneway" != '-1'
                        OR osm."cycleway:right:oneway" IS NULL
                    )
                    THEN 'lane'
                WHEN osm.cycleway = 'track'
                    THEN 'track'
                WHEN
                    osm."cycleway:right" = 'track'
                    AND (
                        osm."cycleway:right:oneway" != '-1'
                        OR osm."cycleway:right:oneway" IS NULL
                    )
                    THEN 'track'
            END

            -- one-way=tf
        WHEN one_way_car = 'tf'
            THEN CASE
                WHEN
                    osm.cycleway = 'opposite_lane'
                    AND osm."cycleway:buffer" IN (
                        'yes', 'both', 'right', 'left'
                    )
                    THEN 'buffered_lane'
                WHEN
                    osm."cycleway:right" = 'opposite_lane'
                    AND osm."cycleway:buffer" IN (
                        'yes', 'both', 'right', 'left'
                    )
                    THEN 'buffered_lane'
                WHEN
                    osm."cycleway:right" = 'opposite_lane'
                    AND osm."cycleway:right:buffer" IN (
                        'yes', 'both', 'right', 'left'
                    )
                    THEN 'buffered_lane'
                WHEN
                    osm."cycleway:left:oneway" = '-1'
                    AND "cycleway:left" = 'track'
                    THEN 'track'
                WHEN
                    osm."cycleway:right:oneway" = '-1'
                    AND "cycleway:right" = 'track'
                    THEN 'track'
                WHEN
                    osm."cycleway:left:oneway" = '-1'
                    AND "cycleway:left" = 'lane'
                    AND "cycleway:left:buffer" = 'yes'
                    THEN 'buffered_lane'
                WHEN
                    osm."cycleway:right:oneway" = '-1'
                    AND "cycleway:right" = 'lane'
                    AND "cycleway:right:buffer" = 'yes'
                    THEN 'buffered_lane'
                WHEN
                    osm."cycleway:left:oneway" = '-1'
                    AND "cycleway:left" = 'lane'
                    THEN 'lane'
                WHEN
                    osm."cycleway:right:oneway" = '-1'
                    AND "cycleway:right" = 'lane'
                    THEN 'lane'
                WHEN osm.cycleway = 'opposite_lane'
                    THEN 'lane'
                WHEN osm."cycleway:right" = 'opposite_lane'
                    THEN 'lane'
                WHEN osm.cycleway = 'opposite_track'
                    THEN 'track'
                WHEN
                    (
                        one_way_car = 'tf'
                        AND osm."cycleway:left" = 'opposite_track'
                    )
                    THEN 'track'
                WHEN
                    (
                        one_way_car = 'tf'
                        AND osm."cycleway:right" = 'opposite_track'
                    )
                    THEN 'track'
            END

            -- two-way
        WHEN one_way_car IS NULL
            THEN CASE
                WHEN osm.cycleway = 'shared_lane'
                    THEN 'sharrow'
                WHEN osm."cycleway:right" = 'shared_lane'
                    THEN 'sharrow'
                WHEN osm.cycleway = 'buffered_lane'
                    THEN 'buffered_lane'
                WHEN osm."cycleway:right" = 'buffered_lane'
                    THEN 'buffered_lane'
                WHEN
                    osm.cycleway = 'lane'
                    AND osm."cycleway:buffer" IN (
                        'yes', 'both', 'right', 'left'
                    )
                    THEN 'buffered_lane'
                WHEN
                    osm."cycleway:right" = 'lane'
                    AND osm."cycleway:buffer" IN (
                        'yes', 'both', 'right', 'left'
                    )
                    THEN 'buffered_lane'
                WHEN
                    osm."cycleway:right" = 'lane'
                    AND osm."cycleway:right:buffer" IN (
                        'yes', 'both', 'right', 'left'
                    )
                    THEN 'buffered_lane'
                WHEN osm.cycleway = 'lane'
                    THEN 'lane'
                WHEN osm."cycleway:right" = 'lane'
                    THEN 'lane'
                WHEN osm.cycleway = 'track'
                    THEN 'track'
                WHEN osm."cycleway:right" = 'track'
                    THEN 'track'
            END
    END,

    tf_bike_infra = CASE

        -- both
        WHEN osm."cycleway:both" = 'shared_lane'
            THEN 'sharrow'
        WHEN osm."cycleway:both" = 'buffered_lane'
            THEN 'buffered_lane'
        WHEN
            osm."cycleway:both" = 'lane'
            AND osm."cycleway:buffer" IN ('yes', 'both', 'right', 'left')
            THEN 'buffered_lane'
        WHEN
            osm."cycleway:both" = 'lane'
            AND osm."cycleway:both:buffer" IN ('yes', 'both', 'right', 'left')
            THEN 'buffered_lane'
        WHEN osm."cycleway:both" = 'lane'
            THEN 'lane'
        WHEN osm."cycleway:both" = 'track'
            THEN 'track'
        WHEN
            (
                osm."cycleway:right" = 'track'
                AND (
                    osm."oneway:bicycle" = 'no'
                    OR osm."cycleway:right:oneway" = 'no'
                )
            )
            THEN 'track'
        WHEN
            (
                osm."cycleway:left" = 'track'
                AND (
                    osm."oneway:bicycle" = 'no'
                    OR osm."cycleway:left:oneway" = 'no'
                )
            )
            THEN 'track'
        WHEN (osm.cycleway = 'track' AND osm."oneway:bicycle" = 'no')
            THEN 'track'

            -- one-way=tf
        WHEN one_way_car = 'tf'
            THEN CASE
                WHEN osm."cycleway:right" = 'shared_lane'
                    THEN 'sharrow'
                WHEN
                    osm."cycleway:right" = 'lane'
                    AND (
                        osm."cycleway:right:oneway" != '-1'
                        OR osm."cycleway:right:oneway" IS NULL
                    )
                    AND osm."cycleway:buffer" IN (
                        'yes', 'both', 'right', 'left'
                    )
                    THEN 'buffered_lane'
                WHEN
                    osm."cycleway:right" = 'lane'
                    AND (
                        osm."cycleway:right:oneway" != '-1'
                        OR osm."cycleway:right:oneway" IS NULL
                    )
                    AND osm."cycleway:right:buffer" IN (
                        'yes', 'both', 'right', 'left'
                    )
                    THEN 'buffered_lane'
                WHEN
                    osm."cycleway:right" = 'lane'
                    AND (
                        osm."cycleway:right:oneway" != '-1'
                        OR osm."cycleway:right:oneway" IS NULL
                    )
                    THEN 'lane'
                WHEN
                    osm."cycleway:right" = 'track'
                    AND (
                        osm."cycleway:right:oneway" != '-1'
                        OR osm."cycleway:right:oneway" IS NULL
                    )
                    THEN 'track'

                -- stuff from two-way that also applies to one-way=tf
                WHEN osm.cycleway = 'shared_lane'
                    THEN 'sharrow'
                WHEN osm."cycleway:left" = 'shared_lane'
                    THEN 'sharrow'
                WHEN osm.cycleway = 'buffered_lane'
                    THEN 'buffered_lane'
                WHEN
                    osm."cycleway:left" = 'buffered_lane'
                    THEN 'buffered_lane'
                WHEN
                    osm.cycleway = 'lane'
                    AND (
                        osm."cycleway:left:oneway" != '-1'
                        OR osm."cycleway:left:oneway" IS NULL
                    )
                    AND osm."cycleway:buffer" IN (
                        'yes', 'both', 'right', 'left'
                    )
                    THEN 'buffered_lane'
                WHEN
                    osm."cycleway:left" = 'lane'
                    AND (
                        osm."cycleway:left:oneway" != '-1'
                        OR osm."cycleway:left:oneway" IS NULL
                    )
                    AND osm."cycleway:buffer" IN (
                        'yes', 'both', 'right', 'left'
                    )
                    THEN 'buffered_lane'
                WHEN
                    osm."cycleway:left" = 'lane'
                    AND (
                        osm."cycleway:left:oneway" != '-1'
                        OR osm."cycleway:left:oneway" IS NULL
                    )
                    AND osm."cycleway:left:buffer" IN (
                        'yes', 'both', 'right', 'left'
                    )
                    THEN 'buffered_lane'
                WHEN osm.cycleway = 'lane'
                    THEN 'lane'
                WHEN
                    osm."cycleway:left" = 'lane'
                    AND (
                        osm."cycleway:left:oneway" != '-1'
                        OR osm."cycleway:left:oneway" IS NULL
                    )
                    THEN 'lane'
                WHEN osm.cycleway = 'track'
                    THEN 'track'
                WHEN
                    osm."cycleway:left" = 'track'
                    AND (
                        osm."cycleway:left:oneway" != '-1'
                        OR osm."cycleway:left:oneway" IS NULL
                    )
                    THEN 'track'
            END

            -- one-way=ft
        WHEN one_way_car = 'ft'
            THEN CASE
                WHEN
                    osm.cycleway = 'opposite_lane'
                    AND osm."cycleway:buffer" IN (
                        'yes', 'both', 'right', 'left'
                    )
                    THEN 'buffered_lane'
                WHEN
                    osm."cycleway:right" = 'opposite_lane'
                    AND osm."cycleway:buffer" IN (
                        'yes', 'both', 'right', 'left'
                    )
                    THEN 'buffered_lane'
                WHEN
                    osm."cycleway:right" = 'opposite_lane'
                    AND osm."cycleway:right:buffer" IN (
                        'yes', 'both', 'right', 'left'
                    )
                    THEN 'buffered_lane'
                WHEN
                    osm."cycleway:left:oneway" = '-1'
                    AND "cycleway:left" = 'track'
                    THEN 'track'
                WHEN
                    osm."cycleway:right:oneway" = '-1'
                    AND "cycleway:right" = 'track'
                    THEN 'track'
                WHEN
                    osm."cycleway:left:oneway" = '-1'
                    AND "cycleway:left" = 'lane'
                    AND "cycleway:left:buffer" = 'yes'
                    THEN 'buffered_lane'
                WHEN
                    osm."cycleway:right:oneway" = '-1'
                    AND "cycleway:right" = 'lane'
                    AND "cycleway:right:buffer" = 'yes'
                    THEN 'buffered_lane'
                WHEN
                    osm."cycleway:left:oneway" = '-1'
                    AND "cycleway:left" = 'lane'
                    THEN 'lane'
                WHEN
                    osm."cycleway:right:oneway" = '-1'
                    AND "cycleway:right" = 'lane'
                    THEN 'lane'
                WHEN osm.cycleway = 'opposite_lane'
                    THEN 'lane'
                WHEN osm."cycleway:right" = 'opposite_lane'
                    THEN 'lane'
                WHEN osm.cycleway = 'opposite_track'
                    THEN 'track'
                WHEN
                    (
                        one_way_car = 'tf'
                        AND osm."cycleway:left" = 'opposite_track'
                    )
                    THEN 'track'
                WHEN
                    (
                        one_way_car = 'tf'
                        AND osm."cycleway:right" = 'opposite_track'
                    )
                    THEN 'track'
            END

            -- two-way
        WHEN one_way_car IS NULL
            THEN CASE
                WHEN osm.cycleway = 'shared_lane'
                    THEN 'sharrow'
                WHEN osm."cycleway:left" = 'shared_lane'
                    THEN 'sharrow'
                WHEN osm.cycleway = 'buffered_lane'
                    THEN 'buffered_lane'
                WHEN osm."cycleway:left" = 'buffered_lane'
                    THEN 'buffered_lane'
                WHEN
                    osm.cycleway = 'lane'
                    AND osm."cycleway:buffer" IN (
                        'yes', 'both', 'right', 'left'
                    )
                    THEN 'buffered_lane'
                WHEN
                    osm."cycleway:left" = 'lane'
                    AND osm."cycleway:buffer" IN (
                        'yes', 'both', 'right', 'left'
                    )
                    THEN 'buffered_lane'
                WHEN
                    osm."cycleway:left" = 'lane'
                    AND osm."cycleway:left:buffer" IN (
                        'yes', 'both', 'right', 'left'
                    )
                    THEN 'buffered_lane'
                WHEN osm.cycleway = 'lane'
                    THEN 'lane'
                WHEN osm."cycleway:left" = 'lane'
                    THEN 'lane'
                WHEN osm.cycleway = 'track'
                    THEN 'track'
                WHEN osm."cycleway:left" = 'track'
                    THEN 'track'
            END
    END
FROM neighborhood_osm_full_line AS osm
WHERE neighborhood_ways.osm_id = osm.osm_id;

-- update one_way based on bike infra
UPDATE neighborhood_ways
SET one_way = NULL;
UPDATE neighborhood_ways
SET one_way = one_way_car
FROM neighborhood_osm_full_line AS osm
WHERE
    neighborhood_ways.osm_id = osm.osm_id
    AND one_way_car = 'ft'
    AND NOT (
        tf_bike_infra IS NOT NULL
        OR COALESCE(osm."oneway:bicycle", 'yes') = 'no'
    );
UPDATE neighborhood_ways
SET one_way = one_way_car
FROM neighborhood_osm_full_line AS osm
WHERE
    neighborhood_ways.osm_id = osm.osm_id
    AND one_way_car = 'tf'
    AND NOT (
        ft_bike_infra IS NOT NULL
        OR COALESCE(osm."oneway:bicycle", 'yes') = 'no'
    );

-- get facility widths
UPDATE neighborhood_ways
SET
    ft_bike_infra_width = CASE

        -- feet
        WHEN osm."cycleway:right:width" LIKE '% ft'
            THEN SUBSTRING("cycleway:right:width" FROM '\d+\.?\d?\d?')::FLOAT
        WHEN one_way_car = 'ft' AND osm."cycleway:left:width" LIKE '% ft'
            THEN SUBSTRING("cycleway:left:width" FROM '\d+\.?\d?\d?')::FLOAT
        WHEN osm."cycleway:both:width" LIKE '% ft'
            THEN SUBSTRING("cycleway:both:width" FROM '\d+\.?\d?\d?')::FLOAT
        WHEN osm."cycleway:width" LIKE '% ft'
            THEN SUBSTRING("cycleway:width" FROM '\d+\.?\d?\d?')::FLOAT

            -- meters
        WHEN osm."cycleway:right:width" LIKE '% m'
            THEN
                3.28084
                * SUBSTRING("cycleway:right:width" FROM '\d+\.?\d?\d?')::FLOAT
        WHEN one_way_car = 'ft' AND osm."cycleway:left:width" LIKE '% m'
            THEN
                3.28084
                * SUBSTRING("cycleway:left:width" FROM '\d+\.?\d?\d?')::FLOAT
        WHEN osm."cycleway:both:width" LIKE '% m'
            THEN
                3.28084
                * SUBSTRING("cycleway:both:width" FROM '\d+\.?\d?\d?')::FLOAT
        WHEN osm."cycleway:width" LIKE '% m'
            THEN
                3.28084 * SUBSTRING("cycleway:width" FROM '\d+\.?\d?\d?')::FLOAT

        -- no units (default=meters)
        WHEN osm."cycleway:right:width" IS NOT NULL
            THEN
                3.28084
                * SUBSTRING("cycleway:right:width" FROM '\d+\.?\d?\d?')::FLOAT
        WHEN one_way_car = 'ft' AND osm."cycleway:left:width" IS NOT NULL
            THEN
                3.28084
                * SUBSTRING("cycleway:left:width" FROM '\d+\.?\d?\d?')::FLOAT
        WHEN osm."cycleway:both:width" IS NOT NULL
            THEN
                3.28084
                * SUBSTRING("cycleway:both:width" FROM '\d+\.?\d?\d?')::FLOAT
        WHEN osm."cycleway:width" IS NOT NULL
            THEN
                3.28084 * SUBSTRING("cycleway:width" FROM '\d+\.?\d?\d?')::FLOAT
    END
FROM neighborhood_osm_full_line AS osm
WHERE
    neighborhood_ways.osm_id = osm.osm_id
    AND ft_bike_infra IS NOT NULL;

UPDATE neighborhood_ways
SET
    tf_bike_infra_width = CASE

        -- feet
        WHEN osm."cycleway:left:width" LIKE '% ft'
            THEN SUBSTRING("cycleway:left:width" FROM '\d+\.?\d?\d?')::FLOAT
        WHEN one_way_car = 'tf' AND osm."cycleway:right:width" LIKE '% ft'
            THEN SUBSTRING("cycleway:right:width" FROM '\d+\.?\d?\d?')::FLOAT
        WHEN osm."cycleway:both:width" LIKE '% ft'
            THEN SUBSTRING("cycleway:both:width" FROM '\d+\.?\d?\d?')::FLOAT
        WHEN osm."cycleway:width" LIKE '% ft'
            THEN SUBSTRING("cycleway:width" FROM '\d+\.?\d?\d?')::FLOAT

            -- meters
        WHEN osm."cycleway:left:width" LIKE '% m'
            THEN
                3.28084
                * SUBSTRING("cycleway:left:width" FROM '\d+\.?\d?\d?')::FLOAT
        WHEN one_way_car = 'tf' AND osm."cycleway:right:width" LIKE '% m'
            THEN
                3.28084
                * SUBSTRING("cycleway:right:width" FROM '\d+\.?\d?\d?')::FLOAT
        WHEN osm."cycleway:both:width" LIKE '% m'
            THEN
                3.28084
                * SUBSTRING("cycleway:both:width" FROM '\d+\.?\d?\d?')::FLOAT
        WHEN osm."cycleway:width" LIKE '% m'
            THEN
                3.28084 * SUBSTRING("cycleway:width" FROM '\d+\.?\d?\d?')::FLOAT

        -- no units (default=meters)
        WHEN osm."cycleway:left:width" IS NOT NULL
            THEN
                3.28084
                * SUBSTRING("cycleway:left:width" FROM '\d+\.?\d?\d?')::FLOAT
        WHEN one_way_car = 'tf' AND osm."cycleway:right:width" IS NOT NULL
            THEN
                3.28084
                * SUBSTRING("cycleway:right:width" FROM '\d+\.?\d?\d?')::FLOAT
        WHEN osm."cycleway:both:width" IS NOT NULL
            THEN
                3.28084
                * SUBSTRING("cycleway:both:width" FROM '\d+\.?\d?\d?')::FLOAT
        WHEN osm."cycleway:width" IS NOT NULL
            THEN
                3.28084 * SUBSTRING("cycleway:width" FROM '\d+\.?\d?\d?')::FLOAT
    END
FROM neighborhood_osm_full_line AS osm
WHERE
    neighborhood_ways.osm_id = osm.osm_id
    AND tf_bike_infra IS NOT NULL;
-- noqa: enable=all

----------------------------------------
-- Protected bike lanes (PBL) mapped as separate paths
--
-- Label the parts of candidate paths that run alongside a car road at the
-- same level as 'track'. See specs/0004-pbl-refinement for the method.
----------------------------------------

-- Car roads, with their level (bridge, tunnel or ground).
CREATE TEMPORARY TABLE pbl_roads ON COMMIT DROP AS
WITH way_lvl AS (
    SELECT
        osm_id,
        MAX(
            CASE
                WHEN COALESCE(bridge, 'no') NOT IN ('no', 'boardwalk')
                    THEN 'bridge'
                WHEN COALESCE(tunnel, 'no') != 'no'
                    THEN 'tunnel'
                ELSE 'ground'
            END
        ) AS lvl
    FROM neighborhood_osm_full_line
    GROUP BY osm_id
)

SELECT
    w.road_id,
    ST_MAKEVALID(w.geom) AS geom,
    COALESCE(way_lvl.lvl, 'ground') AS lvl
FROM neighborhood_ways AS w
LEFT JOIN way_lvl ON w.osm_id = way_lvl.osm_id
WHERE w.functional_class IN (
    'motorway', 'motorway_link', 'trunk', 'trunk_link',
    'primary', 'primary_link', 'secondary', 'secondary_link',
    'tertiary', 'tertiary_link', 'residential', 'unclassified'
);
CREATE INDEX ON pbl_roads USING gist (geom);

-- Road buffer, merged once per level and cut into tiles for the index. Flat
-- ends cover the area beside each road but not past its end, so a path that
-- continues beyond a dead end does not count.
CREATE TEMPORARY TABLE pbl_road_buf ON COMMIT DROP AS
SELECT
    lvl,
    ST_SUBDIVIDE(
        ST_UNION(ST_BUFFER(geom, :pbl_buffer_m, 'endcap=flat')), 256
    ) AS geom
FROM pbl_roads
GROUP BY lvl;
CREATE INDEX ON pbl_road_buf USING gist (geom);

-- Candidate ways, with their level.
CREATE TEMPORARY TABLE pbl_cand ON COMMIT DROP AS
SELECT
    osm_id,
    NULL::BIGINT AS chain_id,
    ST_MAKEVALID(way) AS geom,
    CASE
        WHEN COALESCE(bridge, 'no') NOT IN ('no', 'boardwalk') THEN 'bridge'
        WHEN COALESCE(tunnel, 'no') != 'no' THEN 'tunnel'
        ELSE 'ground'
    END AS lvl
FROM neighborhood_osm_full_line
WHERE
    highway = 'cycleway'
    OR (
        highway = 'path'
        AND bicycle IN ('yes', 'designated')
        AND surface IN (
            'paved', 'asphalt', 'concrete', 'concrete:plates',
            'concrete:lanes', 'paving_stones', 'chipseal'
        )
    );
CREATE INDEX ON pbl_cand USING gist (geom);

-- Chains: candidate ways joined end to end where exactly two of them meet.
CREATE TEMPORARY TABLE pbl_chains ON COMMIT DROP AS
SELECT
    d.geom,
    ROW_NUMBER() OVER () AS chain_id
FROM (SELECT ST_LINEMERGE(ST_UNION(geom)) AS geom FROM pbl_cand) AS m,
    LATERAL ST_DUMP(m.geom) AS d;
CREATE INDEX ON pbl_chains USING gist (geom);

UPDATE pbl_cand
SET chain_id = c.chain_id
FROM pbl_chains AS c
WHERE ST_DWITHIN(c.geom, ST_LINEINTERPOLATEPOINT(pbl_cand.geom, 0.5), 0.01);

-- Overlap pieces: the parts of each chain inside the road buffer for the same
-- level, one level per piece.
CREATE TEMPORARY TABLE pbl_pieces ON COMMIT DROP AS
SELECT
    o.chain_id,
    o.lvl,
    d.geom,
    ROW_NUMBER() OVER () AS piece_id,
    ST_LENGTH(d.geom) AS len_m
FROM (
    SELECT
        c.chain_id,
        c.lvl,
        ST_LINEMERGE(ST_UNION(ST_INTERSECTION(c.geom, b.geom))) AS geom
    FROM pbl_cand AS c
    INNER JOIN pbl_road_buf AS b
        ON c.lvl = b.lvl AND ST_INTERSECTS(c.geom, b.geom)
    WHERE c.chain_id IS NOT NULL
    GROUP BY c.chain_id, c.lvl
) AS o,
    LATERAL ST_DUMP(ST_COLLECTIONEXTRACT(o.geom, 2)) AS d
WHERE ST_LENGTH(d.geom) > 0;

-- Parallel stretches: pieces whose median angle to the nearest road at the
-- same level, sampled every 5 m, is at most the maximum angle.
CREATE TEMPORARY TABLE pbl_stretch ON COMMIT DROP AS
SELECT
    p.chain_id,
    p.geom
FROM pbl_pieces AS p,
    LATERAL (
        SELECT
            PERCENTILE_CONT(0.5) WITHIN GROUP (
                ORDER BY LEAST(
                    MOD(ABS(az.path_az - az.road_az)::NUMERIC, 180),
                    180 - MOD(ABS(az.path_az - az.road_az)::NUMERIC, 180)
                )
            ) AS median_angle
        FROM (
            SELECT (ST_DUMPPOINTS(ST_SEGMENTIZE(p.geom, 5))).geom AS pt
        ) AS pts,
            LATERAL (
                SELECT
                    DEGREES(ST_AZIMUTH(
                        ST_LINEINTERPOLATEPOINT(
                            p.geom,
                            GREATEST(
                                ST_LINELOCATEPOINT(p.geom, pts.pt)
                                - 5 / p.len_m,
                                0
                            )
                        ),
                        ST_LINEINTERPOLATEPOINT(
                            p.geom,
                            LEAST(
                                ST_LINELOCATEPOINT(p.geom, pts.pt)
                                + 5 / p.len_m,
                                1
                            )
                        )
                    )) AS path_az,
                    DEGREES(ST_AZIMUTH(
                        ST_LINEINTERPOLATEPOINT(
                            r.geom,
                            GREATEST(
                                ST_LINELOCATEPOINT(r.geom, pts.pt)
                                - 5 / GREATEST(ST_LENGTH(r.geom), 5),
                                0
                            )
                        ),
                        ST_LINEINTERPOLATEPOINT(
                            r.geom,
                            LEAST(
                                ST_LINELOCATEPOINT(r.geom, pts.pt)
                                + 5 / GREATEST(ST_LENGTH(r.geom), 5),
                                1
                            )
                        )
                    )) AS road_az
                FROM pbl_roads AS r
                WHERE r.lvl = p.lvl
                ORDER BY r.geom <-> pts.pt
                LIMIT 1
            ) AS az
        WHERE az.path_az IS NOT NULL AND az.road_az IS NOT NULL
    ) AS a
WHERE a.median_angle <= :pbl_max_angle_deg;

-- Gap fill: add the part of the chain between consecutive stretches when it is
-- at most the maximum gap and never strays farther than the maximum distance
-- from a road. Skipped on closed chains, where position is ambiguous.
INSERT INTO pbl_stretch (chain_id, geom)
SELECT
    chain_id,
    gap_geom
FROM (
    SELECT
        chain_id,
        ST_LINESUBSTRING(chain_geom, gap_lo, gap_hi) AS gap_geom
    FROM (
        SELECT
            chain_id,
            chain_geom,
            hi AS gap_lo,
            LEAD(lo) OVER (PARTITION BY chain_id ORDER BY lo) AS gap_hi
        FROM (
            SELECT
                s.chain_id,
                c.geom AS chain_geom,
                LEAST(
                    ST_LINELOCATEPOINT(c.geom, ST_STARTPOINT(s.geom)),
                    ST_LINELOCATEPOINT(c.geom, ST_ENDPOINT(s.geom))
                ) AS lo,
                GREATEST(
                    ST_LINELOCATEPOINT(c.geom, ST_STARTPOINT(s.geom)),
                    ST_LINELOCATEPOINT(c.geom, ST_ENDPOINT(s.geom))
                ) AS hi
            FROM pbl_stretch AS s
            INNER JOIN pbl_chains AS c ON s.chain_id = c.chain_id
            WHERE NOT ST_ISCLOSED(c.geom)
        ) AS located
    ) AS ordered
    WHERE gap_hi > gap_lo
) AS gaps
WHERE
    ST_LENGTH(gap_geom) <= :pbl_max_gap_m
    AND (
        SELECT MAX(nearest.dist)
        FROM (
            SELECT (ST_DUMPPOINTS(ST_SEGMENTIZE(gap_geom, 5))).geom AS pt
        ) AS pts,
            LATERAL (
                SELECT r.geom <-> pts.pt AS dist
                FROM pbl_roads AS r
                ORDER BY r.geom <-> pts.pt
                LIMIT 1
            ) AS nearest
    ) <= :pbl_max_gap_dist_m;

ALTER TABLE pbl_stretch ADD COLUMN buf GEOMETRY;
UPDATE pbl_stretch SET buf = ST_BUFFER(geom, 1);
CREATE INDEX ON pbl_stretch USING gist (buf);

-- Label each unlabeled candidate segment where at least half of its length
-- lies within stretches. A path is labeled in both directions only when it is
-- tagged two-way for bikes (oneway:bicycle, or else oneway, set to 'no');
-- otherwise it is labeled in one direction: against the drawn direction for
-- '-1', along it in every other case.
-- noqa: disable=RF05
UPDATE neighborhood_ways
SET
    ft_bike_infra = CASE
        WHEN COALESCE(osm."oneway:bicycle", osm.oneway) IS DISTINCT FROM '-1'
            THEN 'track'
    END,
    tf_bike_infra = CASE
        WHEN COALESCE(osm."oneway:bicycle", osm.oneway) IN ('no', '-1')
            THEN 'track'
    END
FROM neighborhood_osm_full_line AS osm
WHERE
    neighborhood_ways.osm_id = osm.osm_id
    AND neighborhood_ways.functional_class = 'path'
    AND neighborhood_ways.xwalk IS NULL
    AND neighborhood_ways.ft_bike_infra IS NULL
    AND neighborhood_ways.tf_bike_infra IS NULL
    AND EXISTS (
        SELECT 1 FROM pbl_cand AS c
        WHERE c.osm_id = osm.osm_id
    )
    AND (
        SELECT
            ST_LENGTH(
                ST_INTERSECTION(neighborhood_ways.geom, ST_UNION(s.buf))
            )
        FROM pbl_stretch AS s
        WHERE ST_INTERSECTS(neighborhood_ways.geom, s.buf)
    ) >= 0.5 * ST_LENGTH(neighborhood_ways.geom);
-- noqa: enable=all
