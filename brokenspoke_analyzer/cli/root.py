import asyncio
import pathlib
from typing import Optional

import typer
from rich.console import Console

from brokenspoke_analyzer.cli import (
    common,
    export,
    importer,
    prepare,
)
from brokenspoke_analyzer.core import (
    analysis,
    runner,
)

app = typer.Typer()
app.add_typer(prepare.app, name="prepare", help="Prepare files needed for an analysis.")
app.add_typer(importer.app, name="import", help="Import files into database.")
app.add_typer(export.app, name="export", help="Export tables from database.")


@app.command()
def compute(
    state: str,
    city_shp: pathlib.Path,
    pfb_osm_file: pathlib.Path,
    output_dir: pathlib.Path = common.OutputDir,
    docker_image: Optional[str] = common.DockerImage,
    container_name: Optional[str] = common.ContainerName,
    city_fips: Optional[str] = common.CityFIPS,
):
    """Run an analysis."""
    # Retrieve the state info if needed.
    state_abbrev, state_fips = analysis.state_info(state) if state else (0, 0)
    compute_(
        state_abbrev,
        state_fips,
        city_shp,
        pfb_osm_file,
        output_dir,
        docker_image,
        container_name,
        city_fips,
    )


# pylint: disable=too-many-arguments,duplicate-code
def compute_(
    state_abbrev,
    state_fips,
    city_shp,
    pfb_osm_file,
    output_dir,
    docker_image,
    container_name,
    city_fips,
):
    """Run the analysis."""
    console = Console()
    with console.status("[bold green]Running the full analysis (may take a while)..."):
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


@app.command()
def run(
    country: str,
    city: str,
    state: Optional[str] = typer.Argument(None),
    output_dir: pathlib.Path = common.OutputDir,
    docker_image: Optional[str] = common.DockerImage,
    speed_limit: Optional[int] = common.SpeedLimit,
    block_size: Optional[int] = common.BlockSize,
    block_population: Optional[int] = common.BlockPopulation,
    container_name: Optional[str] = common.ContainerName,
    city_fips: Optional[str] = common.CityFIPS,
    retries: Optional[int] = common.Retries,
):
    """Prepare all files and run an analysis."""
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
    """Prepare all files and run an analysis."""
    speed_file = output_dir / "city_fips_speed.csv"
    speed_file.unlink(missing_ok=True)
    tabblock_file = output_dir / "tabblock2010_91_pophu.zip"
    tabblock_file.unlink(missing_ok=True)
    params = await prepare.prepare_(
        country,
        state,
        city,
        output_dir,
        speed_limit,
        block_size,
        block_population,
        retries,
    )
    compute.compute_(*params, docker_image, container_name, city_fips)
