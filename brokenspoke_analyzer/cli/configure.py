"""Define the configure subcommand."""

import typer

from brokenspoke_analyzer.cli import common
from brokenspoke_analyzer.core.database import dbcore

app = typer.Typer()


@app.command()
def docker(
    database_url: common.DatabaseURL,
) -> None:
    """Configures a database running in a docker container."""
    engine = dbcore.create_psycopg_engine(database_url)
    dbcore.configure_docker_db(engine)


@app.command()
def custom(
    cores: int,
    memory_mb: int,
    pguser: str,
    database_url: common.DatabaseURL,
) -> None:
    """Configures a database with custom values."""
    engine = dbcore.create_psycopg_engine(database_url)
    dbcore.configure_db(engine, cores, memory_mb, pguser)
