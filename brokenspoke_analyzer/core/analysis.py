"""Define functions used to perform an analysis."""

import os
import pathlib
import random
import string
import warnings
import zipfile

import geopandas as gpd
import numpy as np
import pygris
import shapely
from geopandas.geodataframe import GeoDataFrame
from loguru import logger
from osmnx import (
    geocoder,
    settings,
)
from slugify import slugify

from brokenspoke_analyzer.cli import common
from brokenspoke_analyzer.core import (
    constant,
    runner,
    utils,
)

warnings.filterwarnings("ignore")


def osmnx_query(
    country: str,
    city: str,
    state: str | None = None,
) -> tuple[dict[str, str], str, str]:
    """
    Prepare the osmnx.

    Returns: the OSMNX query and its slugified version.

    Example:
        >>> osmnx_query("united states", "santa rosa", "new mexico")
        ({'city': 'santa rosa', 'country': 'united states', 'state': 'new mexico'}, 'santa rosa, new mexico, united states', 'santa-rosa-new-mexico-united-states')

        >>> osmnx_query("malta", "valletta")
        ({'city': 'valletta', 'country': 'malta'}, 'valletta, malta', 'valletta-malta')
    """  # noqa: E501
    if country == state:
        state = None
    q = ", ".join(filter(None, [city, state, country]))
    slug = slugify(q)
    structured_query = {
        "city": city,
        "country": country,
    }

    if state:
        structured_query["state"] = state

    return (structured_query, q, slug)


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
    from us import states  # noqa: PLC0415

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
    if not fips:
        raise ValueError(f"cannot find FIPS code for: {state}, {abbrev}")

    return (abbrev, fips)


def derive_state_info(state: str | None) -> tuple[str, str, bool]:
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
            raise ValueError("no 'state' was provided")  # noqa: TRY301
        run_import_jobs = True
        state_abbrev, state_fips = state_info(state)
    except ValueError:
        run_import_jobs = False
        state_abbrev, state_fips = (
            runner.NON_US_STATE_ABBREV,
            runner.NON_US_STATE_FIPS,
        )
    return (state_abbrev, state_fips, run_import_jobs)


def ensure_gdf_class_boundary(gdf: gpd.GeoDataFrame) -> None:
    """Ensure the GeoDataFrame class is "boundary"."""
    gdf_class = gdf["class"].iloc[0]
    if gdf_class != constant.GDF_CLASS_BOUNDARY:
        raise TypeError(f"invalid result class: {gdf_class}")


def retrieve_city_boundaries(
    structured_query: dict[str, str],
    text_query: str,
    fips_code: str | None = None,
) -> GeoDataFrame:
    """
    Retrieve the city boundaries and save them as Shapefile and GeoJSON.

    :return: the slugified query used to retrieve the city boundaries.
    """
    if fips_code is not None and fips_code != common.DEFAULT_CITY_FIPS_CODE:
        places = pygris.places(
            state=fips_code[:2],
            cache=False,
            year=common.DEFAULT_PYGRIS_YEAR,
        )
        city_gdf = places[places["PLACEFP"] == fips_code[2:]]
        if city_gdf.empty:
            logger.debug(
                f"Cannot find Place with FIPS code: {fips_code}, "
                f"trying the County Subdivisions table",
            )
            county_subdivisions = pygris.county_subdivisions(
                state=fips_code[:2],
                cache=False,
                year=common.DEFAULT_PYGRIS_YEAR,
            )
            city_gdf = county_subdivisions[
                county_subdivisions["COUSUBFP"] == fips_code[2:]
            ]
    else:
        settings.use_cache = False
        logger.debug(f"Query used to retrieve the boundaries: {structured_query}")
        try:
            city_gdf = geocoder.geocode_to_gdf(structured_query)
            ensure_gdf_class_boundary(city_gdf)
        except TypeError:
            city_gdf = geocoder.geocode_to_gdf(text_query)
            ensure_gdf_class_boundary(city_gdf)

        # Remove the display_name series to ensure there are no international
        # characters in the dataframe. The import will fail if the analyzer finds
        # non US characters.
        # https://github.com/PeopleForBikes/brokenspoke-analyzer/issues/24
        city_gdf.drop("display_name", axis=1, inplace=True)

    return city_gdf


# pylint: disable=too-many-locals
def create_synthetic_population(
    area: gpd.GeoDataFrame,
    length: int,
    width: int,
    population: int | None = 100,
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
                ],
            )

            # Append it if it intersects with the biggest region.
            if any(map(cell.intersects, boundaries)):
                cells.append(cell)

    # Create a geodataframe made of the cells overlapping with the area.
    # Add new columns to simulate US census data.
    blockid_len = 15
    grid = gpd.GeoDataFrame(
        {
            "geometry": cells,
            "POP20": population,
            "GEOID20": [
                "".join(
                    random.choice(string.ascii_lowercase)  # noqa: S311
                    for x in range(blockid_len)
                )
                for _ in range(len(cells))
            ],
        },
        crs=utils.PSEUDO_MERCATOR_CRS,
    )  # ty:ignore[no-matching-overload]

    return grid.to_crs(area.crs)


def change_speed_limit(
    output: pathlib.Path,
    city: str,
    state_abbrev: str,
    speed: int,
) -> None:
    """Change the speed limit."""
    speedlimit_csv = output / "city_fips_speed.csv"
    speedlimit_csv.write_text(
        f"city,state,fips_code_city,speed\n{city},{state_abbrev.lower()},{0:07},{speed}\n",
    )


def simulate_census_blocks(
    output: pathlib.Path,
    synthetic_population: gpd.GeoDataFrame,
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
