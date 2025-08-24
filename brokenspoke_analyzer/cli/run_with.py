"""Define the run-with sub-command."""

import pathlib
import subprocess
import typing
from importlib import resources

import pandas as pd
import rich
import typer
from loguru import logger
from rich.console import Console

from brokenspoke_analyzer.cli import (
    common,
    configure,
    export,
    importer,
    prepare,
)
from brokenspoke_analyzer.core import (
    analysis,
    compute,
    exporter,
    ingestor,
    runner,
    utils,
)
from brokenspoke_analyzer.core.database import dbcore

app = typer.Typer()
verbose = False


@app.command()
def compose(
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
    export_dir: common.ExportDirOpt = common.DEFAULT_EXPORT_DIR,
    lodes_year: common.LODESYear = common.DEFAULT_LODES_YEAR,
    max_trip_distance: common.MaxTripDistance = common.DEFAULT_MAX_TRIP_DISTANCE,
    mirror: common.Mirror = None,
    no_cache: common.NoCache = False,
    retries: common.Retries = common.DEFAULT_RETRIES,
    s3_bucket: typing.Optional[str] = None,
    with_bundle: typing.Optional[bool] = False,
    with_export: typing.Optional[exporter.Exporter] = exporter.Exporter.local,
    with_parts: common.ComputeParts = common.DEFAULT_COMPUTE_PARTS,
) -> typing.Optional[pathlib.Path]:
    """Manage Docker Compose when running the analysis."""
    database_url = "postgresql://postgres:postgres@localhost:5432/postgres"
    try:
        subprocess.run(
            ["docker", "compose", "up", "-d", "--wait"],
            check=True,
            capture_output=not verbose,
        )
        configure.docker(database_url)
        export_dir_: typing.Optional[pathlib.Path] = run_(
            block_population=block_population,
            block_size=block_size,
            buffer=buffer,
            cache_dir=cache_dir,
            city_speed_limit=city_speed_limit,
            city=city,
            country=country,
            data_dir=data_dir,
            database_url=database_url,
            export_dir=export_dir,
            fips_code=fips_code,
            lodes_year=lodes_year,
            max_trip_distance=max_trip_distance,
            mirror=mirror,
            no_cache=no_cache,
            region=region,
            retries=retries,
            s3_bucket=s3_bucket,
            with_bundle=with_bundle,
            with_export=with_export,
            with_parts=with_parts,
        )
    finally:
        subprocess.run(
            ["docker", "compose", "rm", "-sfv"], check=True, capture_output=True
        )
        subprocess.run(
            ["docker", "volume", "rm", "-f", "brokenspoke-analyzer_postgres"],
            capture_output=True,
        )
    return export_dir_


