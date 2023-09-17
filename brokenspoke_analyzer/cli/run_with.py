import pathlib
import subprocess
import typing
from importlib import resources

import pandas as pd
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
    constant,
    ingestor,
    runner,
    utils,
)
from brokenspoke_analyzer.core.database import dbcore

app = typer.Typer()


@app.command()
def compose(
    country: common.Country,
    city: common.City,
    state: common.State = None,
    output_dir: common.OutputDir = common.DEFAULT_OUTPUT_DIR,
    fips_code: common.FIPSCode = common.DEFAULT_CITY_FIPS_CODE,
    export_dir: common.ExportDirOpt = common.DEFAULT_EXPORT_DIR,
    buffer: common.Buffer = common.DEFAULT_BUFFER,
    speed_limit: common.SpeedLimit = common.DEFAULT_CITY_SPEED_LIMIT,
    block_size: common.BlockSize = common.DEFAULT_BLOCK_SIZE,
    block_population: common.BlockPopulation = common.DEFAULT_BLOCK_POPULATION,
    census_year: common.CensusYear = common.DEFAULT_CENSUS_YEAR,
    retries: common.Retries = common.DEFAULT_RETRIES,
    max_trip_distance: common.MaxTripDistance = common.DEFAULT_MAX_TRIP_DISTANCE,
) -> pathlib.Path:
    """Manage Docker Compose when running the analysis."""
    database_url = "postgresql://postgres:postgres@localhost:5432/postgres"
    try:
        subprocess.run(["docker", "compose", "up", "-d"], check=True)
        subprocess.run(
            f"until pg_isready -d {database_url}; do sleep 5; done",
            shell=True,
            check=True,
            timeout=60,
        )
        configure.docker(database_url)
        export_dir = run_(
            database_url=database_url,
            country=country,
            city=city,
            state=state,
            output_dir=output_dir,
            fips_code=fips_code,
            buffer=buffer,
            speed_limit=speed_limit,
            block_size=block_size,
            block_population=block_population,
            census_year=census_year,
            retries=retries,
            max_trip_distance=max_trip_distance,
        )
    finally:
        subprocess.run(["docker", "compose", "rm", "-sfv"], check=True)
        subprocess.run(
            ["docker", "volume", "rm", "-f", "brokenspoke-analyzer_postgres"]
        )
    return export_dir


@app.command()
def original_bna(
    city_shp: pathlib.Path,
    pfb_osm_file: pathlib.Path,
    state: typing.Optional[str] = None,
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
    with console.status("[bold green]Running the full analysis (may take a while)..."):
        state_abbrev, state_fips = (
            analysis.state_info(state)
            if state
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
    state: common.State = None,
    output_dir: common.OutputDir = common.DEFAULT_OUTPUT_DIR,
    fips_code: common.FIPSCode = common.DEFAULT_CITY_FIPS_CODE,
    buffer: common.Buffer = common.DEFAULT_BUFFER,
    speed_limit: common.SpeedLimit = common.DEFAULT_CITY_SPEED_LIMIT,
    block_size: common.BlockSize = common.DEFAULT_BLOCK_SIZE,
    block_population: common.BlockPopulation = common.DEFAULT_BLOCK_POPULATION,
    census_year: common.CensusYear = common.DEFAULT_CENSUS_YEAR,
    retries: common.Retries = common.DEFAULT_RETRIES,
    max_trip_distance: common.MaxTripDistance = common.DEFAULT_MAX_TRIP_DISTANCE,
) -> pd.DataFrame:
    # Make mypy happy.
    if not output_dir:
        raise ValueError("`output_dir` must be set")

    logger.info("Run with compose")
    brokenspoke_export_dir = compose(
        country=country,
        city=city,
        state=state,
        output_dir=output_dir,
        fips_code=fips_code,
        buffer=buffer,
        speed_limit=speed_limit,
        block_size=block_size,
        block_population=block_population,
        census_year=census_year,
        retries=retries,
        max_trip_distance=max_trip_distance,
    )

    logger.info("Run with original BNA")
    _, slug = analysis.osmnx_query(country, city, state)
    city_shp = output_dir / f"{slug}.shp"
    pfb_osm_file = city_shp.with_suffix(".osm")
    original_export_dir = original_bna(
        state=state,
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
    state: typing.Optional[str] = None,
    output_dir: typing.Optional[pathlib.Path] = common.DEFAULT_OUTPUT_DIR,
    export_dir: typing.Optional[pathlib.Path] = common.DEFAULT_EXPORT_DIR,
    fips_code: typing.Optional[str] = common.DEFAULT_CITY_FIPS_CODE,
    buffer: typing.Optional[int] = common.DEFAULT_BUFFER,
    speed_limit: typing.Optional[int] = common.DEFAULT_CITY_SPEED_LIMIT,
    block_size: typing.Optional[int] = common.DEFAULT_BLOCK_SIZE,
    block_population: typing.Optional[int] = common.DEFAULT_BLOCK_POPULATION,
    census_year: common.CensusYear = common.DEFAULT_CENSUS_YEAR,
    retries: typing.Optional[int] = common.DEFAULT_RETRIES,
    max_trip_distance: typing.Optional[int] = common.DEFAULT_MAX_TRIP_DISTANCE,
) -> pathlib.Path:
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

    # Ensure US/USA cities have the right parameters.
    if country.upper() == "US":
        country = "usa"
    if country.upper() == constant.COUNTRY_USA:
        if not (state and fips_code != common.DEFAULT_CITY_FIPS_CODE):
            raise ValueError("`state` and `fips_code` are required for US cities")

    # Prepare the database connection.
    engine = dbcore.create_psycopg_engine(database_url)

    # Prepare.
    logger.info("Prepare")
    logger.debug(f"{output_dir=}")
    prepare.all(
        country=country,
        city=city,
        state=state,
        fips_code=fips_code,
        output_dir=output_dir,
        speed_limit=speed_limit,
        block_size=block_size,
        block_population=block_population,
        retries=retries,
    )

    # Import.
    logger.info("Import")
    _, slug = analysis.osmnx_query(country, city, state)
    input_dir = output_dir / slug
    importer.all(
        database_url=database_url,
        input_dir=input_dir,
        country=country,
        city=city,
        state=state,
        census_year=census_year,
        buffer=buffer,
        fips_code=fips_code,
    )

    # Compute.
    logger.info("Compute")
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
    if country.upper() == "US":
        country = "usa"
    import_jobs = country.upper() == constant.COUNTRY_USA

    compute.all(
        database_url=database_url,
        sql_script_dir=sql_script_dir,
        output_srid=output_srid,
        buffer=buffer,
        state_default_speed=state_default_speed,
        city_default_speed=city_default_speed,
        import_jobs=import_jobs,
        max_trip_distance=max_trip_distance,
    )

    # Export.
    logger.info("Export")
    export_dir = export.local_calver(
        database_url=database_url,
        country=country,
        city=city,
        region=state,
        force=False,
        export_dir=export_dir,
    )
    return export_dir
