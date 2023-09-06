import typer
from loguru import logger
from typing_extensions import Annotated

from brokenspoke_analyzer.cli import common
from brokenspoke_analyzer.core import (
    analysis,
    constant,
    ingestor,
    utils,
)
from brokenspoke_analyzer.core.database import dbcore

app = typer.Typer()


@app.command()
def all(
    database_url: common.DatabaseURL,
    input_dir: common.InputDir,
    country: common.Country,
    city: common.City,
    state: common.State = None,
    fips_code: common.FIPSCode = "0",
    census_year: common.CensusYear = common.DEFAULT_CENSUS_YEAR,
    buffer: common.Buffer = common.DEFAULT_BUFFER,
) -> None:
    """Import all files into database."""
    neighborhood(
        input_dir=input_dir,
        country=country,
        city=city,
        state=state,
        database_url=database_url,
        buffer=buffer,
    )
    # Derive state FIPS code from state name.
    state_abbrev, _, import_jobs = analysis.derive_state_info(state)
    logger.debug(f"{import_jobs=}")
    if import_jobs == "1":
        jobs(
            input_dir=input_dir,
            state_abbreviation=state_abbrev,
            census_year=census_year,
            database_url=database_url,
        )
    osm(
        input_dir=input_dir,
        country=country,
        city=city,
        state=state,
        fips_code=fips_code,
        database_url=database_url,
    )


@app.command()
def neighborhood(
    database_url: common.DatabaseURL,
    input_dir: common.InputDir,
    country: common.Country,
    city: common.City,
    state: common.State = None,
    buffer: common.Buffer = common.DEFAULT_BUFFER,
) -> None:
    """Import neighborhood data."""
    # Make MyPy happy.
    if not buffer:
        raise ValueError("a buffer value is required")

    # Ensure US/USA cities have the right parameters.
    if country.upper() == "US":
        country = "usa"
    if country.upper() == constant.COUNTRY_USA and not state:
        raise ValueError("`state` is required for US cities")

    # Prepare the database connection.
    engine = dbcore.create_psycopg_engine(database_url)

    # Prepare the files to import.
    _, slug = analysis.osmnx_query(country, city, state)
    boundary_file = input_dir / f"{slug}.shp"
    population_file = input_dir / "population.shp"
    water_blocks_file = input_dir / "censuswaterblocks.csv"

    # compute the outpur SRID from the boundary file.
    output_srid = utils.get_srid(boundary_file.resolve(strict=True))
    logger.debug(f"{output_srid=}")

    # Import the neighborhood data.
    ingestor.import_neighborhood(
        engine,
        country=country.upper(),
        boundary_file=boundary_file,
        population_file=population_file.resolve(strict=True),
        water_blocks_file=water_blocks_file.resolve(),
        output_srid=output_srid,
        buffer=buffer,
    )


@app.command()
def jobs(
    database_url: common.DatabaseURL,
    input_dir: common.InputDir,
    state_abbreviation: Annotated[str, typer.Argument(help="two-letter US state name")],
    census_year: common.CensusYear = common.DEFAULT_CENSUS_YEAR,
) -> None:
    """Import US census job data."""
    # Make mypy happy.
    if not census_year:
        raise ValueError("`census_year` must be set")

    # validate the US state.
    state_abbreviation = state_abbreviation.lower()
    if len(state_abbreviation) != 2:
        raise ValueError("a state abbreviation must be 2 letter long")

    # Prepare the database connection.
    engine = dbcore.create_psycopg_engine(database_url)

    # Import the jobs.
    ingestor.import_jobs(engine, state_abbreviation, census_year, input_dir)


@app.command()
def osm(
    database_url: common.DatabaseURL,
    input_dir: common.InputDir,
    country: common.Country,
    city: common.City,
    state: common.State = None,
    fips_code: common.FIPSCode = "0",
) -> None:
    """Import OSM data."""
    # Make mypy happy.
    if not fips_code:
        raise ValueError("`fips_code` must be set")

    # Prepare the database connection.
    engine = dbcore.create_psycopg_engine(database_url)

    # Prepare the files to import.
    _, slug = analysis.osmnx_query(country, city, state)
    boundary_file = input_dir / f"{slug}.shp"
    osm_file = input_dir / f"{slug}.osm"
    state_speed_limits_csv = input_dir / "state_fips_speed.csv"
    city_speed_limits_csv = input_dir / "city_fips_speed.csv"

    # Compute the output SRID from the boundary file.
    output_srid = utils.get_srid(boundary_file.resolve(strict=True))
    logger.debug(f"{output_srid=}")

    # Derive state FIPS code from state name.
    _, state_fips, _ = analysis.derive_state_info(state)

    ingestor.import_osm_data(
        engine,
        osm_file,
        output_srid,
        state_fips,
        fips_code,
        state_speed_limits_csv,
        city_speed_limits_csv,
    )
