"""Define functions used to perform an analysis."""
from enum import Enum

import geopandas as gpd
import numpy as np
import shapely
from loguru import logger
from osmnx import geocoder
from slugify import slugify
from us import states

from brokenspoke_analyzer.core import aiohttphelper
from brokenspoke_analyzer.core import processhelper

# WGS 84 / Pseudo-Mercator -- Spherical Mercator.
# https://epsg.io/3857
PSEUDO_MERCATOR_CRS = "EPSG:3857"


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
    # Lookup for the state name.
    abbrev = states.mapping("name", "abbr").get(state.title())
    if not abbrev:
        raise ValueError(f"cannot find state: {state}")

    # Lookup for the state info.
    st = states.lookup(abbrev)
    if not st:
        raise ValueError(f"cannot find state info for: {state}, {abbrev}")
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


# pylint: disable=too-many-locals
def create_synthetic_population(area, length, width, population=100):
    """
    Create a grid representing the synthetic population.

    :param GeoDataFrame area: area to grid
    :param int length: length of a cell of the grid in meters
    :param int width: width of a cell of the grid in meters
    :param int population: population to inject in each cell
    :returns: a GeoDataFrame representing the synthetic population.
    :rtype: GeoDataFrame
    """
    # Project the area into mercator.
    mercator_area = area.to_crs(PSEUDO_MERCATOR_CRS)

    # Prepare the rows and columns.
    xmin, ymin, xmax, ymax = mercator_area.total_bounds
    cols = list(np.arange(xmin, xmax + width, width))
    rows = list(np.arange(ymin, ymax + length, length))

    # Extract the biggest region.
    boundaries = max(
        mercator_area.geometry.explode(index_parts=True), key=lambda a: a.area
    )

    # Compute the cells.
    cells = []
    for col in cols[:-1]:
        for row in rows[:-1]:
            # Create a new grid cell.
            cell = shapely.geometry.Polygon(
                [
                    (col, row),
                    (col + width, row),
                    (col + width, row + length),
                    (col, row + length),
                ]
            )

            # Append it if it intersects with the biggest region.
            if cell.intersects(boundaries):
                cells.append(cell)

    # Create a geodataframe made of the cells overlapping with the area.
    # Add new columns to simulate US census data.
    rng = np.random.default_rng()
    grid = gpd.GeoDataFrame(
        {
            "geometry": cells,
            "POP10": population,
            "BLOCKID10": rng.integers(
                100000000000000, 999999999999999, size=len(cells)
            ),
        },
        crs=PSEUDO_MERCATOR_CRS,
    )

    return grid
