"""Define the prepare sub-command."""

import asyncio
import logging
import os
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
    datastore,
    runner,
    utils,
)

app = typer.Typer()

AWS_REGION = "AWS_REGION"
BNA_CACHE_AWS_S3_BUCKET = "BNA_CACHE_AWS_S3_BUCKET"


@app.command()
def all(
    country: common.Country,
    city: common.City,
    region: common.Region = None,
    block_population: common.BlockPopulation = common.DEFAULT_BLOCK_POPULATION,
    block_size: common.BlockSize = common.DEFAULT_BLOCK_SIZE,
    city_speed_limit: common.SpeedLimit = common.DEFAULT_CITY_SPEED_LIMIT,
    fips_code: common.FIPSCode = common.DEFAULT_CITY_FIPS_CODE,
    lodes_year: common.LODESYear = common.DEFAULT_LODES_YEAR,
    output_dir: common.OutputDir = common.DEFAULT_OUTPUT_DIR,
    retries: common.Retries = common.DEFAULT_RETRIES,
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
    country = utils.normalize_country_name(country)

    # Ensure US/USA cities have the right parameters.
    if utils.is_usa(country):
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
    logger.info(f"{output_dir=}")

    # Prepare the Rich output.
    console = rich.get_console()

    # Create retrier instance to use for all downloads.
    retryer = Retrying(
        stop=stop_after_attempt(retries),
        reraise=True,
        before=before_log(logger, logging.DEBUG),  # type: ignore
    )

    # Retrieve city boundaries.
    console.log(
        f"[green]Querying OSM to retrieve {city} boundaries...",
    )
    slug = retryer(analysis.retrieve_city_boundaries, output_dir, country, city, region)
    boundary_file = output_dir / f"{slug}.shp"

    # Download the OSM region file.
    osm_region = region if region else country
    console.log(
        f"[green]Fetching the OSM region file for {osm_region}...",
    )
    with console.status("Downloading..."):
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

    # Reduce the osm file with osmium.
    console.log(f"[green]Reducing the OSM file for {city} with osmium...")
    polygon_file = output_dir / f"{slug}.geojson"
    pfb_osm_file = pathlib.Path(f"{slug}.osm")
    analysis.prepare_city_file(output_dir, region_file_path, polygon_file, pfb_osm_file)

    # Retrieve the state info if needed.
    state_abbrev, state_fips, _ = analysis.derive_state_info(region)

    # Perform some specific operations for non-US cities.
    if state_fips == runner.NON_US_STATE_FIPS:
        # Create synthetic population.
        console.log("[green]Preparing synthetic population...")
        CELL_SIZE = (block_size, block_size)
        city_boundaries_gdf = gpd.read_file(boundary_file)
        synthetic_population = analysis.create_synthetic_population(
            city_boundaries_gdf, *CELL_SIZE, population=block_population
        )

        # Simulate the census blocks.
        console.log("[green]Simulating census blocks...")
        analysis.simulate_census_blocks(output_dir, synthetic_population)

        # Change the speed limit.
        console.log(
            f"[green]Adjusting default city speed limit to {city_speed_limit} km/h..."
        )
        analysis.change_speed_limit(output_dir, city, state_abbrev, city_speed_limit)
    else:
        # Prepare the caching strategy.
        cache_aws_s3_bucket = None
        match os.getenv("BNA_CACHING_STRATEGY"):
            case "USER_CACHE":
                caching_strategy = datastore.CacheType.USER_CACHE
            case "AWS_S3":
                caching_strategy = datastore.CacheType.AWS_S3
                cache_aws_s3_bucket = os.getenv(BNA_CACHE_AWS_S3_BUCKET)
                if not cache_aws_s3_bucket:
                    raise ValueError(
                        f"the name of the S3 bucket must be specified in the {BNA_CACHE_AWS_S3_BUCKET} environment variable"
                    )
                aws_region = os.getenv(AWS_REGION)
                if not aws_region:
                    raise ValueError("AWS_REGION must be set")

            case _:
                caching_strategy = datastore.CacheType.NONE
        logger.debug(f"{caching_strategy=}")
        logger.debug(f"{cache_aws_s3_bucket=}")
        bna_store = datastore.BNADataStore(
            output_dir, caching_strategy, s3_bucket=cache_aws_s3_bucket
        )

        # Fetch the data.
        async with aiohttp.ClientSession() as session:
            console.log("[green]Fetching US state speed limits...")
            with console.status("Downloading..."):
                await bna_store.download_state_speed_limits(session)

            console.log("[green]Fetching US city speed limits...")
            with console.status("Downloading..."):
                await bna_store.download_city_speed_limits(session)

            console.log(f"[green]Fetching US employment data ({lodes_year})...")
            with console.status("Downloading..."):
                await bna_store.download_lodes_data(session, state_abbrev, lodes_year)

            console.log("[green]Fetching US census blocks (2020)...")
            with console.status("Downloading..."):
                await bna_store.download_2020_census_blocks(session, state_fips)
