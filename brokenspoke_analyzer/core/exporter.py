"""Define functions to export the data to various destinations."""

import pathlib
import shutil
import tempfile
import typing
from datetime import date
from enum import Enum

import boto3
from loguru import logger
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
        "neighborhood_ways",
        "neighborhood_ways_intersections",
    ],
    "csv": [
        "neighborhood_connected_census_blocks",
        "neighborhood_overall_scores",
        "neighborhood_score_inputs",
        "residential_speed_limit",
        "mileage",
    ],
}


class Exporter(str, Enum):
    """Define the available exporters."""

    none = "none"
    local = "local"
    s3 = "s3"
    s3_custom = "s3_custom"


def export_to_csv(
    export_dir: pathlib.Path, tables: typing.Sequence[str], engine: Engine
) -> None:
    """Export a list of PostgreSQL tables to CSV files."""
    for table in tables:
        # Skip export if the table does not exist.
        if not dbcore.table_exists(engine, table):
            continue
        csv_file = export_dir / f"{table}.csv"
        dbcore.export_to_csv(engine, csv_file, table)


def export_to_geojson(
    export_dir: pathlib.Path, tables: typing.Sequence[str], database_url: str
) -> None:
    """Export a list of PostGIS tables to GeoJSON files."""
    engine = dbcore.create_psycopg_engine(database_url)
    for table in tables:
        # Skip export if the table does not exist.
        if not dbcore.table_exists(engine, table):
            continue
        geojson_file = export_dir / f"{table}.geojson"
        runner.run_ogr2ogr_geojson_export(database_url, geojson_file, table)


def export_to_shp(
    export_dir: pathlib.Path, tables: typing.Sequence[str], database_url: str
) -> None:
    """Export a list of PostGIS tables to Shapefiles."""
    engine = dbcore.create_psycopg_engine(database_url)
    for table in tables:
        # Skip export if the table does not exist.
        if not dbcore.table_exists(engine, table):
            continue
        shapefile = export_dir / f"{table}.shp"
        runner.run_pgsql2shp(database_url, shapefile, table)


