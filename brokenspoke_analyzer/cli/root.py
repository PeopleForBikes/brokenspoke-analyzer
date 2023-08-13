import logging
import pathlib
import sys

import typer
from loguru import logger
from rich.console import Console
from sqlalchemy import create_engine

from brokenspoke_analyzer.cli import (
    common,
    configure,
    export,
    importer,
    prepare,
)
from brokenspoke_analyzer.core import (
    analysis,
    compute,
    constant,
    utils,
)


def callback(verbose: int = typer.Option(0, "--verbose", "-v", count=True)) -> None:
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
app = typer.Typer()
app.add_typer(
    configure.app, name="configure", help="Configure a database for an analysis."
)
app.add_typer(prepare.app, name="prepare", help="Prepare files needed for an analysis.")
app.add_typer(importer.app, name="import", help="Import files into database.")
app.add_typer(export.app, name="export", help="Export tables from database.")


@app.command(name="compute")
def compute_cmd(
    database_url: common.DatabaseURL,
    input_dir: common.InputDir,
    country: common.Country,
    city: common.City,
    state: common.State = None,
    buffer: common.Buffer = common.DEFAULT_BUFFER,
) -> None:
    """Run an analysis."""
    # Make MyPy happy.
    if not buffer:
        raise ValueError("`buffer` must be set")

    # Prepare the database connection.
    engine = create_engine(
        database_url.replace("postgresql://", "postgresql+psycopg://")
    )

    # Prepare directories.
    _, slug = analysis.osmnx_query(country, city, state)
    sql_script_dir = pathlib.Path("scripts/sql")
    boundary_file = input_dir / f"{slug}.shp"

    # Prepare compute params.
    state_default_speed, city_default_speed = (30, None)
    tolerance = compute.Tolerance()
    path_constraint = compute.PathConstraint()
    block_road = compute.BlockRoad()
    score = compute.Score()
    if country.upper() == "US":
        country = "usa"
    import_jobs = country == constant.COUNTRY_USA

    # Compute the output SRID from the boundary file.
    output_srid = int(utils.get_srid(boundary_file.resolve(strict=True)))
    logger.debug(f"{output_srid=}")

    console = Console()
    with console.status("[bold green]Running the full analysis (may take a while)..."):
        compute.compute_all(
            engine=engine,
            sql_script_dir=sql_script_dir,
            output_srid=output_srid,
            buffer=buffer,
            state_default_speed=state_default_speed,
            city_default_speed=city_default_speed,
            tolerance=tolerance,
            path_constraint=path_constraint,
            block_road=block_road,
            score=score,
            import_jobs=import_jobs,
        )
        console.log(f"Analysis for {slug} complete.")
