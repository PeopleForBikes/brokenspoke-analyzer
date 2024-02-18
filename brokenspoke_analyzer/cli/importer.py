"""Define the import sub-command."""

import typer
from typing_extensions import Annotated

from brokenspoke_analyzer.cli import common
from brokenspoke_analyzer.core import ingestor

app = typer.Typer()


@app.command()
def all(
    database_url: common.DatabaseURL,
    input_dir: common.InputDir,
    country: common.Country,
    city: common.City,
    region: common.Region = None,
    fips_code: common.FIPSCode = common.DEFAULT_CITY_FIPS_CODE,
    lodes_year: common.LODESYear = common.DEFAULT_LODES_YEAR,
    buffer: common.Buffer = common.DEFAULT_BUFFER,
) -> None:
    """Import all files into database."""
    # Make MyPy happy.
    if not region:
        raise ValueError("`region` must be set")
    if not fips_code:
        raise ValueError("`fips_code` must be set")
    if not lodes_year:
        raise ValueError("`lodes_year` must be set")
    if not buffer:
        raise ValueError("`buffer` must be set")

    ingestor.all_wrapper(
        database_url=database_url,
        input_dir=input_dir,
        country=country,
        city=city,
        region=region,
        fips_code=fips_code,
        lodes_year=lodes_year,
        buffer=buffer,
    )


@app.command()
def neighborhood(
    database_url: common.DatabaseURL,
    input_dir: common.InputDir,
    country: common.Country,
    city: common.City,
    region: common.Region = None,
    buffer: common.Buffer = common.DEFAULT_BUFFER,
) -> None:
    """Import neighborhood data."""
    # Make MyPy happy.
    if not region:
        raise ValueError("`region` must be set")
    if not buffer:
        raise ValueError("`buffer` must be set")

    ingestor.neighborhood_wrapper(
        database_url=database_url,
        input_dir=input_dir,
        country=country,
        city=city,
        region=region,
        buffer=buffer,
    )


@app.command()
def jobs(
    database_url: common.DatabaseURL,
    input_dir: common.InputDir,
    state_abbreviation: Annotated[str, typer.Argument(help="two-letter US state name")],
    lodes_year: common.LODESYear = common.DEFAULT_LODES_YEAR,
) -> None:
    """Import US census job data."""
    # Make mypy happy.
    if not lodes_year:
        raise ValueError("`lodes_year` must be set")

    ingestor.jobs_wrapper(
        database_url=database_url,
        input_dir=input_dir,
        state_abbreviation=state_abbreviation,
        lodes_year=lodes_year,
    )


@app.command()
def osm(
    database_url: common.DatabaseURL,
    input_dir: common.InputDir,
    country: common.Country,
    city: common.City,
    region: common.Region = None,
    fips_code: common.FIPSCode = common.DEFAULT_CITY_FIPS_CODE,
) -> None:
    """Import OSM data."""
    # Make mypy happy.
    if not region:
        raise ValueError("`region` must be set")
    if not fips_code:
        raise ValueError("`fips_code` must be set")

    ingestor.osm_wrapper(
        database_url=database_url,
        input_dir=input_dir,
        country=country,
        city=city,
        region=region,
        fips_code=fips_code,
    )
