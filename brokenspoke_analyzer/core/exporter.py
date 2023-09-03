import pathlib
import typing
from datetime import date

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

from brokenspoke_analyzer.core import runner
from brokenspoke_analyzer.core.database import dbcore

# Catalog the tables and associate them to an export format.
TABLE_CATALOG = {
    "shp": [
        "neighborhood_census_blocks",
        "neighborhood_ways",
    ],
    "geojson": [
        "neighborhood_census_blocks",
        "neighborhood_colleges",
        "neighborhood_community_centers",
        "neighborhood_dentists",
        "neighborhood_doctors",
        "neighborhood_hospitals",
        "neighborhood_parks",
        "neighborhood_pharmacies",
        "neighborhood_retail",
        "neighborhood_schools",
        "neighborhood_social_services",
        "neighborhood_supermarkets",
        "neighborhood_transit",
        "neighborhood_universities",
    ],
    "csv": [
        "neighborhood_connected_census_blocks",
        "neighborhood_overall_scores",
        "neighborhood_score_inputs",
        "residential_speed_limit",
    ],
}


def export_to_csv(
    export_dir: pathlib.Path, tables: typing.Sequence[str], engine: Engine
) -> None:
    """Export a list of PostgreSQL tables to CSV files."""
    for table in tables:
        csv_file = export_dir / f"{table}.csv"
        dbcore.export_to_csv(engine, csv_file, table)


def export_to_geojson(
    export_dir: pathlib.Path, tables: typing.Sequence[str], database_url: str
) -> None:
    """Export a list of PostGIS tables to GeoJSON files"""
    for table in tables:
        geojson_file = export_dir / f"{table}.geojson"
        runner.run_ogr2ogr_geojson_export(database_url, geojson_file, table)


def export_to_shp(
    export_dir: pathlib.Path, tables: typing.Sequence[str], database_url: str
) -> None:
    """Export a list of PostGIS tables to Shapefiles."""
    for table in tables:
        shapefile = export_dir / f"{table}.shp"
        runner.run_pgsql2shp(database_url, shapefile, table)


def auto_export(
    export_dir: pathlib.Path,
    tables: typing.Mapping[str, typing.Sequence[str]],
    database_url: str,
) -> None:
    """Export PostgreSQL/PostGIS tables to their repective files."""
    # Prepare the database connection.
    engine = create_engine(
        database_url.replace("postgresql://", "postgresql+psycopg://")
    )

    # Export the tables per target.
    export_to_shp(export_dir, tables.get("shp", []), database_url)
    export_to_geojson(export_dir, tables.get("geojson", []), database_url)
    export_to_csv(export_dir, tables.get("csv", []), engine)


def create_calver_directories(
    country: str,
    city: str,
    region: typing.Optional[str],
    date_override: typing.Optional[str] = None,
    base_dir: pathlib.Path = pathlib.Path(),
) -> pathlib.Path:
    """
    Create a directory structure following calver to export the tables.

    The calver scheme is based and inspired by the BNA mechanics standards:
    <country>/<egion>/<city>/YY.MM[.Micro]
    See https://calver.org/#scheme for more details.

    Examples:

    * usa/tx/austin/23.8
    * usa/tx/austin/23.12.2
    * spain/valencia/valencia/23.8

    >>> today = date.today()
    >>> calver = f"{today.strftime('%y')}.{today.month}"
    >>> directory = create_calver_directories("usa", "austin", "tx")
    >>> assert directory == pathlib.Path(f"usa/tx/austin/{calver}")

    """
    # Start with the base path.
    p = base_dir

    # Add the country.
    p /= country.lower()

    # Add the region, falling back to the country name.
    if region:
        p /= region.lower()
    else:
        p /= country.lower()

    # Add the city.
    p /= city.lower()

    # Use the date override if any.
    if date_override:
        return p / date_override

    # Otherwise use the appropriate calver.
    today = date.today()
    calver = f"{today.strftime('%y')}.{today.month}"

    # List all the directories with the same calver stem.
    dirs = list(p.glob(f"{calver}*"))

    # If there is none, it means it is the first one.
    if not dirs:
        return p / calver

    # If there are existing directories, keep only the ones with a micro part,
    # extract the micro parts and convert them to integers.
    with_micro = [int(d.suffixes[-1][-1:]) for d in dirs if len(d.suffixes) == 2]

    # If there is no directory with a micro part, create the first one.
    if not with_micro:
        return p / f"{calver}.1"

    # Otherwise get the highest micro and increment it.
    micro = max(with_micro) + 1
    return p / f"{calver}.{micro}"
