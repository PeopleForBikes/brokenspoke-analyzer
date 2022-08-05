"""Define the CLI frontend for this library."""
import asyncio
import pathlib
import sys
from typing import Optional

import aiohttp
import geopandas as gpd
import typer
from loguru import logger
from pyrosm import get_data
from rich.console import Console
from slugify import slugify

from brokenspoke_analyzer.core import analysis
from brokenspoke_analyzer.core import processhelper

# Default values
OutputDir = typer.Argument(
    default="./data",
    exists=False,
    file_okay=False,
    dir_okay=True,
    writable=True,
    readable=True,
    resolve_path=True,
)


# Configure the logger.
logger.remove()
logger.add(sys.stderr, level="DEBUG")

# Create the CLI app.
app = typer.Typer()

MAGIC_STATE_NUMBER = 91


@app.command()
def prepare(
    country: str,
    city: str,
    state: Optional[str] = typer.Argument(None),
    output_dir: pathlib.Path = OutputDir,
):
    """Prepare the required files for an analysis."""
    asyncio.run(prepare_(country, state, city, output_dir))


@app.command()
def analyze(
    state: str,
    city_shp: pathlib.Path,
    pfb_osm_file: pathlib.Path,
    output_dir: pathlib.Path = OutputDir,
):
    """Run an analysis."""
    # Retrieve the state info if needed.
    state_abbrev, state_fips = analysis.state_info(state) if state else (0, 0)
    analyze_(
        state_abbrev,
        state_fips,
        city_shp,
        pfb_osm_file,
        output_dir,
    )


@app.command()
def run(
    country: str,
    city: str,
    state: Optional[str] = typer.Argument(None),
    output_dir: pathlib.Path = OutputDir,
):
    """Prepare and run an analysis."""
    asyncio.run(prepare_and_run(country, state, city, output_dir))


async def prepare_and_run(country, state, city, output_dir):
    """Prepare and run an analysis."""
    params = await prepare_(country, state, city, output_dir)
    analyze_(*params)


# pylint: disable=too-many-locals
async def prepare_(country, state, city, output_dir):
    """Prepare and kicks off the analysis."""
    # Prepare the output directory.
    output_dir.mkdir(parents=True, exist_ok=True)

    # Prepare the Rich output.
    console = Console()

    # Retrieve city boundaries.
    with console.status("[bold green]Querying OSM to retrieve the city boudaries..."):
        slug = analysis.retrieve_city_boundaries(output_dir, country, city, state)
        city_shp = output_dir / f"{slug}.shp"
        console.log("Boundary files ready.")

    # Download the OSM region file.
    with console.status("[bold green]Downloading the OSM region file..."):
        dataset = ", ".join(filter(None, [country, state]))
        region_file_path = get_data(dataset, directory=output_dir)
        console.log("OSM Region file downloaded.")

    # Reduce the osm file with osmium.
    with console.status(f"[bold green]Reducing the OSM file for {city} with osmium..."):
        polygon_file = output_dir / f"{slug}.geojson"
        pfb_osm_file = f"{slug}.osm"
        analysis.prepare_city_file(
            output_dir, region_file_path, polygon_file, pfb_osm_file
        )
        console.log(f"OSM file for {city} ready.")

    # Retrieve the state info if needed.
    if state:
        state_abbrev, state_fips = analysis.state_info(state)
    else:
        try:
            state_abbrev, state_fips = analysis.state_info(country)
        except ValueError:
            state_abbrev, state_fips = ("AL", MAGIC_STATE_NUMBER)

    # For non-US cities:
    if state_fips == MAGIC_STATE_NUMBER:
        # Create synthetic population.
        CELL_SIZE = (1000, 1000)
        city_boundaries_gdf = gpd.read_file(city_shp)
        synthetic_population = analysis.create_synthetic_population(
            city_boundaries_gdf, *CELL_SIZE
        )

        # Simulate the census blocks.
        analysis.simulate_census_blocks(
            output_dir, slug, state_fips, synthetic_population
        )

        # Change the speed limit.
        DEFAULT_SPEED_LIMIT_KMH = 50
        analysis.change_speed_limit(
            output_dir, city, state_abbrev, DEFAULT_SPEED_LIMIT_KMH
        )

    # Return the parameters required to perform the analysis.
    # pylint: disable=duplicate-code
    return (
        state_abbrev,
        state_fips,
        city_shp,
        pfb_osm_file,
        output_dir,
    )


# pylint: disable=too-many-arguments,duplicate-code
def analyze_(
    state_abbrev,
    state_fips,
    city_shp,
    pfb_osm_file,
    output_dir,
):
    """Run the analysis."""
    console = Console()
    with console.status("[bold green]Running the full analysis (may take a while)..."):
        processhelper.run_analysis(
            state_abbrev,
            state_fips,
            city_shp,
            pfb_osm_file,
            output_dir,
        )
        console.log(f"Analysis for {city_shp} complete.")


async def _prepare_with_osmrelationid(state, city, osm_relation_id, output_dir):
    # pylint: disable=too-many-locals
    """Prepare and kicks off the analysis."""
    # Prepare the Rich output.
    console = Console()

    # Computed inputs.
    region_file_name = f"{slugify(state)}-latest.osm.pbf"
    slugged_city_state = slugify(f"{city}-{state}")
    polygon_file_name = f"{slugged_city_state}.poly"
    pfb_osm_file = f"{slugged_city_state}.osm"
    state_abbrev, state_fips = analysis.state_info(state)

    # Retrieve the US Census file.
    async with aiohttp.ClientSession(raise_for_status=True) as session:
        # Download the census file.
        with console.status("[bold green]Downloading the US census file..."):
            tiger_file = await analysis.download_census_file(
                session, output_dir, state_fips
            )
            console.log("US Census file downloaded.")

        # Prepare the boudary file.
        with console.status("[bold green]Preparing the boudary file..."):
            city_shp = analysis.prepare_boundary_file(output_dir, city, tiger_file)
            console.log("Boundary file ready.")

        # Download the OSM region file.
        with console.status("[bold green]Downloading the US OSM file..."):
            region_file_path = await analysis.download_osm_us_region_file(
                session, output_dir, state, region_file_name
            )
            console.log("Regional OSM file downloaded.")

        # Download the polygon file.
        with console.status("[bold green]Downloading the polygon file..."):
            polygon_file_path = output_dir / polygon_file_name
            await analysis.download_polygon_file(
                session, osm_relation_id, polygon_file_path
            )
            console.log("Polygon file downloaded.")

    # Reduce the osm file with osmium.
    # Osmium performs way better than osmosis.
    with console.status(f"[bold green]Reducing the OSM file for {city} with osmium..."):
        analysis.prepare_city_file(
            output_dir, region_file_path, polygon_file_path, pfb_osm_file
        )
        console.log(f"OSM file for {city} ready.")

    # Return the parameters required to perform the analysis.
    # pylint: disable=duplicate-code
    return (
        state_abbrev,
        state_fips,
        city_shp,
        pfb_osm_file,
        output_dir,
    )
