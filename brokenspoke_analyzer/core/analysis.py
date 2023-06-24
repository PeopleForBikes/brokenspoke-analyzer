"""Define functions used to perform an analysis."""
import gzip
import random
import string
import zipfile
from enum import Enum

import geopandas as gpd
import numpy as np
import shapely
from loguru import logger
from osmnx import geocoder
from slugify import slugify
from us import states

from brokenspoke_analyzer.core import (
    aiohttphelper,
    processhelper,
)

# WGS 84 / Pseudo-Mercator -- Spherical Mercator.
# https://epsg.io/3857
PSEUDO_MERCATOR_CRS = "EPSG:3857"


class PolygonFormat(Enum):
    """Represent the available polygon formats from polygons.openstreetmap.fr."""

    WKT = "get_wkt.py"
    GEOJSON = "get_geojson.py"
    POLY = "get_poly.py"


async def download_census_file(session, output_dir, state_fips):
    """Download the US Census file for a specific state."""
    tiger_url = (
        "https://www2.census.gov/geo/tiger/TIGER2021/PLACE/"
        f"tl_2021_{state_fips}_place.zip"
    )
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
    if not state:
        raise ValueError("the state to lookup was not specified")
    state_map = states.mapping("name", "abbr")
    abbrev = state_map.get(state.title())
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
    # Remove the display_name series to ensure there are no international
    # characters in the dataframe. The import will fail if the analyzer finds
    # non US characters.
    # https://github.com/PeopleForBikes/brokenspoke-analyzer/issues/24
    city_gdf.drop("display_name", axis=1)

    # Export the boundaries.
    slug = slugify(query)
    city_gdf.to_file(output / f"{slug}.shp", encoding="utf-8")
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

    # Extract all the boundaries.
    boundaries = mercator_area.geometry.explode(index_parts=True)

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
            if any(map(cell.intersects, boundaries)):
                cells.append(cell)

    # Create a geodataframe made of the cells overlapping with the area.
    # Add new columns to simulate US census data.
    BLOCKID_LEN = 15
    grid = gpd.GeoDataFrame(
        {
            "geometry": cells,
            "POP10": population,
            "BLOCKID10": [
                "".join(
                    random.choice(string.ascii_lowercase) for x in range(BLOCKID_LEN)
                )
                for _ in range(len(cells))
            ],
        },
        crs=PSEUDO_MERCATOR_CRS,
    )

    return grid.to_crs(area.crs)


def change_speed_limit(output, city, state_abbrev, speed):
    """Change the speed limit."""
    speedlimit_csv = output / "city_fips_speed.csv"
    speedlimit_csv.write_text(
        f"city,state,fips_code_city,speed\n{city},{state_abbrev.lower()},1234567,{speed}\n"
    )


def simulate_census_blocks(output, synthetic_population):
    """Simulate census blocks."""
    tabblock = "population"
    synthetic_population_shp = output / f"{tabblock}.shp"
    synthetic_population.to_file(synthetic_population_shp)
    shapefile_parts = [
        output / f"{tabblock}.{suffix}"
        for suffix in ["cpg", "dbf", "prj", "shp", "shx"]
    ]
    # The shapefile components must be zipped at the root of one zip archive.
    # https://github.com/azavea/pfb-network-connectivity/blob/a9a4bc9546e1c798c6a6e11ee57dcca5db438f3e/src/analysis/import/import_neighborhood.sh#L112-L114
    synthetic_population_zip = output / f"{tabblock}.zip"
    with zipfile.ZipFile(synthetic_population_zip, "w") as z:
        for f in shapefile_parts:
            z.write(f, arcname=f.name)


