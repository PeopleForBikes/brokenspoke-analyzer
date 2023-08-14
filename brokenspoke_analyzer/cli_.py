"""Define the CLI frontend for this library."""
import asyncio
import logging
import pathlib
import sys
from typing import Optional

import typer
from loguru import logger

# Default values
OutputDir = typer.Option(
    default="./data",
    exists=False,
    file_okay=False,
    dir_okay=True,
    writable=True,
    readable=True,
    resolve_path=True,
)
DockerImage = typer.Option(
    "azavea/pfb-network-connectivity:0.18.0", help="override the BNA Docker image"
)
SpeedLimit = typer.Option(30, help="override the default speed limit (in mph)")
BlockSize = typer.Option(
    500, help="size of a synthetic block for non-US cities (in meters)"
)
BlockPopulation = typer.Option(
    100, help="population of a synthetic block for non-US cities"
)
ContainerName = typer.Option(
    None, help="give a specific name to the container running the BNA"
)
CityFIPS = typer.Option(None, help="city FIPS code")
Retries = typer.Option(2, help="number of times to retry downloading files")


def callback(verbose: int = typer.Option(0, "--verbose", "-v", count=True)):
    """Define callback to configure global flags."""
    # Configure the logger.

    # Remove any predefined logger.
    logger.remove()

    # The log level gets adjusted by adding/removing `-v` flags:
    #   None    : Initial log level is WARNING.
    #   -v      : INFO
    #   -vv     : DEBUG
    #   -vvv    : TRACE
    initial_log_level = logging.WARNING
    log_format = (
        "<level>{time:YYYY-MM-DDTHH:mm:ssZZ} {level:.3} {name}:{line} {message}</level>"
    )
    log_level = max(initial_log_level - verbose * 10, 0)

    # Set the log colors.
    logger.level("ERROR", color="<red><bold>")
    logger.level("WARNING", color="<yellow>")
    logger.level("SUCCESS", color="<green>")
    logger.level("INFO", color="<cyan>")
    logger.level("DEBUG", color="<blue>")
    logger.level("TRACE", color="<magenta>")

    # Add the logger.
    logger.add(sys.stdout, format=log_format, level=log_level, colorize=True)


# Create the CLI app.
app = typer.Typer(callback=callback)


# pylint: disable=too-many-arguments
# @app.command()
# def prepare(
#     country: str,
#     city: str,
#     state: Optional[str] = typer.Argument(None),
#     output_dir: Optional[pathlib.Path] = OutputDir,
#     speed_limit: Optional[int] = SpeedLimit,
#     block_size: Optional[int] = BlockSize,
#     block_population: Optional[int] = BlockPopulation,
#     retries: Optional[int] = Retries,
# ):
#     """Prepare the required files for an analysis."""
#     asyncio.run(
#         prepare_(
#             country,
#             state,
#             city,
#             output_dir,
#             speed_limit,
#             block_size,
#             block_population,
#             retries,
#         )
#     )


# @app.command()
# def analyze(
#     state: str,
#     city_shp: pathlib.Path,
#     pfb_osm_file: pathlib.Path,
#     output_dir: pathlib.Path = OutputDir,
#     docker_image: Optional[str] = DockerImage,
#     container_name: Optional[str] = ContainerName,
#     city_fips: Optional[str] = CityFIPS,
# ):
#     """Run an analysis."""
#     # Retrieve the state info if needed.
#     state_abbrev, state_fips = analysis.state_info(state) if state else (0, 0)
#     analyze_(
#         state_abbrev,
#         state_fips,
#         city_shp,
#         pfb_osm_file,
#         output_dir,
#         docker_image,
#         container_name,
#         city_fips,
#     )


# pylint: disable=too-many-arguments
@app.command()
def run(
    country: str,
    city: str,
    state: Optional[str] = typer.Argument(None),
    output_dir: pathlib.Path = OutputDir,
    docker_image: Optional[str] = DockerImage,
    speed_limit: Optional[int] = SpeedLimit,
    block_size: Optional[int] = BlockSize,
    block_population: Optional[int] = BlockPopulation,
    container_name: Optional[str] = ContainerName,
    city_fips: Optional[str] = CityFIPS,
    retries: Optional[int] = Retries,
):
    """Prepare and run an analysis."""
    asyncio.run(
        prepare_and_run(
            country,
            state,
            city,
            output_dir,
            docker_image,
            speed_limit,
            block_size,
            block_population,
            container_name,
            city_fips,
            retries,
        )
    )


# pylint: disable=too-many-arguments
async def prepare_and_run(
    country,
    state,
    city,
    output_dir,
    docker_image,
    speed_limit,
    block_size,
    block_population,
    container_name,
    city_fips,
    retries,
):
    """Prepare and run an analysis."""
    speed_file = output_dir / "city_fips_speed.csv"
    speed_file.unlink(missing_ok=True)
    tabblock_file = output_dir / "tabblock2010_91_pophu.zip"
    tabblock_file.unlink(missing_ok=True)
    params = await prepare_(
        country,
        state,
        city,
        output_dir,
        speed_limit,
        block_size,
        block_population,
        retries,
    )
    analyze_(*params, docker_image, container_name, city_fips)


