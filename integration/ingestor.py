"""
These tests are gross integration tests that are only being used to help validate the
development of the next version : v2.0.0.

Run:
    bna prepare all usa "santa rosa" "new mexico" 3570670

They will eventually be improved or removed.
"""

import os
import pathlib

from loguru import logger
from sqlalchemy import create_engine

from brokenspoke_analyzer.core import (
    ingestor,
    runner,
)
from brokenspoke_analyzer.core.database import dbcore


def test_import_neighborhood():
    database_url = "postgresql://postgres:postgres@localhost:5432/postgres"
    engine = create_engine(
        database_url.replace("postgresql://", "postgresql+psycopg://")
    )

    os.environ["DATABASE_URL"] = database_url

    output_srid = 32613
    buffer = 2680

    input_dir = pathlib.Path("data")
    boundary_file = input_dir / "santa-rosa-new-mexico-usa.shp"
    population_file = input_dir / "population.shp"
    water_blocks_file = input_dir / "censuswaterblocks.csv"
    print(f"{input_dir=}")
    assert input_dir.exists()
    print(f"{boundary_file=}")
    assert boundary_file.exists()

    ingestor.import_neighborhood(
        engine,
        country="USA",
        boundary_file=boundary_file,
        population_file=population_file,
        water_blocks_file=water_blocks_file,
        output_srid=output_srid,
        buffer=buffer,
    )


def test_retrieve_population():
    database_url = "postgresql://postgres:postgres@localhost:5432/postgres"
    engine = create_engine(
        database_url.replace("postgresql://", "postgresql+psycopg://")
    )
    population = ingestor.retrieve_population(engine)
    print(f"{population=}")
    assert population == 3199


def test_import_jobs():
    database_url = "postgresql://postgres:postgres@localhost:5432/postgres"
    os.environ["DATABASE_URL"] = database_url
    engine = create_engine(
        database_url.replace("postgresql://", "postgresql+psycopg://")
    )
    input_dir = pathlib.Path("data")
    ingestor.import_jobs(engine, "nm", 2019, input_dir)


def test_import_all():
    database_url = "postgresql://postgres:postgres@localhost:5432/postgres"
    engine = create_engine(
        database_url.replace("postgresql://", "postgresql+psycopg://")
    )

    os.environ["DATABASE_URL"] = database_url
    os.environ["PGPASSWORD"] = "postgres"
    os.environ["PGUSER"] = "postgres"
    os.environ["PGHOST"] = "localhost"
    os.environ["PGDATABASE"] = "postgres"
    os.environ["PGPORT"] = "5432"
    os.environ["PFB_DEBUG"] = "1"

    country = "USA"
    state = "new mexico"
    city_fips = "3570670"
    buffer = 2680
    output_srid = 32613
    census_year = 2019
    # state_fips = "35"
    input_dir = pathlib.Path("data")
    boundary_file = input_dir / "santa-rosa-new-mexico-usa.shp"
    population_file = input_dir / "population.shp"
    water_blocks_file = input_dir / "censuswaterblocks.csv"
    osm_file = input_dir / "santa-rosa-new-mexico-usa.osm"
    state_speed_limits_csv = input_dir / "state_fips_speed.csv"
    city_speed_limits_csv = input_dir / "city_fips_speed.csv"

    # Prepare DB.
    logger.debug("Configure the database")
    docker_info = runner.run_docker_info()
    docker_cores = docker_info["NCPU"]
    docker_memory_mb = docker_info["MemTotal"] // (1024**2)
    dbcore.configure_db(engine, docker_cores, docker_memory_mb, os.environ["PGUSER"])

    ingestor.import_all(
        engine,
        country,
        output_srid,
        buffer,
        boundary_file,
        population_file,
        water_blocks_file,
        input_dir,
        osm_file,
        state_speed_limits_csv,
        city_speed_limits_csv,
        city_fips,
        state,
        census_year,
    )


def test_retrieve_boundary_box():
    database_url = "postgresql://postgres:postgres@localhost:5432/postgres"
    engine = create_engine(
        database_url.replace("postgresql://", "postgresql+psycopg://")
    )

    bbox = ingestor.retrieve_boundary_box(engine)
    print(f"{bbox}")
    assert len(bbox) == 4


def test_import_osm_data():
    """Require import neighborhood."""
    database_url = "postgresql://postgres:postgres@localhost:5432/postgres"
    engine = create_engine(
        database_url.replace("postgresql://", "postgresql+psycopg://")
    )

    os.environ["DATABASE_URL"] = database_url

    output_srid = 32613
    state_fips = "35"
    city_fips = "3570670"
    input_dir = pathlib.Path("data")
    osm_file = input_dir / "santa-rosa-new-mexico-usa.osm"
    state_speed_limits_csv = input_dir / "state_fips_speed.csv"
    city_speed_limits_csv = input_dir / "city_fips_speed.csv"

    ingestor.import_osm_data(
        engine,
        osm_file,
        output_srid,
        state_fips,
        city_fips,
        state_speed_limits_csv,
        city_speed_limits_csv,
    )


def test_docker_info():
    d = runner.run_docker_info()
    assert d["NCPU"] == 4
    assert d["MemTotal"] == 2085761024
