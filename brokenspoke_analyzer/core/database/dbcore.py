"""Define functions used to manipulate database data."""

import pathlib
import typing

from sqlalchemy import (
    CursorResult,
    create_engine,
    text,
)
from sqlalchemy.engine import Engine

from brokenspoke_analyzer.core import runner


def execute_query(engine: Engine, query: str) -> None:
    """Execute a query and commit it."""
    with engine.begin() as conn:
        conn.execute(text(query))


def execute_sql_file(engine: Engine, sqlfile: pathlib.Path) -> None:
    """Execute a SQL file."""
    execute_query(engine, sqlfile.read_text())


def import_csv_file_with_header(
    engine: Engine, csvfile: pathlib.Path, table: str
) -> None:
    """
    Import a CSV file into a table.

    refs:
    - https://www.psycopg.org/psycopg3/docs/basic/copy.html#copy
    - https://www.psycopg.org/articles/2020/11/15/psycopg3-copy/

    For some unknown and annoying reason, importing CSV data with a cursor does
    not work. Therefore we used `psql` as fallback.
    """
    # with engine.connect() as conn:
    #     cursor = conn.connection.cursor()
    #     cursor_cmd = (
    #         f"COPY {table} FROM STDIN WITH(FORMAT CSV, HEADER true, DELIMITER ',');"
    #     )
    #     logger.debug(cursor_cmd)
    #     with csvfile.open() as f:
    #         with cursor.copy(cursor_cmd) as copy:
    #             # for line in f.readline():
    #             #     copy.write_row(line)
    #             copy.write(f.read())
    #             # while data := f.readline():
    #             #     copy.write(data)
    #             # logger.debug(data)
    #             # while data := f.read(8096):
    #             #     copy.write(data)
    #     conn.commit()
    database_url = engine.engine.url.set(drivername="postgresql").render_as_string(
        hide_password=False
    )
    psql_cmd = (
        f"\\copy {table} FROM '{csvfile.resolve(strict=True)}' "
        "DELIMITER ',' CSV HEADER;"
    )
    runner.run_psql_command_string(database_url, psql_cmd)


def load_csv_file(
    engine: Engine, sqlfile: pathlib.Path, csvfile: pathlib.Path, table: str
) -> None:
    """Create a table and load the data from the CSV file."""
    # Run the script to create the table.
    execute_sql_file(engine, sqlfile)

    # Load the data from the CSV file.
    import_csv_file_with_header(engine, csvfile, table)


def export_to_csv(engine: Engine, csvfile: pathlib.Path, table: str) -> None:
    """Dump the table content into a CSV file."""
    psql_cmd = f"\\copy {table} TO '{csvfile.resolve()}' WITH (FORMAT CSV, HEADER);"
    database_url = engine.engine.url.set(drivername="postgresql").render_as_string(
        hide_password=False
    )
    runner.run_psql_command_string(database_url, psql_cmd)


def configure_db(engine: Engine, cores: int, memory_mb: int, pguser: str) -> None:
    """
    Configure the database.

    Configures the database with the appropriate settings, extensions and schemas.

    This function is idempotent.
    """
    configure_system(engine, cores, memory_mb)
    configure_extensions(engine)
    configure_schemas(engine, pguser)


def configure_docker_db(engine: Engine) -> None:
    """Configure a database running in Docker."""
    database_url = engine.engine.url
    pguser = database_url.username
    if not pguser:
        raise ValueError("postgresql user must be specified in the databsse engine URL")
    docker_info = runner.run_docker_info()
    docker_cores = docker_info["NCPU"]
    docker_memory_mb = docker_info["MemTotal"] // (1024**2)
    configure_db(engine, docker_cores, docker_memory_mb, pguser)


def create_psycopg_engine(database_url: str) -> Engine:
    """Create a SQLAlchemy engine with the psycopg3 driver."""
    return create_engine(database_url.replace("postgresql://", "postgresql+psycopg://"))


def execute_with_autocommit(engine: Engine, statements: typing.Sequence[str]) -> None:
    """Execute a series of statements with autocommit."""
    with engine.execution_options(isolation_level="AUTOCOMMIT").connect() as conn:
        for statement in statements:
            conn.execute(text(statement))


def configure_system(engine: Engine, cores: int, memory_mb: int) -> None:
    """
    Configure the system parameters.

    This requires elevated permissions.
    """
    statements = [
        f"ALTER SYSTEM SET shared_buffers TO '{memory_mb // 4}MB';",
        f"ALTER SYSTEM SET effective_cache_size TO '{3 * memory_mb // 4}MB';",
        f"ALTER SYSTEM SET work_mem TO '{8 * memory_mb // 1024}MB';",
        f"ALTER SYSTEM SET maintenance_work_mem TO '{memory_mb // 16}MB';",
        f"ALTER SYSTEM SET min_wal_size TO '{memory_mb // 8}MB';",
        f"ALTER SYSTEM SET max_wal_size TO '{memory_mb // 2}MB';",
        "ALTER SYSTEM SET checkpoint_completion_target TO '0.9';",
        "ALTER SYSTEM SET wal_buffers TO '-1';",
        "ALTER SYSTEM SET listen_addresses TO '*';",
        "ALTER SYSTEM SET max_connections TO '100';",
        "ALTER SYSTEM SET random_page_cost TO '1.1';",
        "ALTER SYSTEM SET effective_io_concurrency TO '200';",
        f"ALTER SYSTEM SET max_worker_processes TO '{cores}';",
        f"ALTER SYSTEM SET max_parallel_workers TO '{cores}';",
        f"ALTER SYSTEM SET max_parallel_workers_per_gather TO '{cores // 2}';",
        f"ALTER SYSTEM SET max_parallel_maintenance_workers TO '{cores // 2}';",
    ]
    execute_with_autocommit(engine, statements)


def configure_extensions(engine: Engine) -> None:
    """Configure the required extensions."""
    statements = [
        'CREATE EXTENSION IF NOT EXISTS "postgis";',
        'CREATE EXTENSION IF NOT EXISTS "uuid-ossp";',
        'CREATE EXTENSION IF NOT EXISTS "hstore";',
        'CREATE EXTENSION IF NOT EXISTS "pgrouting";',
    ]
    execute_with_autocommit(engine, statements)


def configure_schemas(engine: Engine, pguser: str) -> None:
    """Configure the schemas."""
    statements = [
        f"CREATE SCHEMA IF NOT EXISTS generated AUTHORIZATION {pguser};",
        f"CREATE SCHEMA IF NOT EXISTS received AUTHORIZATION {pguser};",
        f"CREATE SCHEMA IF NOT EXISTS scratch AUTHORIZATION {pguser};",
        (
            f"ALTER ROLE {pguser} SET search_path TO "
            'generated,received,scratch,"$user",public;'
        ),
    ]
    execute_with_autocommit(engine, statements)


def table_exists(engine: Engine, table: str) -> bool:
    """Check whether a table exists or not."""
    query = f"""SELECT EXISTS (
        SELECT FROM information_schema.tables
        WHERE (table_schema = 'generated' OR table_schema = 'received')
        AND table_name = '{table}'
        );
    """
    with engine.connect() as conn:
        res = conn.execute(text(query))
        return bool(res.scalar_one())
