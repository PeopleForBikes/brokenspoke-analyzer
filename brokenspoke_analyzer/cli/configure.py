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
    """Configures a database running in a Docker container."""
    console.log("[bold green]Configure the Docker database...")
    engine = dbcore.create_psycopg_engine(database_url)
    dbcore.configure_docker_db(engine)


@app.command()
def custom(
    cores: Cores, memory_mb: MemoryMB, pguser: PGUser, database_url: common.DatabaseURL
) -> None:
    """Configures a database with custom values."""
    console.log("[bold green]Configure the database with custom settings...")
    system(database_url, cores, memory_mb)
    extensions(database_url)
    schemas(database_url, pguser)


@app.command()
def system(database_url: common.DatabaseURL, cores: Cores, memory_mb: MemoryMB) -> None:
    """Configures the database system parameters."""
    console.log("[bold green]Configure the system parameters...")
    engine = dbcore.create_psycopg_engine(database_url)
    dbcore.configure_system(engine, cores, memory_mb)


@app.command()
def extensions(database_url: common.DatabaseURL) -> None:
    """Configures the database extensions."""
    console.log("[bold green]Configure the extensions...")
    engine = dbcore.create_psycopg_engine(database_url)
    dbcore.configure_extensions(engine)


@app.command()
def schemas(database_url: common.DatabaseURL, pguser: PGUser) -> None:
    """Configures the database schemas."""
    console.log("[bold green]Configure the schemas...")
    engine = dbcore.create_psycopg_engine(database_url)
    dbcore.configure_schemas(engine, pguser)
