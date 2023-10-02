import asyncio
import logging
import pathlib
import typing

import aiohttp
import geopandas as gpd
import rich
import typer
from loguru import logger
from tenacity import (
    Retrying,
    before_log,
    stop_after_attempt,
)

from brokenspoke_analyzer.cli import common
from brokenspoke_analyzer.core import (
    analysis,
    constant,
    downloader,
    runner,
    utils,
)

app = typer.Typer()


@app.command()
def all(
    country: common.Country,
    city: common.City,
    region: common.Region = None,
    fips_code: common.FIPSCode = common.DEFAULT_CITY_FIPS_CODE,
    output_dir: common.OutputDir = common.DEFAULT_OUTPUT_DIR,
    city_speed_limit: common.SpeedLimit = common.DEFAULT_CITY_SPEED_LIMIT,
    block_size: common.BlockSize = common.DEFAULT_BLOCK_SIZE,
    block_population: common.BlockPopulation = common.DEFAULT_BLOCK_POPULATION,
    retries: common.Retries = common.DEFAULT_RETRIES,
    lodes_year: common.LODESYear = common.DEFAULT_LODES_YEAR,
) -> None:
    """Prepare all the files required for an analysis."""
    # Make MyPy happy.
    if not output_dir:
        raise ValueError("`output_dir` must be set")
    if not city_speed_limit:
        raise ValueError("`city_speed_limit` must be set")
    if not block_size:
        raise ValueError("`block_size` must be set")
    if not block_population:
        raise ValueError("`block_population` must be set")
    if not retries:
        raise ValueError("`retries` must be set")
    if not lodes_year:
        raise ValueError("`lodes_year` must be set")

    # Handles us/usa as the same country.
    if country.upper() == "US":
        country = "usa"

    # Ensure US/USA cities have the right parameters.
    if country.upper() == constant.COUNTRY_USA:
        if not (region and fips_code != common.DEFAULT_CITY_FIPS_CODE):
            raise ValueError("`state` and `fips_code` are required for US cities")
    else:
        # Ensure FIPS code has the default value for non-US cities.
        fips_code = common.DEFAULT_CITY_FIPS_CODE

    logger.debug(f"{output_dir=}")
    asyncio.run(
        prepare_(
            country=country,
            region=region,
            city=city,
            output_dir=output_dir,
            city_speed_limit=city_speed_limit,
            block_size=block_size,
            block_population=block_population,
            retries=retries,
            lodes_year=lodes_year,
        )
    )


async def prepare_(
    country: str,
    city: str,
    output_dir: pathlib.Path,
    city_speed_limit: int,
    block_size: int,
    block_population: int,
    retries: int,
    lodes_year: int,
    region: typing.Optional[str] = None,
) -> None:
    """Prepare and kicks off the analysis."""
    # Compute the city slug.
    _, slug = analysis.osmnx_query(country, city, region)

    # Prepare the output directory.
    output_dir /= slug
    output_dir.mkdir(parents=True, exist_ok=True)

    # Prepare the Rich output.
    console = rich.get_console()

    # Create retrier instance to use for all downloads.
    retryer = Retrying(
        stop=stop_after_attempt(retries),
        reraise=True,
        before=before_log(logger, logging.DEBUG),  # type: ignore
    )

    # Retrieve city boundaries.
    with console.status("[bold green]Querying OSM to retrieve the city boundaries..."):
        slug = retryer(
            analysis.retrieve_city_boundaries, output_dir, country, city, region
        )
        boundary_file = output_dir / f"{slug}.shp"
        console.log("Boundary files ready.")

    # Download the OSM region file.
    with console.status("[bold green]Downloading the OSM region file..."):
        try:
            if not region:
                raise ValueError
            region_file_path = retryer(
                analysis.retrieve_region_file, region, output_dir
            )
        except ValueError:
            region_file_path = retryer(
                analysis.retrieve_region_file, country, output_dir
            )
        region_file_path_md5 = pathlib.Path(str(region_file_path) + ".md5")
        if not utils.file_checksum_ok(region_file_path, region_file_path_md5):
            raise ValueError("Invalid OSM region file")
        console.log("OSM Region file downloaded.")

    # Reduce the osm file with osmium.
    with console.status(f"[bold green]Reducing the OSM file for {city} with osmium..."):
        polygon_file = output_dir / f"{slug}.geojson"
        pfb_osm_file = pathlib.Path(f"{slug}.osm")
        analysis.prepare_city_file(
            output_dir, region_file_path, polygon_file, pfb_osm_file
        )
        console.log(f"OSM file for {city} ready.")

    # Retrieve the state info if needed.
    state_abbrev, state_fips, _ = analysis.derive_state_info(region)

    # Perform some specific operations for non-US cities.
    if state_fips == runner.NON_US_STATE_FIPS:
        # Create synthetic population.
        with console.status("[bold green]Prepare synthetic population..."):
            CELL_SIZE = (block_size, block_size)
            city_boundaries_gdf = gpd.read_file(boundary_file)
            synthetic_population = analysis.create_synthetic_population(
                city_boundaries_gdf, *CELL_SIZE, population=block_population
            )
            console.log("Synthetic population ready.")

        # Simulate the census blocks.
        with console.status("[bold green]Simulate census blocks..."):
            analysis.simulate_census_blocks(output_dir, synthetic_population)
            console.log("Census blocks ready.")

        # Change the speed limit.
        with console.status("[bold green]Adjust default city speed limit..."):
            analysis.change_speed_limit(
                output_dir, city, state_abbrev, city_speed_limit
            )
            console.log(
                f"Default city speed limit adjusted to {city_speed_limit} km/h."
            )
    else:
        async with aiohttp.ClientSession() as session:
            lodes_year = lodes_year
            with console.status(
                f"[bold green]Fetching {lodes_year} US employment data..."
            ):
                await retryer(
                    downloader.download_lodes_data,
                    session,
                    output_dir,
                    state_abbrev,
                    "main",
                    lodes_year,
                )
                await retryer(
                    downloader.download_lodes_data,
                    session,
                    output_dir,
                    state_abbrev,
                    "aux",
                    lodes_year,
                )

            with console.status("[bold green]Fetching US census waterblocks..."):
                await retryer(
                    downloader.download_census_waterblocks, session, output_dir
                )

            with console.status("[bold green]Fetching 2010 US census blocks..."):
                await retryer(
                    downloader.download_2010_census_blocks,
                    session,
                    output_dir,
                    state_fips,
                )

            with console.status("[bold green]Fetching US state speed limits..."):
                await retryer(
                    downloader.download_state_speed_limits, session, output_dir
                )

            with console.status("[bold green]Fetching US city speed limits..."):
                await retryer(
                    downloader.download_city_speed_limits, session, output_dir
                )
