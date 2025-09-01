"""Define the configure subcommand."""

import rich
import typer
from typing_extensions import Annotated

from brokenspoke_analyzer.cli import common
from brokenspoke_analyzer.core.database import dbcore

Cores = Annotated[int, typer.Argument(help="number of cores")]
MemoryMB = Annotated[int, typer.Argument(help="memory amount in MB")]
PGUser = Annotated[str, typer.Argument(help="PostgreSQL user name to connect as")]


app = typer.Typer()
console = rich.get_console()


@app.command()
def docker(database_url: common.DatabaseURL) -> None:
    """Configure a database running in a Docker container."""
    console.log("[green]Configuring the Docker database...")
    engine = dbcore.create_psycopg_engine(database_url)
    dbcore.configure_docker_db(engine)


@app.command()
def custom(
    cores: Cores, memory_mb: MemoryMB, pguser: PGUser, database_url: common.DatabaseURL
) -> None:
    """Configure a database with custom values."""
    console.log("[green]Configuring the database with custom settings...")
    system(database_url, cores, memory_mb)
    extensions(database_url)
    schemas(database_url, pguser)


@app.command()
def system(database_url: common.DatabaseURL, cores: Cores, memory_mb: MemoryMB) -> None:
    """Configure the database system parameters."""
    console.log("[green]Configuring the system parameters...")
    engine = dbcore.create_psycopg_engine(database_url)
    dbcore.configure_system(engine, cores, memory_mb)


@app.command()
def extensions(database_url: common.DatabaseURL) -> None:
    """Configure the database extensions."""
    console.log("[green]Configuring the extensions...")
    engine = dbcore.create_psycopg_engine(database_url)
    dbcore.configure_extensions(engine)


@app.command()
def schemas(database_url: common.DatabaseURL, pguser: PGUser) -> None:
    """Configure the database schemas."""
    console.log("[green]Configuring the schemas...")
    engine = dbcore.create_psycopg_engine(database_url)
    dbcore.configure_schemas(engine, pguser)


@app.command()
def reset(database_url: common.DatabaseURL) -> None:
    """Reset the database tables created by a BNA run."""
    console.log("[green]Resetting the database tables...")
    engine = dbcore.create_psycopg_engine(database_url)
    dbcore.reset_tables(engine)
