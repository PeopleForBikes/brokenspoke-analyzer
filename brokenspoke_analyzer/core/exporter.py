"""Define functions to export the data to various destinations."""

from __future__ import annotations

import os
import pathlib
import shutil
import tempfile
import typing
from datetime import date
from enum import Enum
from typing import TYPE_CHECKING

import boto3
import obstore
from loguru import logger
from obstore.store import from_url
from sqlalchemy.engine import Engine

from brokenspoke_analyzer.core import runner
from brokenspoke_analyzer.core.database import dbcore

if TYPE_CHECKING:
    from obstore.store import ObjectStore

# Catalog the tables and associate them to an export format.
TABLE_CATALOG = {
    "shp": [
        "neighborhood_census_blocks",
        "neighborhood_ways",
    ],
    "geojson": [
        "neighborhood_boundary",
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
    r2 = "r2"
    r2_custom = "r2_custom"


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

    * usa/tx/austin/23.08
    * usa/tx/austin/23.12.2
    * spain/valencia/valencia/23.08

    Examples:
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
    """
    Build the base part of the calver path.

    Examples:
        >>> today = date.today()
        >>> calver = f"{today.strftime('%y.%m')}"
        >>> directory = calver_base("usa", "austin", "tx")
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


async def s3(
    database_url: str,
    bucket_name: str,
    folder: pathlib.Path = pathlib.Path(),
    with_bundle: bool = False,
) -> None:
    """Export PostgreSQL/PostGIS tables to an S3 Bucket."""
    store = create_s3_store(bucket_name)
    await export_store(store, database_url, folder, with_bundle)


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
    with_bundle: bool = False,
) -> None:
    """Export result files into a local directory."""
    # Prepare the output directory.
    export_dir.mkdir(parents=True, exist_ok=True)

    # Export the catalogued tables to their associated format.
    auto_export(export_dir.resolve(strict=True), TABLE_CATALOG, database_url)

    # Bundle the result files into a zip file if needed.
    if with_bundle:
        bundle(export_dir)


def create_s3_store(bucket_name: str) -> ObjectStore:
    """
    Create the S3 store.

    Authentication is done via AWS environment viariables:
    - AWS_ACCESS_KEY_ID
    - AWS_SECRET_ACCESS_KEY
    - AWS_SESSION_TOKEN (optional)
    - AWS_REGION
    """
    return from_url(f"s3://{bucket_name}")


def create_r2_store(bucket_name: str) -> ObjectStore:
    """
    Create the R2 store.

    Authentication is done via environment viariables:
    - AWS_ACCESS_KEY_ID
    - AWS_SECRET_ACCESS_KEY
    - CLOUDFLARE_ACCOUNT_ID

    Since R2 is an S3 compatible storage, we must use the AWS environment variables.
    """
    account_id = os.environ["CLOUDFLARE_ACCOUNT_ID"]
    return from_url(
        f"https://{account_id}.r2.cloudflarestorage.com/{bucket_name}",
    )


async def mkdir(store: ObjectStore, path: pathlib.Path) -> None:
    """
    Create the directory if it does not exist.

    Since object stores do not have a concept of directories, we create an empty
    file with the name of the directory and a suffix to indicate that it is a
    directory.
    """
    await store.put_async(f"{path}/.dir", b"")


async def upload_file(store: ObjectStore, path: pathlib.Path) -> None:
    """Upload a file to the store."""
    await store.put_async(str(path), path)


async def mkdir_calver_directory(
    store: ObjectStore,
    country: str,
    city: str,
    region: typing.Optional[str] = None,
) -> pathlib.Path:
    """Create the calver directory in the S3 bucket."""
    # Create the calver directory.
    calver_dir = calver_base(country, city, region)

    # Get a stream of metadata objects:
    items = store.list()

    # Check for any existing matching directories.
    matches = [
        pathlib.Path(meta["path"][:-5])  # Remove "/.dir" suffix
        for item in items
        for meta in item
        if meta["path"].endswith("/.dir")
        and str(calver_dir) in meta["path"]
        and meta["size"] == 0
    ]

    # In case there is already a calver folder, we must increment the revision.
    if matches:
        rev = calver_revision(matches)
        calver_dir = pathlib.Path(f"{calver_dir}.{rev}/")

    # Create the folder in the bucket.
    await mkdir(store, calver_dir)

    # Return the calver directory.
    return calver_dir


async def export_store(
    store: ObjectStore,
    database_url: str,
    folder: pathlib.Path = pathlib.Path(),
    with_bundle: bool = False,
) -> None:
    """Export PostgreSQL/PostGIS tables to a store."""
    # Get bucket name.
    # !!Remarks:
    #   - HTTPStore, LocalStore and MemoryStore do not have a config attribute.
    #   - AzureConfig has no key "bucket", uses "container_name" instead.
    bucket_name = store.config["bucket"]  # type: ignore

    # Create a temporary directory to export the files.
    with tempfile.TemporaryDirectory() as tmpdir_name:
        tmpdir = pathlib.Path(tmpdir_name)
        local_files(
            database_url=database_url,
            export_dir=tmpdir,
            with_bundle=with_bundle,
        )

        # Create a local store.
        local_store = from_url(f"file://{tmpdir}")

        # Upload each file sequentially.
        for file in tmpdir.iterdir():
            # Skip directories and non-files.
            if not file.is_file():
                continue

            # Stream the file from the local store to the destination store.
            object_name = str(folder / file.name)
            logger.debug(f"Uploading file to store://{bucket_name}/{object_name}")
            resp = await local_store.get_async(file.name)
            await store.put_async(object_name, resp)


async def export_store_with_calver(
    store: ObjectStore,
    database_url: str,
    country: str,
    city: str,
    region: typing.Optional[str] = None,
    with_bundle: bool = False,
) -> pathlib.Path:
    """Export PostgreSQL/PostGIS tables to a directory following the calver convention."""
    # Create the calver directory in the store.
    folder = await mkdir_calver_directory(store, country, city, region)

    # Export the files to the store.
    await export_store(store, database_url, folder, with_bundle)

    return folder


async def export_store_with_custom_dir(
    store: ObjectStore,
    database_url: str,
    custom_dir: pathlib.Path,
    with_bundle: bool = False,
) -> None:
    """Export PostgreSQL/PostGIS tables to a custom directory."""
    # Create the custom directory in the store.
    await mkdir(store, custom_dir)

    # Export the files to the store.
    await export_store(store, database_url, custom_dir, with_bundle)
