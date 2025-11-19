"""Define the import sub-command."""

import asyncio

import typer
from typing_extensions import Annotated

from brokenspoke_analyzer.cli import common
from brokenspoke_analyzer.core import ingestor

StateAbbreviation = Annotated[str, typer.Argument(help="two-letter US state name")]

app = typer.Typer()


@app.command()
def all(
    data_dir: common.DataDir,
    database_url: common.DatabaseURL,
    country: common.Country,
    city: common.City,
    region: common.Region = None,
    fips_code: common.FIPSCode = common.DEFAULT_CITY_FIPS_CODE,
    buffer: common.Buffer = common.DEFAULT_BUFFER,
    lodes_year: common.LODESYear = None,
) -> None:
    """Import all files into database."""
    # Make MyPy happy.
    if not fips_code:
        raise ValueError("`fips_code` must be set")
    if not buffer:
        raise ValueError("`buffer` must be set")

    # Set the region as the country if it was not provided.
    if not region:
        region = country

    asyncio.run(
        ingestor.all_wrapper(
            buffer=buffer,
            city=city,
            country=country,
            data_dir=data_dir,
            database_url=database_url,
            fips_code=fips_code,
            lodes_year=lodes_year,
            region=region,
        )
    )


@app.command()
def neighborhood(
    data_dir: common.DataDir,
    database_url: common.DatabaseURL,
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
        buffer=buffer,
        city=city,
        country=country,
        data_dir=data_dir,
        database_url=database_url,
        region=region,
    )


@app.command()
def jobs(
    data_dir: common.DataDir,
    database_url: common.DatabaseURL,
    state_abbreviation: StateAbbreviation,
    lodes_year: common.LODESYear = None,
) -> None:
    """Import US census job data."""
    asyncio.run(
        ingestor.jobs_wrapper(
            data_dir=data_dir,
            database_url=database_url,
            lodes_year=lodes_year,
            state_abbreviation=state_abbreviation,
        )
    )


@app.command()
def osm(
    data_dir: common.DataDir,
    database_url: common.DatabaseURL,
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
        city=city,
        country=country,
        data_dir=data_dir,
        database_url=database_url,
        fips_code=fips_code,
        region=region,
    )
