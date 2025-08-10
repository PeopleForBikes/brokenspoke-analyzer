"""Define functions used to perform an analysis."""

import os
import pathlib
import random
import string
import typing
import warnings
import zipfile

import geopandas as gpd
import numpy as np
import shapely
from loguru import logger
from osmnx import (
    geocoder,
    settings,
)
from slugify import slugify

from brokenspoke_analyzer.core import (
    runner,
    utils,
)
from brokenspoke_analyzer.pyrosm import data

warnings.filterwarnings("ignore")


def osmnx_query(
    country: str, city: str, state: typing.Optional[str] = None
) -> typing.Tuple[typing.Dict[str, str], str]:
    """
    Prepare the osmnx.

    Returns: the OSMNX query and its slugified version.

    Example:
        >>> osmnx_query("united states", "santa rosa", "new mexico")
        ({'city': 'santa rosa', 'country': 'united states', 'state': 'new mexico'}, 'santa-rosa-new-mexico-united-states')

        >>> osmnx_query("malta", "valletta")
        ({'city': 'valletta', 'country': 'malta'}, 'valletta-malta')
    """
    if country == state:
        state = None
    slug = slugify(", ".join(filter(None, [city, state, country])))
    query = {
        "city": city,
        "country": country,
    }

    if state:
        query["state"] = state

    return (query, slug)


def prepare_city_file(
    output_dir: pathlib.Path,
    region_file_path: pathlib.Path,
    boundary_file_path: pathlib.Path,
    pfb_osm_file: pathlib.Path,
) -> None:
    """
    Prepare the city OSM file.

    Use osmium to extract the content limited by the polygon file from the region file.
    """
    pfb_osm_file_path = output_dir / pfb_osm_file
    if not pfb_osm_file_path.exists():
        runner.run_osmium_extract(
            boundary_file_path.resolve(),
            region_file_path.resolve(),
            pfb_osm_file_path.resolve(),
        )


def state_info(state: str) -> tuple[str, str]:
    """
    Given a state, returns the corresponding abbreviation and FIPS code.

    The District of Columbia is also recognized as a state.

    Examples:
        >>> assert ("TX", "48") = state_info("texas")
        >>> assert ("DC", "11") = state_info("district of columbia")
    """
    # Ensure DC is considered a US state.
    # https://github.com/unitedstates/python-us/issues/67
    os.environ["DC_STATEHOOD"] = "1"
    from us import states

    # Lookup for the state name.
    if not state:
        raise ValueError("the state to lookup was not specified")
    state_map = states.mapping("name", "abbr")
    abbrev = state_map.get(state.title().replace(" Of ", " of "))
    if not abbrev:
        raise ValueError(f"cannot find state: {state}")

    # Lookup for the state info.
    st = states.lookup(abbrev)
    if not st:
        raise ValueError(f"cannot find state info for: {state}, {abbrev}")
    fips = st.fips

    return (abbrev, fips)


def derive_state_info(state: str | None) -> typing.Tuple[str, str, bool]:
    """
    Derive state information.

    Returns the state abbreviation, the state fips, and whether the job
    information can be retrieved from the US census.

    Examples:
        >>> assert ("TX", "48", True) == derive_state_info("texas")
        >>> assert ("ZZ", "0", False) == derive_state_info("spain")
    """
    try:
        if not state:
            raise ValueError("no 'state' was provided")
        run_import_jobs = True
        state_abbrev, state_fips = state_info(state)
    except ValueError:
        run_import_jobs = False
        state_abbrev, state_fips = (
            runner.NON_US_STATE_ABBREV,
            runner.NON_US_STATE_FIPS,
        )
    return (state_abbrev, state_fips, run_import_jobs)


def retrieve_city_boundaries(
    output: pathlib.Path, country: str, city: str, state: typing.Optional[str] = None
) -> str:
    """
    Retrieve the city boundaries and save them as Shapefile and GeoJSON.

    :return: the slugified query used to retrieve the city boundaries.
    """
    # Prepare the query.
    query, slug = osmnx_query(country, city, state)
    logger.debug(f"Query used to retrieve the boundaries: {query}")

    # Retrieve the geodataframe.
    settings.use_cache = os.getenv("BNA_OSMNX_CACHE", "1") == "1"
    city_gdf = geocoder.geocode_to_gdf(query)
    # Remove the display_name series to ensure there are no international
    # characters in the dataframe. The import will fail if the analyzer finds
    # non US characters.
    # https://github.com/PeopleForBikes/brokenspoke-analyzer/issues/24
    city_gdf.drop("display_name", axis=1)

    # Export the boundaries.
    city_gdf.to_file(output / f"{slug}.shp", encoding="utf-8")
    city_gdf.to_file(output / f"{slug}.geojson")

    return slug


# pylint: disable=too-many-locals
def create_synthetic_population(
    area: gpd.GeoDataFrame,
    length: int,
    width: int,
    population: typing.Optional[int] = 100,
) -> gpd.GeoDataFrame:
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
    mercator_area = area.to_crs(utils.PSEUDO_MERCATOR_CRS)

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
        crs=utils.PSEUDO_MERCATOR_CRS,
    )

    return grid.to_crs(area.crs)


def change_speed_limit(
    output: pathlib.Path, city: str, state_abbrev: str, speed: int
) -> None:
    """Change the speed limit."""
    speedlimit_csv = output / "city_fips_speed.csv"
    speedlimit_csv.write_text(
        f"city,state,fips_code_city,speed\n{city},{state_abbrev.lower()},{0:07},{speed}\n"
    )


def simulate_census_blocks(
    output: pathlib.Path, synthetic_population: gpd.GeoDataFrame
) -> None:
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


def retrieve_region_file(region: str, output_dir: pathlib.Path) -> pathlib.Path:
    """Retrieve the region file from Geofabrik or BBike."""
    # As per https://github.com/PeopleForBikes/brokenspoke-analyzer/issues/863
    # we must define an exception for the countries of Malaysia, Singapore and
    # Brunei as they have been grouped together in the Geofabrik dataset.
    if region in {"malaysia", "singapore", "brunei"}:
        region = "malaysia_singapore_brunei"
    dataset = utils.normalize_unicode_name(region)
    dataset_file = data.get_data(dataset, directory=output_dir)  # type: ignore
    region_file_path: pathlib.Path = pathlib.Path(dataset_file)
    region_file_path = region_file_path.resolve(strict=True)
    if not region_file_path.exists():
        raise ValueError(f"the path `{region_file_path}` does not exist")
    return region_file_path
