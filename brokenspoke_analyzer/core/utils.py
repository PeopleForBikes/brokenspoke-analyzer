import gzip
import pathlib
import typing
import zipfile
from enum import Enum

import geopandas as gpd
from loguru import logger
from slugify import slugify

# WGS 84 / Pseudo-Mercator -- Spherical Mercator.
# https://epsg.io/3857
PSEUDO_MERCATOR_CRS = "EPSG:3857"


class PolygonFormat(Enum):
    """Represent the available polygon formats from polygons.openstreetmap.fr."""

    WKT = "get_wkt.py"
    GEOJSON = "get_geojson.py"
    POLY = "get_poly.py"


def unzip(
    zip_file: pathlib.Path,
    output_dir: pathlib.Path,
    delete_after: typing.Optional[bool] = True,
) -> None:
    """Unzip an archive into a specific directory."""
    # Decompress it.
    zip_file = zip_file.resolve(strict=True)
    with zipfile.ZipFile(zip_file) as zipped:
        zipped.extractall(output_dir.resolve(strict=True))

    # Delete the archive.
    if delete_after:
        zip_file.unlink()


def gunzip(
    gzip_file: pathlib.Path,
    target: pathlib.Path,
    delete_after: typing.Optional[bool] = True,
) -> None:
    """Gunzip a file into a specific target."""
    # Decompress it.
    gzip_file = gzip_file.resolve(strict=True)
    with gzip.open(gzip_file, "rb") as f:
        content = f.read()
        target.resolve().write_bytes(content)

    # Delete the archive.
    if delete_after:
        gzip_file.unlink()


def prepare_census_blocks(tabblk_file: pathlib.Path, output_dir: pathlib.Path) -> None:
    """Prepare the census block files to match our naming convention."""
    # Unzip it.
    output_dir = output_dir.resolve()
    unzip(tabblk_file.resolve(strict=True), output_dir)

    # Rename the tabulation block files to "population".
    tabblk2010_files = output_dir.glob(f"{tabblk_file.stem}.*")
    for file in tabblk2010_files:
        file.rename(output_dir / f"population{file.suffix}")


def normalize_unicode_name(value: str) -> str:
    """
    Normalize unicode names.

    Examples:
        >>> normalize_unicode_name("Québec")
        quebec

        >>> normalize_unicode_name("Cañon City")
        canon city
    """
    return slugify(value, save_order=True, separator=" ")


def prepare_environment(
    city: str,
    state: str,
    country: str,
    city_fips: str,
    state_fips: str,
    state_abbrev: str,
    run_import_jobs: str,
) -> typing.Mapping[str, str]:
    """
    Prepare the environment variables required by the modular BNA.

    Example:
        >>> d = prepare_environment(
        >>>     "washington", "district of columbia", "usa", "1150000", "11", "DC", "1"
        >>> )
        >>> assert d == {
        >>>    "BNA_CITY_FIPS": "1150000",
        >>>    "BNA_CITY": "washington",
        >>>    "BNA_COUNTRY": "usa",
        >>>    "BNA_FULL_STATE": "district of columbia",
        >>>    "BNA_SHORT_STATE": "dc",
        >>>    "BNA_STATE_FIPS": "11",
        >>>    "CENSUS_YEAR": "2019",
        >>>    "NB_COUNTRY": "usa",
        >>>    "NB_INPUT_SRID": "4326",
        >>>    "PFB_CITY_FIPS": "1150000",
        >>>    "PFB_STATE_FIPS": "11",
        >>>    "PFB_STATE": "dc",
        >>>    "RUN_IMPORT_JOBS": "1",
        >>> }
    """
    normalized_city_fips = f"{city_fips:07}"
    normalized_state_abbrev = state_abbrev.lower()
    normalized_state_fips = str(state_fips)
    return {
        "BNA_CITY_FIPS": normalized_city_fips,
        "BNA_CITY": city,
        "BNA_COUNTRY": country,
        "BNA_FULL_STATE": state,
        "BNA_SHORT_STATE": normalized_state_abbrev,
        "BNA_STATE_FIPS": normalized_state_fips,
        "CENSUS_YEAR": "2019",
        "NB_COUNTRY": country,
        "NB_INPUT_SRID": "4326",
        "PFB_CITY_FIPS": normalized_city_fips,
        "PFB_STATE_FIPS": normalized_state_fips,
        "PFB_STATE": normalized_state_abbrev,
        "RUN_IMPORT_JOBS": run_import_jobs,
    }


def prepare_city_inputs(
    country: str, city: str, state: str, root: typing.Optional[pathlib.Path] = None
) -> tuple[pathlib.Path, pathlib.Path, pathlib.Path]:
    """
    Prepare the directories and files that will be used to perform the analysis.

    :returns: a tuple containing the input directory created for the city, the
        boundary file and the OSM file.
    """
    # Normalize the name.
    normalized_city_name = slugify(f"{city} {state} {country}")
    logger.debug(f"{normalized_city_name=}")

    # Prepare the directory structure.
    if not root:
        root = pathlib.Path("./data")
    city_dir = root.resolve(strict=True) / normalized_city_name
    city_data_file = city_dir / normalized_city_name
    city_osm_file = city_data_file.with_suffix(".osm")
    city_boundary_file = city_data_file.with_suffix(".shp")

    city_dir.mkdir(parents=True, exist_ok=True)

    return (city_dir, city_boundary_file, city_osm_file)


def get_srid(shapefile: pathlib.Path) -> str:
    """Get the SRID of a shapefile."""
    gdf = gpd.read_file(shapefile.resolve(strict=True))
    utm = gdf.estimate_utm_crs()
    return str(utm.to_string()[5:])
