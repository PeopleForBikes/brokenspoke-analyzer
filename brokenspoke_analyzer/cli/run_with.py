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
    output_dir: common.OutputDir = common.DEFAULT_OUTPUT_DIR,
    fips_code: common.FIPSCode = common.DEFAULT_CITY_FIPS_CODE,
    export_dir: common.ExportDirOpt = common.DEFAULT_EXPORT_DIR,
    buffer: common.Buffer = common.DEFAULT_BUFFER,
    city_speed_limit: common.SpeedLimit = common.DEFAULT_CITY_SPEED_LIMIT,
    block_size: common.BlockSize = common.DEFAULT_BLOCK_SIZE,
    block_population: common.BlockPopulation = common.DEFAULT_BLOCK_POPULATION,
    lodes_year: common.LODESYear = common.DEFAULT_LODES_YEAR,
    retries: common.Retries = common.DEFAULT_RETRIES,
    max_trip_distance: common.MaxTripDistance = common.DEFAULT_MAX_TRIP_DISTANCE,
    with_export: typing.Optional[exporter.Exporter] = exporter.Exporter.local,
    s3_bucket: typing.Optional[str] = None,
    with_bundle: typing.Optional[bool] = False,
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
            database_url=database_url,
            country=country,
            city=city,
            region=region,
            output_dir=output_dir,
            export_dir=export_dir,
            fips_code=fips_code,
            buffer=buffer,
            city_speed_limit=city_speed_limit,
            block_size=block_size,
            block_population=block_population,
            lodes_year=lodes_year,
            retries=retries,
            max_trip_distance=max_trip_distance,
            with_export=with_export,
            s3_bucket=s3_bucket,
            with_bundle=with_bundle,
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


@app.command()
def original_bna(
    city_shp: pathlib.Path,
    pfb_osm_file: pathlib.Path,
    region: common.Region = None,
    output_dir: common.OutputDir = common.DEFAULT_OUTPUT_DIR,
    docker_image: common.DockerImage = common.DEFAULT_DOCKER_IMAGE,
    container_name: common.ContainerName = common.DEFAULT_CONTAINER_NAME,
    city_fips: common.FIPSCode = common.DEFAULT_CITY_FIPS_CODE,
) -> pathlib.Path:
    """Use the original BNA Docker image to run the analysis."""
    # Make mypy happy.
    if not output_dir:
        raise ValueError("`output_dir` must be set")
    if not docker_image:
        raise ValueError("`docker_image` must be set")
    if not container_name:
        raise ValueError("`container_name` must be set")

    console = Console()
    with console.status("[green]Running the full analysis (may take a while)..."):
        state_abbrev, state_fips = (
            analysis.state_info(region)
            if region
            else (
                runner.NON_US_STATE_ABBREV,
                runner.NON_US_STATE_FIPS,
            )
        )
        logger.debug(f"{state_abbrev=} | {state_fips=}")
        runner.run_analysis(
            state_abbrev,
            state_fips,
            city_shp,
            pfb_osm_file,
            output_dir,
            docker_image,
            container_name,
            city_fips=city_fips,
        )
        console.log(f"Analysis for {city_shp} complete.")

    # Grab the last result directory.
    result_dirs = list(output_dir.glob("local-analysis-*"))
    result_dirs.sort()
    return result_dirs[-1]


@app.command()
def compare(
    country: common.Country,
    city: common.City,
    region: common.Region = None,
    output_dir: common.OutputDir = common.DEFAULT_OUTPUT_DIR,
    fips_code: common.FIPSCode = common.DEFAULT_CITY_FIPS_CODE,
    buffer: common.Buffer = common.DEFAULT_BUFFER,
    city_speed_limit: common.SpeedLimit = common.DEFAULT_CITY_SPEED_LIMIT,
    block_size: common.BlockSize = common.DEFAULT_BLOCK_SIZE,
    block_population: common.BlockPopulation = common.DEFAULT_BLOCK_POPULATION,
    lodes_year: common.LODESYear = common.DEFAULT_LODES_YEAR,
    retries: common.Retries = common.DEFAULT_RETRIES,
    max_trip_distance: common.MaxTripDistance = common.DEFAULT_MAX_TRIP_DISTANCE,
    with_bundle: typing.Optional[bool] = False,
) -> pd.DataFrame:
    """Run the analysis using the original BNA and teh brokenspoke-analyzer."""
    # Make mypy happy.
    if not output_dir:
        raise ValueError("`output_dir` must be set")

    logger.info("Run with compose")
    brokenspoke_export_dir = compose(
        country=country,
        city=city,
        region=region,
        output_dir=output_dir,
        fips_code=fips_code,
        buffer=buffer,
        city_speed_limit=city_speed_limit,
        block_size=block_size,
        block_population=block_population,
        lodes_year=lodes_year,
        retries=retries,
        max_trip_distance=max_trip_distance,
        with_export=exporter.Exporter.local,
        with_bundle=with_bundle,
    )
    if brokenspoke_export_dir is None:
        raise ValueError("the export must be specified")

    logger.info("Run with original BNA")
    _, slug = analysis.osmnx_query(country, city, region)
    city_shp = output_dir / f"{slug}.shp"
    pfb_osm_file = city_shp.with_suffix(".osm")
    original_export_dir = original_bna(
        region=region,
        output_dir=output_dir / slug,
        city_shp=city_shp,
        pfb_osm_file=pfb_osm_file,
        city_fips=fips_code,
        docker_image=common.DEFAULT_DOCKER_IMAGE,
        container_name=common.DEFAULT_CONTAINER_NAME,
    )

    logger.info("Compare the results")
    brokenspoke_scores = brokenspoke_export_dir / "neighborhood_overall_scores.csv"
    original_scores = original_export_dir / "neighborhood_overall_scores.csv"
    output_csv = output_dir / slug / f"{slug}.csv"
    logger.debug(f"{output_csv=}")
    return utils.compare_bna_results(brokenspoke_scores, original_scores, output_csv)