# pylint: disable=too-many-locals,too-many-arguments
# async def prepare_(
#     country,
#     state,
#     city,
#     output_dir,
#     speed_limit,
#     block_size,
#     block_population,
#     retries,
# ):
#     """Prepare and kicks off the analysis."""
#     # Prepare the output directory.
#     output_dir.mkdir(parents=True, exist_ok=True)

#     # Prepare the Rich output.
#     console = Console()

#     # Create retrier instance to use for all downloads
#     retryer = Retrying(stop=stop_after_attempt(retries), reraise=True)

#     # Retrieve city boundaries.
#     with console.status("[bold green]Querying OSM to retrieve the city boundaries..."):
#         slug = retryer(
#             analysis.retrieve_city_boundaries, output_dir, country, city, state
#         )
#         city_shp = output_dir / f"{slug}.shp"
#         console.log("Boundary files ready.")

#     # Download the OSM region file.
#     with console.status("[bold green]Downloading the OSM region file..."):
#         try:
#             if not state:
#                 raise ValueError
#             region_file_path = retryer(analysis.retrieve_region_file, state, output_dir)
#         except ValueError:
#             region_file_path = retryer(
#                 analysis.retrieve_region_file, country, output_dir
#             )

#         console.log("OSM Region file downloaded.")

#     # Reduce the osm file with osmium.
#     with console.status(f"[bold green]Reducing the OSM file for {city} with osmium..."):
#         polygon_file = output_dir / f"{slug}.geojson"
#         pfb_osm_file = f"{slug}.osm"
#         analysis.prepare_city_file(
#             output_dir, region_file_path, polygon_file, pfb_osm_file
#         )
#         console.log(f"OSM file for {city} ready.")

#     # Retrieve the state info if needed.
#     try:
#         if state:
#             state_abbrev, state_fips = analysis.state_info(state)
#         else:
#             state_abbrev, state_fips = analysis.state_info(country)
#     except ValueError:
#         state_abbrev, state_fips = (
#             runner.NON_US_STATE_ABBREV,
#             runner.NON_US_STATE_FIPS,
#         )

#     # Perform some specific operations for non-US cities.
#     if str(state_fips) == runner.NON_US_STATE_FIPS:
#         # Create synthetic population.
#         with console.status("[bold green]Prepare synthetic population..."):
#             CELL_SIZE = (block_size, block_size)
#             city_boundaries_gdf = gpd.read_file(city_shp)
#             synthetic_population = analysis.create_synthetic_population(
#                 city_boundaries_gdf, *CELL_SIZE, population=block_population
#             )
#             console.log("Synthetic population ready.")

#         # Simulate the census blocks.
#         with console.status("[bold green]Simulate census blocks..."):
#             analysis.simulate_census_blocks(output_dir, synthetic_population)
#             console.log("Census blocks ready.")

#         # Change the speed limit.
#         with console.status("[bold green]Adjust default speed limit..."):
#             analysis.change_speed_limit(output_dir, city, state_abbrev, speed_limit)
#             console.log(f"Default speed limit adjusted to {speed_limit} km/h.")
#     else:
#         async with aiohttp.ClientSession() as session:
#             lodes_year = 2019
#             with console.status(
#                 f"[bold green]Fetching {lodes_year} US employment data..."
#             ):
#                 await retryer(
#                     analysis.download_lodes_data,
#                     session,
#                     output_dir,
#                     state_abbrev,
#                     "main",
#                     lodes_year,
#                 )
#                 await retryer(
#                     analysis.download_lodes_data,
#                     session,
#                     output_dir,
#                     state_abbrev,
#                     "aux",
#                     lodes_year,
#                 )

#             with console.status("[bold green]Fetching US census waterblocks..."):
#                 await retryer(analysis.download_census_waterblocks, session, output_dir)

#             with console.status("[bold green]Fetching 2010 US census blocks..."):
#                 await retryer(
#                     analysis.download_2010_census_blocks,
#                     session,
#                     output_dir,
#                     state_fips,
#                 )

#             with console.status("[bold green]Fetching US state speed limits..."):
#                 await retryer(analysis.download_state_speed_limits, session, output_dir)

#             with console.status("[bold green]Fetching US city speed limits..."):
#                 await retryer(analysis.download_city_speed_limits, session, output_dir)

#     # Return the parameters required to perform the analysis.
#     # pylint: disable=duplicate-code
#     return (
#         state_abbrev,
#         state_fips,
#         city_shp,
#         pfb_osm_file,
#         output_dir,
#     )


# pylint: disable=too-many-arguments,duplicate-code
# def analyze_(
#     state_abbrev,
#     state_fips,
#     city_shp,
#     pfb_osm_file,
#     output_dir,
#     docker_image,
#     container_name,
#     city_fips,
# ):
#     """Run the analysis."""
#     console = Console()
#     with console.status("[bold green]Running the full analysis (may take a while)..."):
#         runner.run_analysis(
#             state_abbrev,
#             state_fips,
#             city_shp,
#             pfb_osm_file,
#             output_dir,
#             docker_image,
#             container_name,
#             city_fips=city_fips,
#         )
#         console.log(f"Analysis for {city_shp} complete.")
