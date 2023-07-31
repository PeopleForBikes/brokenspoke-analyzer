"""Define the configure subcommand."""

import typer
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

from brokenspoke_analyzer.cli import common
from brokenspoke_analyzer.core.database import dbcore

app = typer.Typer()


@app.command()
def docker(
    database_url: common.DatabaseURL,
) -> None:
    """Configures a database running in a docker container."""
    engine = create_engine_(database_url)
    dbcore.configure_docker_db(engine)


@app.command()
def custom(
    cores: int,
    memory_mb: int,
    pguser: str,
    database_url: common.DatabaseURL,
) -> None:
    """Configures a database with custom values."""
    engine = create_engine_(database_url)
    dbcore.configure_db(engine, cores, memory_mb, pguser)


def create_engine_(database_url: str) -> Engine:
    """Create a SQLAlchemy engine."""
    return create_engine(database_url.replace("postgresql://", "postgresql+psycopg://"))
