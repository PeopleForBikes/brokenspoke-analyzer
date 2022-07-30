"""Define functions used to perform an analysis."""
from enum import Enum

import geopandas as gpd
from loguru import logger
from osmnx import geocoder
from slugify import slugify
from us import states

from brokenspoke_analyzer.core import aiohttphelper
from brokenspoke_analyzer.core import processhelper


class PolygonFormat(Enum):
    """Represent tha available polygon formats from polygons.openstreetmap.fr."""

    WKT = "get_wkt.py"
    GEOJSON = "get_geojson.py"
    POLY = "get_poly.py"


async def download_census_file(session, output_dir, state_fips):
    """Download the US Census file for a specific state."""
    tiger_url = f"https://www2.census.gov/geo/tiger/TIGER2021/PLACE/tl_2021_{state_fips}_place.zip"
    tiger_file = output_dir / f"tl_2021_{state_fips}_place.zip"
    await aiohttphelper.download_file(session, tiger_url, tiger_file)
    return tiger_file


def prepare_boundary_file(output_dir, city, tiger_file):
    """Extract the boundaries of a specific city from a census file."""
    city_shp = output_dir / f"{slugify(city)}.shp"
    logger.debug(f"Saving data into {city_shp}...")
    census_place = gpd.read_file(tiger_file)
    city_gdf = census_place.loc[census_place["NAME"] == city.title()]
    city_gdf.to_file(city_shp)
    return city_shp


async def download_osm_us_region_file(session, output_dir, state, region_file_name):
    """Download the region file."""
    host = "download.geofabrik.de"
    region = "north-america"
    country = "us"
    state_slug = state.lower().replace(" ", "-")
    region_file_url = f"https://{host}/{region}/{country}/{state_slug}-latest.osm.pbf"
    region_file_path = output_dir / region_file_name
    await aiohttphelper.download_file(session, region_file_url, region_file_path)
    return region_file_path


async def download_polygon_file(
    session, osm_relation_id, polygon_file, format_=PolygonFormat.POLY
):
    """Download the polygon file for a specific city from polygons.openstreetmap.fr."""
    polygon_host = "http://polygons.openstreetmap.fr"
    polygon_url = f"{polygon_host}/{format_.value}"
    # Need to warm up the database first.
    await aiohttphelper.fetch_text(session, polygon_host, {"id": osm_relation_id})
    polygon_file.write_text(
        await aiohttphelper.fetch_text(
            session, polygon_url, {"id": osm_relation_id, "params": 0}
        )
    )


def prepare_city_file(output_dir, region_file_path, polygon_file_path, pfb_osm_file):
    """
    Prepare the city OSM file.

    Use osmium to extract the content limited by the polygon file from the region file.
    """
    pfb_osm_file_path = output_dir / pfb_osm_file
    if not pfb_osm_file_path.exists():
        processhelper.run_osmium(polygon_file_path, region_file_path, pfb_osm_file_path)


def state_info(state):
    """
    Given a state, returns the corresponding abbreviation and FIPS code.

    Example:

    >>> abbr, fips = state_info("texas")
    >>> assert abbr == "TX"
    >>> assert fips == "48"
    """
    abbrev = states.mapping("name", "abbr").get(state.title())
    st = states.lookup(abbrev)
    fips = st.fips
    return (abbrev, fips)


def convert_with_geopandas(infile, outfile):
    """Convert a vector-based spatial data file to another format with geopandas."""
    gdf = gpd.read_file(infile)
    gdf.to_file(outfile)


def retrieve_city_boundaries(output, country, city, state=None):
    """
    Retrieve the city boundaries and save them as Shapefile and GeoJSON.

    :return: the slugified query used to retrieve the city boundaries.
    :rtype: str
    """
    query = ", ".join(filter(None, [city, state, country]))
    logger.debug(f"Query used to retrieve the boundaries: {query}")
    city_gdf = geocoder.geocode_to_gdf(query)

    # Export the boundaries.
    slug = slugify(query)
    city_gdf.to_file(output / f"{slug}.shp")
    city_gdf.to_file(output / f"{slug}.geojson")

    return slug