def run_(
    *,
    city: str,
    country: str,
    database_url: str,
    block_population: typing.Optional[int] = common.DEFAULT_BLOCK_POPULATION,
    block_size: typing.Optional[int] = common.DEFAULT_BLOCK_SIZE,
    buffer: typing.Optional[int] = common.DEFAULT_BUFFER,
    cache_dir: typing.Optional[pathlib.Path] = None,
    city_speed_limit: typing.Optional[int] = common.DEFAULT_CITY_SPEED_LIMIT,
    data_dir: typing.Optional[pathlib.Path] = common.DEFAULT_DATA_DIR,
    export_dir: typing.Optional[pathlib.Path] = common.DEFAULT_EXPORT_DIR,
    fips_code: typing.Optional[str] = common.DEFAULT_CITY_FIPS_CODE,
    lodes_year: typing.Optional[int] = common.DEFAULT_LODES_YEAR,
    max_trip_distance: typing.Optional[int] = common.DEFAULT_MAX_TRIP_DISTANCE,
    mirror: common.Mirror = None,
    no_cache: common.NoCache = False,
    region: typing.Optional[str] = None,
    retries: typing.Optional[int] = common.DEFAULT_RETRIES,
    s3_bucket: typing.Optional[str] = None,
    s3_dir: typing.Optional[pathlib.Path] = None,
    with_bundle: typing.Optional[bool] = False,
    with_export: typing.Optional[exporter.Exporter] = exporter.Exporter.local,
    with_parts: common.ComputeParts = common.DEFAULT_COMPUTE_PARTS,
) -> typing.Optional[pathlib.Path]:
    """Run an analysis."""
    # Make mypy happy.
    if not data_dir:
        raise ValueError("`data_dir` must be set")
    if not block_size:
        raise ValueError("`block_size` must be set")
    if not block_population:
        raise ValueError("`block_population` must be set")
    if not export_dir:
        raise ValueError("`export_dir` must be set")

    # Sanity checks.
    if with_export == exporter.Exporter.s3 and not s3_bucket:
        raise ValueError("the bucket name must be specified when exporting to S3")

    # Ensure US/USA cities have the right parameters.
    country = utils.normalize_country_name(country)
    if utils.is_usa(country):
        if not (region and fips_code != common.DEFAULT_CITY_FIPS_CODE):
            raise ValueError("`state` and `fips_code` are required for US cities")
    else:
        # Ensure FIPS code has the default value for non-US cities.
        fips_code = common.DEFAULT_CITY_FIPS_CODE

    # Prepare the database connection.
    engine = dbcore.create_psycopg_engine(database_url)

    # Prepare the Rich output.
    console = rich.get_console()
    msg = [f"[bold bright_blue]Processing {country}"]
    if region:
        msg.append(region)
    msg.append(f"{city} ({fips_code})")
    console.log(", ".join(msg))

    # Prepare.
    logger.debug(f"{data_dir=}")
    prepare.prepare_cmd(
        block_population=block_population,
        block_size=block_size,
        cache_dir=cache_dir,
        city_speed_limit=city_speed_limit,
        city=city,
        country=country,
        data_dir=data_dir,
        fips_code=fips_code,
        lodes_year=lodes_year,
        mirror=mirror,
        no_cache=no_cache,
        region=region,
        retries=retries,
    )

    # Import.
    console.log("[green]Importing input files into the database...")
    with console.status("Importing..."):
        _, slug = analysis.osmnx_query(country, city, region)
        input_dir = data_dir / slug
        importer.all(
            buffer=buffer,
            city=city,
            country=country,
            data_dir=input_dir,
            database_url=database_url,
            fips_code=fips_code,
            lodes_year=lodes_year,
            region=region,
        )

    # Compute.
    console.log("[green]Computing the data...")
    traversable = resources.files("brokenspoke_analyzer.scripts.sql")
    res = pathlib.Path(traversable._paths[0])  # type: ignore
    sql_script_dir = res.resolve(strict=True)
    boundary_file = input_dir / f"{slug}.shp"
    output_srid = utils.get_srid(boundary_file.resolve(strict=True))
    state_default_speed, city_default_speed = ingestor.retrieve_default_speed_limits(
        engine
    )
    logger.debug(f"{state_default_speed=}")
    logger.debug(f"{city_default_speed=}")
    country = utils.normalize_country_name(country)
    import_jobs = utils.is_usa(country)

    with console.status("[green]Computing..."):
        compute.parts(
            buffer=buffer,
            city_default_speed=city_default_speed,
            compute_parts=with_parts,
            database_url=database_url,
            import_jobs=import_jobs,
            max_trip_distance=max_trip_distance,
            output_srid=output_srid,
            sql_script_dir=sql_script_dir,
            state_default_speed=state_default_speed,
        )

    # Export.
    console.log("[green]Exporting the results...")
    if with_export == exporter.Exporter.none:
        return None
    elif with_export == exporter.Exporter.local:
        export_dir = export.local(
            city=city,
            country=country,
            database_url=database_url,
            export_dir=export_dir,
            region=region,
            with_bundle=with_bundle,
        )
    elif with_export == exporter.Exporter.s3:
        export_dir = export.s3(
            bucket_name=s3_bucket,  # type: ignore
            city=city,
            country=country,
            database_url=database_url,
            region=region,
        )
    elif with_export == exporter.Exporter.s3_custom:
        export_dir = export.s3_custom(
            bucket_name=s3_bucket,  # type: ignore
            database_url=database_url,
            s3_dir=s3_dir,
        )
    return export_dir
