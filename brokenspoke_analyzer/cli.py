"""Define the CLI frontend for this library."""
import asyncio
import pathlib

import typer
from loguru import logger

from brokenspoke_analyzer import main
from brokenspoke_analyzer.core import analysis

# Default values
DEFAULT_OUTPUT = "./data"

# Configure the logger.
logger.remove()

# Create the CLI app.
app = typer.Typer()


@app.command()
def prepare(
    state: str,
    city: str,
    osm_relation_id: str,
    output_dir: pathlib.Path = typer.Argument(
        default=DEFAULT_OUTPUT,
        exists=True,
        file_okay=False,
        dir_okay=True,
        writable=True,
        readable=True,
        resolve_path=True,
    ),
):
    """Prepare the required files for an analysis."""
    asyncio.run(main.prepare(state, city, osm_relation_id, output_dir))


@app.command()
def analyze(
    state: str,
    city: str,
    city_shp: pathlib.Path,
    pfb_osm_file: pathlib.Path,
    output_dir: pathlib.Path = typer.Argument(
        default=DEFAULT_OUTPUT,
        exists=True,
        file_okay=False,
        dir_okay=True,
        writable=True,
        readable=True,
        resolve_path=True,
    ),
):
    """Run an analysis."""
    state_abbrev, state_fips = analysis.state_info(state)
    main.analyze(
        state,
        city,
        state_abbrev,
        state_fips,
        city_shp,
        pfb_osm_file,
        output_dir,
    )


@app.command()
def run(
    state: str,
    city: str,
    osm_relation_id: str,
    output_dir: pathlib.Path = typer.Argument(
        default=DEFAULT_OUTPUT,
        exists=True,
        file_okay=False,
        dir_okay=True,
        writable=True,
        readable=True,
        resolve_path=True,
    ),
):
    """Prepare and run an analysis."""
    params = asyncio.run(prepare(state, city, osm_relation_id, output_dir))
    main.analyze(state, city, *params)
