----------------------------------------
-- INPUTS
-- location: neighborhood
-- :nb_boundary_buffer psql var must be set before running this script,
--      e.g. psql -v nb_boundary_buffer=1000 -f clip_osm.sql
----------------------------------------


DELETE FROM neighborhood_ways AS ways
USING neighborhood_boundary AS boundary
WHERE NOT ST_DWithin(ways.geom, boundary.geom, :nb_boundary_buffer);

DELETE FROM neighborhood_osm_full_line AS lines_
USING neighborhood_boundary AS boundary
WHERE NOT ST_DWithin(lines_.way, boundary.geom, :nb_boundary_buffer);

DELETE FROM neighborhood_osm_full_point AS points
USING neighborhood_boundary AS boundary
WHERE NOT ST_DWithin(points.way, boundary.geom, :nb_boundary_buffer);

DELETE FROM neighborhood_osm_full_polygon AS polygons
USING neighborhood_boundary AS boundary
WHERE NOT ST_DWithin(polygons.way, boundary.geom, :nb_boundary_buffer);

DELETE FROM neighborhood_osm_full_roads AS roads
USING neighborhood_boundary AS boundary
WHERE NOT ST_DWithin(roads.way, boundary.geom, :nb_boundary_buffer);
