----------------------------------------
-- INPUTS
-- location: neighborhood
----------------------------------------
UPDATE neighborhood_ways SET ft_park = NULL, tf_park = NULL;

-- noqa: disable=RF05
-- both
UPDATE neighborhood_ways
SET
    ft_park = CASE
        WHEN osm."parking:lane:both" = 'parallel' THEN 1
        WHEN osm."parking:lane:both" = 'paralell' THEN 1
        WHEN osm."parking:lane:both" = 'diagonal' THEN 1
        WHEN osm."parking:lane:both" = 'perpendicular' THEN 1
        WHEN osm."parking:lane:both" = 'no_parking' THEN 0
        WHEN osm."parking:lane:both" = 'no_stopping' THEN 0
        WHEN osm."parking:both" = 'lane' THEN 1
        WHEN osm."parking:both" = 'no' THEN 0
        WHEN osm."parking:both:restriction" = 'no_stopping' THEN 0
        WHEN osm."parking:both:restriction" = 'no_parking' THEN 0
    END,
    tf_park = CASE
        WHEN osm."parking:lane:both" = 'parallel' THEN 1
        WHEN osm."parking:lane:both" = 'paralell' THEN 1
        WHEN osm."parking:lane:both" = 'diagonal' THEN 1
        WHEN osm."parking:lane:both" = 'perpendicular' THEN 1
        WHEN osm."parking:lane:both" = 'no_parking' THEN 0
        WHEN osm."parking:lane:both" = 'no_stopping' THEN 0
        WHEN osm."parking:both" = 'lane' THEN 1
        WHEN osm."parking:both" = 'no' THEN 0
        WHEN osm."parking:both:restriction" = 'no_stopping' THEN 0
        WHEN osm."parking:both:restriction" = 'no_parking' THEN 0
    END
FROM neighborhood_osm_full_line AS osm
WHERE neighborhood_ways.osm_id = osm.osm_id;

-- right
UPDATE neighborhood_ways
SET
    ft_park = CASE
        WHEN osm."parking:lane:right" = 'parallel' THEN 1
        WHEN osm."parking:lane:right" = 'paralell' THEN 1
        WHEN osm."parking:lane:right" = 'diagonal' THEN 1
        WHEN osm."parking:lane:right" = 'perpendicular' THEN 1
        WHEN osm."parking:lane:right" = 'no_parking' THEN 0
        WHEN osm."parking:lane:right" = 'no_stopping' THEN 0
        WHEN osm."parking:right" = 'lane' THEN 1
        WHEN osm."parking:right" = 'no' THEN 0
        WHEN osm."parking:right:restriction" = 'no_stopping' THEN 0
        WHEN osm."parking:right:restriction" = 'no_parking' THEN 0
    END
FROM neighborhood_osm_full_line AS osm
WHERE neighborhood_ways.osm_id = osm.osm_id;

-- left
UPDATE neighborhood_ways
SET
    tf_park = CASE
        WHEN osm."parking:lane:left" = 'parallel' THEN 1
        WHEN osm."parking:lane:left" = 'paralell' THEN 1
        WHEN osm."parking:lane:left" = 'diagonal' THEN 1
        WHEN osm."parking:lane:left" = 'perpendicular' THEN 1
        WHEN osm."parking:lane:left" = 'no_parking' THEN 0
        WHEN osm."parking:lane:left" = 'no_stopping' THEN 0
        WHEN osm."parking:left" = 'lane' THEN 1
        WHEN osm."parking:left" = 'no' THEN 0
        WHEN osm."parking:left:restriction" = 'no_stopping' THEN 0
        WHEN osm."parking:left:restriction" = 'no_parking' THEN 0
    END
FROM neighborhood_osm_full_line AS osm
WHERE neighborhood_ways.osm_id = osm.osm_id;
-- noqa: enable=RF05