def run_(
    database_url: str,
    country: str,
    city: str,
    region: typing.Optional[str] = None,
    output_dir: typing.Optional[pathlib.Path] = common.DEFAULT_OUTPUT_DIR,
    export_dir: typing.Optional[pathlib.Path] = common.DEFAULT_EXPORT_DIR,
    fips_code: typing.Optional[str] = common.DEFAULT_CITY_FIPS_CODE,
    buffer: typing.Optional[int] = common.DEFAULT_BUFFER,
    city_speed_limit: typing.Optional[int] = common.DEFAULT_CITY_SPEED_LIMIT,
    block_size: typing.Optional[int] = common.DEFAULT_BLOCK_SIZE,
    block_population: typing.Optional[int] = common.DEFAULT_BLOCK_POPULATION,
    lodes_year: typing.Optional[int] = common.DEFAULT_LODES_YEAR,
    retries: typing.Optional[int] = common.DEFAULT_RETRIES,
    max_trip_distance: typing.Optional[int] = common.DEFAULT_MAX_TRIP_DISTANCE,
    with_export: typing.Optional[exporter.Exporter] = exporter.Exporter.local,
    s3_bucket: typing.Optional[str] = None,
    s3_dir: typing.Optional[pathlib.Path] = None,
    with_bundle: typing.Optional[bool] = False,
    with_parts: common.ComputeParts = common.DEFAULT_COMPUTE_PARTS,
) -> typing.Optional[pathlib.Path]:
    """Run an analysis."""
    # Make mypy happy.
    if not output_dir:
        raise ValueError("`output_dir` must be set")
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
    logger.debug(f"{output_dir=}")
    prepare.all(
        country=country,
        city=city,
        region=region,
        fips_code=fips_code,
        output_dir=output_dir,
        city_speed_limit=city_speed_limit,
        block_size=block_size,
        block_population=block_population,
        retries=retries,
    )

    # Import.
    console.log("[green]Importing input files into the database...")
    with console.status("Importing..."):
        _, slug = analysis.osmnx_query(country, city, region)
        input_dir = output_dir / slug
        importer.all(
            database_url=database_url,
            input_dir=input_dir,
            country=country,
            city=city,
            region=region,
            lodes_year=lodes_year,
            buffer=buffer,
            fips_code=fips_code,
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
            database_url=database_url,
            sql_script_dir=sql_script_dir,
            output_srid=output_srid,
            buffer=buffer,
            state_default_speed=state_default_speed,
            city_default_speed=city_default_speed,
            import_jobs=import_jobs,
            max_trip_distance=max_trip_distance,
            compute_parts=with_parts,
        )

    # Export.
    console.log("[green]Exporting the results...")
    with console.status("Exporting..."):
        if with_export == exporter.Exporter.none:
            return None
        elif with_export == exporter.Exporter.local:
            export_dir = export.local(
                database_url=database_url,
                country=country,
                city=city,
                region=region,
                export_dir=export_dir,
                with_bundle=with_bundle,
            )
        elif with_export == exporter.Exporter.s3:
            export_dir = export.s3(
                database_url=database_url,
                bucket_name=s3_bucket,  # type: ignore
                country=country,
                city=city,
                region=region,
            )
        elif with_export == exporter.Exporter.s3_custom:
            export_dir = export.s3_custom(
                database_url=database_url,
                bucket_name=s3_bucket,  # type: ignore
                s3_dir=s3_dir,
            )
    return export_dir
