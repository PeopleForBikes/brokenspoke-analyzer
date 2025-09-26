"""Define the run command."""

import pathlib
import typing

import typer
from typing_extensions import Annotated

from brokenspoke_analyzer.cli import (
    common,
    run_with,
)
from brokenspoke_analyzer.core import (
    exporter,
)
from brokenspoke_analyzer.core.database import dbcore

# Create the CLI app.
app = typer.Typer()
verbose = False


@app.command()
def run(
    database_url: common.DatabaseURL,
    country: common.Country,
    city: common.City,
    region: common.Region = None,
    fips_code: common.FIPSCode = common.DEFAULT_CITY_FIPS_CODE,
    block_population: common.BlockPopulation = common.DEFAULT_BLOCK_POPULATION,
    block_size: common.BlockSize = common.DEFAULT_BLOCK_SIZE,
    buffer: common.Buffer = common.DEFAULT_BUFFER,
    cache_dir: common.CacheDir = None,
    city_speed_limit: common.SpeedLimit = common.DEFAULT_CITY_SPEED_LIMIT,
    data_dir: common.DataDir = common.DEFAULT_DATA_DIR,
    lodes_year: common.LODESYear = common.DEFAULT_LODES_YEAR,
    max_trip_distance: common.MaxTripDistance = common.DEFAULT_MAX_TRIP_DISTANCE,
    mirror: common.Mirror = None,
    no_cache: common.NoCache = False,
    retries: common.Retries = common.DEFAULT_RETRIES,
    s3_bucket: Annotated[
        typing.Optional[str], typer.Option(help="S3 bucket name where to export")
    ] = None,
    s3_dir: typing.Optional[pathlib.Path] = None,
    with_bundle: typing.Optional[bool] = False,
    with_export: typing.Optional[exporter.Exporter] = exporter.Exporter.local,
    with_parts: common.ComputeParts = common.DEFAULT_COMPUTE_PARTS,
) -> None:
    """Run a full analysis."""
    run_with.run_(
        block_population=block_population,
        block_size=block_size,
        buffer=buffer,
        cache_dir=cache_dir,
        city_speed_limit=city_speed_limit,
        city=city,
        country=country,
        data_dir=data_dir,
        database_url=database_url,
        fips_code=fips_code,
        lodes_year=lodes_year,
        max_trip_distance=max_trip_distance,
        mirror=mirror,
        no_cache=no_cache,
        region=region,
        retries=retries,
        s3_bucket=s3_bucket,
        s3_dir=s3_dir,
        with_bundle=with_bundle,
        with_export=with_export,
        with_parts=with_parts,
    )