def auto_export(
    export_dir: pathlib.Path,
    tables: typing.Mapping[str, typing.Sequence[str]],
    database_url: str,
) -> None:
    """
    Export PostgreSQL/PostGIS tables to their repective files.

    Regular tables are exported into CSV files. GIS tables are exported either
    to geojson or sometimes shapefiles (or both).
    """
    # Prepare the database connection.
    engine = dbcore.create_psycopg_engine(database_url)

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
    * usa/tx/austin/23.08
    * usa/tx/austin/23.12.2
    * spain/valencia/valencia/23.08

        >>> today = date.today()
        >>> calver = f"{today.strftime('%y.%m')}"
        >>> directory = create_calver_directories("usa", "austin", "tx")
        >>> assert directory == pathlib.Path(f"usa/tx/austin/{calver}")
    """
    p = calver_base(country, city, region, date_override, base_dir)

    # List all the directories with the same calver stem.
    dirs = list(p.parent.glob(f"{p.name}*"))

    # If there is none, it means it is the first one.
    if not dirs:
        return p

    revision = calver_revision(dirs)
    return pathlib.Path(f"{p}.{revision}")


def calver_base(
    country: str,
    city: str,
    region: typing.Optional[str] = None,
    date_override: typing.Optional[str] = None,
    base_dir: pathlib.Path = pathlib.Path(),
) -> pathlib.Path:
    """Build the base part of the calver path."""
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
    p /= f"{today.strftime('%y.%m')}"

    return p


def calver_revision(dirs: typing.Sequence[pathlib.Path]) -> int:
    """
    Build the revision part of the calver path.

    Examples:
        >>> dirs=[pathlib.Path('usa/new mexico/santa rosa/23.08')]
        >>> calver_revision(dirs)
        1
        >>> dirs.append(pathlib.Path('usa/new mexico/santa rosa/23.08.1'))
        >>> calver_revision(dirs)
        2
        >>> dirs.append(pathlib.Path('usa/new mexico/santa rosa/23.08.15'))
        >>> calver_revision(dirs)
        16
        >>> dirs.append(pathlib.Path('usa/new mexico/santa rosa/23.08.150'))
        >>> calver_revision(dirs)
        151

    """
    # Collect the directories with the suffixes.
    with_micro = [
        int(d.suffixes[-1].replace(".", "")) for d in dirs if len(d.suffixes) == 2
    ]

    # If there is no directory with a micro part, create the first one.
    if not with_micro:
        return 1

    # Otherwise get the highest micro and increment it.
    micro = max(with_micro) + 1
    return micro


def create_calver_s3_directories(
    bucket_name: str,
    country: str,
    city: str,
    region: typing.Optional[str] = None,
) -> pathlib.Path:
    """Create the calver directory in the S3 bucket."""
    # Initialize the S3 client.
    s3 = boto3.resource("s3")
    bucket = s3.Bucket(bucket_name)

    # Create the calver directory.
    s3_dir = calver_base(country, city, region)

    # Check for any existing match.
    matches = [
        pathlib.Path(obj.key)
        for obj in bucket.objects.filter(Prefix=str(s3_dir))
        if str(s3_dir) in obj.key and obj.key.endswith("/")
    ]

    # In case there is already a calver folder, we must increment the revision.
    if matches:
        rev = calver_revision(matches)
        s3_dir = pathlib.Path(f"{s3_dir}.{rev}/")

    # Create the folder in the bucket.
    bucket.put_object(Body="", Key=f"{s3_dir}/")

    return s3_dir


def s3_directories(
    bucket_name: str, s3_dir: typing.Optional[pathlib.Path] = pathlib.Path()
) -> pathlib.Path:
    """Create a custom directory in the S3 bucket."""
    # Make mypy happy.
    if not s3_dir:
        raise ValueError("`s3_dir` must be set")

    # Initialize the S3 client.
    s3 = boto3.resource("s3")
    bucket = s3.Bucket(bucket_name)

    # Create the folder in the bucket.
    bucket.put_object(Body="", Key=f"{s3_dir}/")

    return s3_dir


def s3(
    database_url: str,
    bucket_name: str,
    folder: typing.Optional[pathlib.Path] = pathlib.Path(),
    with_bundle: typing.Optional[bool] = False,
) -> None:
    """Export PostgreSQL/PostGIS tables to an S3 Bucket."""
    # Make mypy happy.
    if not folder:
        raise ValueError("`dest` must be set")

    # Initialize the S3 client.
    s3 = boto3.client("s3")

    # Create a temporary directory to export the files.
    with tempfile.TemporaryDirectory() as tmpdir_name:
        tmpdir = pathlib.Path(tmpdir_name)
        local_files(
            database_url=database_url,
            export_dir=tmpdir,
            with_bundle=with_bundle,
        )

        # Upload each file one after the other.
        for file in tmpdir.iterdir():
            if not file.is_file():
                continue

            object_name = folder / file.name
            logger.debug(f"Uploading file to s3://{bucket_name}/{object_name}")
            s3.upload_file(file, bucket_name, str(object_name))


def bundle(src_dir: pathlib.Path) -> pathlib.Path:
    """Bundle the content of `src_dir` into a zip file and save it into `src_dir`."""
    bundle_file = pathlib.Path("bundle.zip")
    dest = src_dir / bundle_file
    shutil.make_archive(bundle_file.stem, bundle_file.suffix[1:], src_dir)
    shutil.move(bundle_file, dest)
    return dest


def local_files(
    database_url: str,
    export_dir: pathlib.Path,
    with_bundle: typing.Optional[bool] = False,
) -> None:
    """Export result files into a local directory."""
    # Prepare the output directory.
    export_dir.mkdir(parents=True, exist_ok=True)

    # Export the catalogued tables to their associated format.
    auto_export(export_dir.resolve(strict=True), TABLE_CATALOG, database_url)

    # Bundle the result files into a zip file if needed.
    if with_bundle:
        bundle(export_dir)
