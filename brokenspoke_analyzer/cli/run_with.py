import pathlib
import subprocess
import typing
from importlib import resources

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
    database_url: common.DatabaseURL,
    country: common.Country,
    city: common.City,
    state: common.State = None,
    output_dir: typing.Optional[pathlib.Path] = common.OutputDir,
    fips_code: common.FIPSCode = "0",
    buffer: common.Buffer = common.DEFAULT_BUFFER,
    speed_limit: typing.Optional[int] = common.SpeedLimit,
    block_size: typing.Optional[int] = common.BlockSize,
    block_population: typing.Optional[int] = common.BlockPopulation,
    census_year: common.CensusYear = common.DEFAULT_CENSUS_YEAR,
    retries: typing.Optional[int] = common.Retries,
    max_trip_distance: typing.Optional[int] = 2680,
) -> None:
    """Manage Docker Compose when running the analysis."""
    try:
        subprocess.run(["docker", "compose", "up", "-d"], check=True)
        subprocess.run(
            f"until pg_isready -d {database_url}; do sleep 5; done",
            shell=True,
            check=True,
            timeout=60,
        )
        configure.docker(database_url)
        run_(
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


@app.command()
def original_bna(
    state: str,
    city_shp: pathlib.Path,
    pfb_osm_file: pathlib.Path,
    output_dir: typing.Optional[pathlib.Path] = common.OutputDir,
    docker_image: typing.Optional[str] = common.DockerImage,
    container_name: typing.Optional[str] = common.ContainerName,
    city_fips: common.FIPSCode = "0",
) -> None:
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
        state_abbrev, state_fips = analysis.state_info(state) if state else ("0", "0")
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


def run_(
    database_url: str,
    country: str,
    city: str,
    state: typing.Optional[str] = None,
    output_dir: typing.Optional[pathlib.Path] = pathlib.Path("./data"),
    fips_code: typing.Optional[str] = "0",
    buffer: typing.Optional[int] = common.DEFAULT_BUFFER,
    speed_limit: typing.Optional[int] = common.DEFAULT_CITY_SPEED_LIMIT,
    block_size: typing.Optional[int] = common.DEFAULT_BLOCKSIZE,
    block_population: typing.Optional[int] = common.DEFAULT_BLOCK_POPULATION,
    census_year: common.CensusYear = common.DEFAULT_CENSUS_YEAR,
    retries: typing.Optional[int] = common.DEFAULT_RETRIES,
    max_trip_distance: typing.Optional[int] = common.DEFAULT_MAX_TRIP_DISTANCE,
) -> None:
    """Run an analysis."""
    # Make mypy happy.
    if not output_dir:
        raise ValueError("`output_dir` must be set")

    # Prepare the database connection.
    engine = dbcore.create_psycopg_engine(database_url)

    # Prepare.
    logger.info("Prepare")
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
        tolerance=compute.Tolerance(),
        path_constraint=compute.PathConstraint(),
        block_road=compute.BlockRoad(),
        score=compute.Score(),
        import_jobs=import_jobs,
        max_trip_distance=max_trip_distance,
    )

    # Export.
    logger.info("Export")
    export.local_calver(
        database_url=database_url,
        country=country,
        city=city,
        region=state,
        force=False,
        export_dir=input_dir / "results",
    )
