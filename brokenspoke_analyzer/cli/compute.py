"""Define the compute command."""

import pathlib
from importlib import (
    resources,
)

import rich
import typer
from loguru import logger
from rich.console import Console

from brokenspoke_analyzer.cli import (
    common,
)
from brokenspoke_analyzer.core import (
    analysis,
    compute,
    ingestor,
    utils,
)
from brokenspoke_analyzer.core.database import dbcore

app = typer.Typer()
console = rich.get_console()


@app.command(name="compute")
def compute_cmd(
    database_url: common.DatabaseURL,
    data_dir: common.DataDir,
    country: common.Country,
    city: common.City,
    region: common.Region = None,
    buffer: common.Buffer = common.DEFAULT_BUFFER,
    with_parts: common.ComputeParts = common.DEFAULT_COMPUTE_PARTS,
) -> None:
    """Compute the analysis results."""
    # Make MyPy happy.
    if not buffer:
        raise ValueError("`buffer` must be set")

    # Prepare the database connection.
    engine = dbcore.create_psycopg_engine(database_url)

    # Prepare directories.
    country = utils.normalize_country_name(country)
    _, slug = analysis.osmnx_query(country, city, region)
    traversable = resources.files("brokenspoke_analyzer.scripts.sql")
    res = pathlib.Path(traversable._paths[0])  # type: ignore
    sql_script_dir = res.resolve(strict=True)
    boundary_file = data_dir / f"{slug}.shp"

    # Prepare compute params.
    state_default_speed, city_default_speed = ingestor.retrieve_default_speed_limits(
        engine
    )
    import_jobs = utils.is_usa(country)

    # Compute the output SRID from the boundary file.
    output_srid = utils.get_srid(boundary_file.resolve(strict=True))
    logger.debug(f"{output_srid=}")

    console = Console()
    with console.status("[green]Running the full analysis (may take a while)..."):
        compute.parts(
            buffer=buffer,
            city_default_speed=city_default_speed,
            compute_parts=with_parts,
            database_url=database_url,
            import_jobs=import_jobs,
            output_srid=output_srid,
            sql_script_dir=sql_script_dir,
            state_default_speed=state_default_speed,
        )
        console.log(f"Analysis for {slug} complete.")
