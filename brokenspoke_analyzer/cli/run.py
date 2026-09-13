"""Define the run command."""

import asyncio
import pathlib
from typing import Annotated

import rich
import typer
from loguru import logger

from brokenspoke_analyzer.cli import (
    common,
    prepare,
)
from brokenspoke_analyzer.core import (
    exporter,
    utils,
)
from brokenspoke_analyzer.core.pipeline import orchestrator

# Create the CLI app.
app = typer.Typer()
verbose = False


@app.command()
def run(
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
    lodes_year: common.LODESYear = None,
    max_trip_distance: common.MaxTripDistance = common.DEFAULT_MAX_TRIP_DISTANCE,
    mirror: common.Mirror = None,
    s3_bucket: Annotated[
        str | None,
        typer.Option(help="S3 bucket name where to export"),
    ] = None,
    s3_dir: pathlib.Path | None = None,
    with_export: exporter.Exporter = exporter.Exporter.local,
    worldpop_year: common.WorldPopYear = common.DEFAULT_WORLDPOP_YEAR,
    *,
    no_cache: common.NoCache = False,
    skip_prepare: Annotated[
        bool,
        typer.Option(help="Reuse the files a previous prepare already downloaded"),
    ] = False,
    with_bundle: bool = False,
) -> None:
    """Run a full analysis.

    Downloads what the analysis needs, computes the BNA scores, and writes the
    results. No database and no Docker are involved.
    """
    asyncio.run(
        run_(
            block_population=block_population,
            block_size=block_size,
            buffer=buffer,
            cache_dir=cache_dir,
            city=city,
            city_speed_limit=city_speed_limit,
            country=country,
            data_dir=data_dir,
            export_dir=export_dir,
            fips_code=fips_code,
            lodes_year=lodes_year,
            max_trip_distance=max_trip_distance,
            mirror=mirror,
            no_cache=bool(no_cache),
            region=region,
            s3_bucket=s3_bucket,
            s3_dir=s3_dir,
            skip_prepare=skip_prepare,
            with_bundle=with_bundle,
            with_export=with_export,
            worldpop_year=worldpop_year,
        ),
    )


async def run_(
    *,
    city: str,
    country: str,
    block_population: int = common.DEFAULT_BLOCK_POPULATION,
    block_size: int = common.DEFAULT_BLOCK_SIZE,
    buffer: int = common.DEFAULT_BUFFER,
    cache_dir: pathlib.Path | None = None,
    city_speed_limit: int = common.DEFAULT_CITY_SPEED_LIMIT,
    data_dir: pathlib.Path = common.DEFAULT_DATA_DIR,
    export_dir: pathlib.Path = common.DEFAULT_EXPORT_DIR,
    fips_code: str = common.DEFAULT_CITY_FIPS_CODE,
    lodes_year: int | None = None,
    max_trip_distance: int = common.DEFAULT_MAX_TRIP_DISTANCE,
    mirror: str | None = None,
    region: str | None = None,
    s3_bucket: str | None = None,
    s3_dir: pathlib.Path | None = None,
    worldpop_year: int = common.DEFAULT_WORLDPOP_YEAR,
    no_cache: bool = False,
    skip_prepare: bool = False,
    with_bundle: bool = False,
    with_export: exporter.Exporter = exporter.Exporter.local,
) -> pathlib.Path:
    """Run one city's analysis end to end.

    Only this function is `async`, and only because `prepare`'s downloads and
    the optional S3 upload are I/O-bound. The analysis stages are CPU-bound and
    run synchronously inside it: `await` would not parallelise them, and the
    CLI analyses one city at a time, so there is nothing to interleave with.

    Parameters
    ----------
    city, country, region, fips_code
        The place to analyse.
    data_dir
        Where `prepare` downloads to and the analysis reads from.
    export_dir
        Root of the calver output tree.
    skip_prepare
        Reuse an earlier `prepare` run's files instead of downloading again.
    with_export
        Where to publish: locally, or to S3/R2.
    with_bundle
        Also produce a zip of the results.

    Returns
    -------
    pathlib.Path
        The directory the results were written to.

    Raises
    ------
    ValueError
        If a US city is missing its region or FIPS code, or an S3 export is
        requested without a bucket.
    """
    country = utils.normalize_country_name(country)
    if utils.is_usa(country):
        if not (region and fips_code != common.DEFAULT_CITY_FIPS_CODE):
            raise ValueError("`state` and `fips_code` are required for US cities")
    else:
        fips_code = common.DEFAULT_CITY_FIPS_CODE
    if with_export in (exporter.Exporter.s3, exporter.Exporter.r2) and not s3_bucket:
        raise ValueError("the bucket name must be specified when exporting to S3")

    console = rich.get_console()
    where = ", ".join(filter(None, [country, region, f"{city} ({fips_code})"]))
    console.log(f"[bold bright_blue]Processing {where}")

    if skip_prepare:
        logger.info("skipping prepare; reusing the existing data directory")
    else:
        console.log("[green]Preparing the input files...")
        await prepare.prepare_(
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
            no_cache=bool(no_cache),
            region=region,
            worldpop_year=worldpop_year,
        )

    console.log("[green]Running the analysis...")
    inputs = orchestrator.AnalysisInputs(
        country=country,
        city=city,
        region=region,
        fips_code=fips_code,
        data_dir=data_dir,
        max_trip_distance=max_trip_distance,
        boundary_buffer=buffer,
        city_speed_limit=city_speed_limit,
        lodes_year=lodes_year,
    )
    destination = exporter.create_calver_directories(
        country=country,
        city=city,
        region=region,
        base_dir=export_dir,
    )
    destination.mkdir(parents=True, exist_ok=True)
    written = orchestrator.analyze_and_export(inputs, destination)
    console.log(f"[green]Wrote {len(written)} files to {destination}")

    if with_bundle:
        archive = exporter.bundle(destination)
        console.log(f"[green]Bundled the results into {archive}")

    if with_export in (exporter.Exporter.s3, exporter.Exporter.r2):
        await _upload(destination, with_export, s3_bucket, s3_dir)

    return destination


def _files_in(directory: pathlib.Path) -> list[pathlib.Path]:
    """List a directory's files, sorted.

    Kept out of the coroutine so the blocking directory walk does not run on
    the event loop.

    Parameters
    ----------
    directory
        The directory to list.

    Returns
    -------
    list of pathlib.Path
        The files it contains.
    """
    return sorted(path for path in directory.iterdir() if path.is_file())


async def _upload(
    source: pathlib.Path,
    target: exporter.Exporter,
    bucket: str | None,
    s3_dir: pathlib.Path | None,
) -> None:
    """Upload an already-exported directory to object storage.

    Uploads what is on disk rather than re-exporting, so the published files
    are exactly the ones just verified locally.

    Parameters
    ----------
    source
        The directory to upload.
    target
        `s3` or `r2`.
    bucket
        Bucket name.
    s3_dir
        Optional prefix within the bucket.
    """
    if not bucket:
        raise ValueError("a bucket name is required to upload")
    store = (
        exporter.create_s3_store(bucket, s3_dir or source)
        if target == exporter.Exporter.s3
        else exporter.create_r2_store(bucket, s3_dir or source)
    )
    files = _files_in(source)
    for path in files:
        await exporter.upload_file(store, path)
    logger.info(f"uploaded {source} to {target}")