async def download_lodes_data(session, output_dir, state, part, year):
    """
    Download employment data from the US census website: https://lehd.ces.census.gov/.

    LODES stands for LEHD Origin-Destination Employment Statistics.

    OD means Origin-Data, which represents the jobs that are associated with
    both a home census block and a work census block.

    The filename has the folowing format: `[ST]_od_[PART]_[TYPE]_[YEAR].csv.gz`,
    where:
    - [ST] = lowercase, 2-letter postal code for a chosen state
    - [PART] = Part of the state file, can have a value of either "main" or
        "aux".
        Complimentary parts of the state file, the main part includes jobs with
        both workplace and residence in the state and the aux part includes jobs
        with the workplace in the state and the residence outside of the state.
    - [TYPE] = Job Type, can have a value of "JTOO" for All Jobs, "JT01" for
        Primary Jobs, "JT02" for All Private Jobs, "JT03" for Private Primary
        Jobs, "JT04" for All Federal Jobs, or "JT05" for Federal Primary Jobs.
    - [YEAR] = Year of job data. Can have the value of 2002-2020 for most
        states.

    As an example, the main OD file of Primary Jobs in 2007 for California would
    be the file: `ca_od_main_JTO1_2007.csv.gz`.

    More information about the formast can be found on the website:
    https://lehd.ces.census.gov/data/#lodes.
    """
    lehd_url = f"http://lehd.ces.census.gov/data/lodes/LODES7/{state.lower()}/od/"
    lehd_filename = f"{state.lower()}_od_{part.lower()}_JT00_{year}.csv.gz"
    gzipped_lehd_file = output_dir / lehd_filename
    decompressed_lefh_file = output_dir / gzipped_lehd_file.stem

    # Skip the download if the target file already exists.
    if decompressed_lefh_file.exists():
        return

    # Download the file.
    await aiohttphelper.download_file(
        session, f"{lehd_url}/{lehd_filename}", gzipped_lehd_file
    )

    # Decompress it.
    gunzip(gzipped_lehd_file, decompressed_lefh_file)


async def download_census_waterblocks(session, output_dir):
    """Download the census waterblocks."""
    waterblock_url = (
        "https://s3.amazonaws.com/pfb-public-documents/censuswaterblocks.zip"
    )
    zipped_waterblock_file = output_dir / "censuswaterblocks.zip"
    decompressed_waterblock_file = output_dir / "censuswaterblocks.csv"

    # Skip the download if the target file already exists.
    if decompressed_waterblock_file.exists():
        return

    # Download the file.
    await aiohttphelper.download_file(session, waterblock_url, zipped_waterblock_file)

    # Unzip it.
    unzip(zipped_waterblock_file, output_dir)


async def download_2010_census_blocks(session, output_dir, fips):
    """Download a 2010 census tabulation block code for a specific state."""
    tabblk2010_url = "http://www2.census.gov/geo/tiger/TIGER2010BLKPOPHU/"
    tabblk2010_filename = f"tabblock2010_{fips}_pophu.zip"
    tabblk2010_file = output_dir / tabblk2010_filename
    population_file = output_dir / "population.shp"

    # Skip the download if the target file already exists.
    if population_file.exists():
        return

    # Download the file.
    await aiohttphelper.download_file(
        session, f"{tabblk2010_url}/{tabblk2010_filename}", tabblk2010_file
    )

    # Unzip it.
    unzip(tabblk2010_file, output_dir)

    # Rename the tabulation block files to "population".
    tabblk2010_files = output_dir.glob(f"{tabblk2010_file.stem}.*")
    for file in tabblk2010_files:
        file.rename(output_dir / f"population{file.suffix}")


async def download_state_speed_limits(session, output_dir):
    """Download the state speed limits."""
    state_speed_filename = "state_fips_speed.csv"
    state_speed_url = (
        f"https://s3.amazonaws.com/pfb-public-documents/{state_speed_filename}"
    )
    state_speed_file = output_dir / state_speed_filename

    # Download the file.
    await aiohttphelper.download_file(session, state_speed_url, state_speed_file)


async def download_city_speed_limits(session, output_dir):
    """Download the city speed limits."""
    city_speed_filename = "city_fips_speed.csv"
    city_speed_url = (
        f"https://s3.amazonaws.com/pfb-public-documents/{city_speed_filename}"
    )
    city_speed_file = output_dir / city_speed_filename

    # Download the file.
    await aiohttphelper.download_file(session, city_speed_url, city_speed_file)


def unzip(zip_file, output_dir, delete_after=True):
    """Unzip an archive into a specific directory."""
    # Decompress it.
    with zipfile.ZipFile(zip_file) as zipped:
        zipped.extractall(output_dir)

    # Delete the archive.
    if delete_after:
        zip_file.unlink()


def gunzip(gzip_file, target, delete_after=True):
    """Gunzip a file into a specific target."""
    # Decompress it.
    with gzip.open(gzip_file, "rb") as f:
        content = f.read()
        target.write_bytes(content)

    # Delete the archive.
    if delete_after:
        gzip_file.unlink()
