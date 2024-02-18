"""Define functions that will be use to ingest the data."""

import pathlib
import subprocess
import typing
from enum import Enum
from importlib import resources

from loguru import logger
from sqlalchemy import text
from sqlalchemy.engine import Engine

from brokenspoke_analyzer.cli import common
from brokenspoke_analyzer.core import (
    analysis,
    constant,
    runner,
    utils,
)
from brokenspoke_analyzer.core.database import dbcore

# Define table constants.
BOUNDARY_TABLE = "neighborhood_boundary"
CENSUS_BLOCKS_TABLE = "neighborhood_census_blocks"
CITY_SPEED_TABLE = "city_speed"
STATE_SPEED_TABLE = "state_speed"
WATER_BLOCKS_TABLE = "water_blocks"
RESIDENTIAL_SPEED_LIMIT_TABLE = "residential_speed_limit"
script_dir = resources.files("brokenspoke_analyzer.scripts")

# https://gis.stackexchange.com/questions/48949/epsg-3857-or-4326-for-web-mapping
# The data in Open Street Map database is stored in a gcs with units decimal
# degrees & datum of wgs84. (EPSG: 4326)
ESPG_4326 = 4326


def import_and_transform_shapefile(
    engine: Engine,
    shapefile: pathlib.Path,
    table: str,
    output_srid: int,
    input_srid: typing.Optional[int] = ESPG_4326,
) -> None:
    """Import a shapefile into PostGIS with shp2pgsql."""
    logger.info(f"Importing {shapefile} into {table} with SRID {input_srid}")
    database_url = engine.engine.url.set(drivername="postgresql").render_as_string(
        hide_password=False
    )

    # Note(rgreinho): I was not able to validate that this is truly needed, but
    # since it was in the original script, I added it back here. It would
    # require move investigation to ensure we do not need this line.
    #
    # Create the table first to prevent the transform_query to fail.
    shp2pgsql_cmd = [
        "shp2pgsql",
        "-p",
        "-I",
        "-D",
        "-s",
        str(input_srid),
        str(shapefile),
        table,
    ]
    logger.debug(f"{' '.join(shp2pgsql_cmd)}")
    shp2pgsql = subprocess.run(
        shp2pgsql_cmd, capture_output=True, encoding="utf-8", check=True
    )
    subprocess.run(
        ["psql", database_url],
        input=shp2pgsql.stdout,
        capture_output=True,
        check=True,
        text=True,
    )

    # Drop the table and creates a new one with the data in the Shape file.
    shp2pgsql_cmd.remove("-p")
    shp2pgsql_cmd.insert(1, "-d")
    logger.debug(f"{' '.join(shp2pgsql_cmd)}")
    shp2pgsql = subprocess.run(
        shp2pgsql_cmd, capture_output=True, encoding="utf-8", check=True
    )
    # TODO(rgreinho): capture_output should be False in debug mode in order to
    # display the output on the screen.
    subprocess.run(
        ["psql", database_url],
        input=shp2pgsql.stdout,
        capture_output=True,
        check=True,
        text=True,
    )

    # Reproject the geometry to the `output_srid`.
    transform_query = (
        f"ALTER TABLE {table} "
        f"ALTER COLUMN geom TYPE geometry(MultiPolygon,{output_srid}) "
        f"USING ST_Force2d(ST_Transform(geom,{output_srid}))"
    )
    dbcore.execute_query(engine, transform_query)


def delete_block_outside_buffer(engine: Engine, buffer: int) -> None:
    """Delete the blocks which are outside the boundaries+buffer."""
    query = (
        "DELETE FROM neighborhood_census_blocks AS blocks "
        "USING neighborhood_boundary AS boundary "
        f"WHERE NOT ST_DWithin(blocks.geom, boundary.geom, {buffer})"
    )
    dbcore.execute_query(engine, query)


def load_water_blocks(engine: Engine, csvfile: pathlib.Path) -> None:
    """Create the water blocks table and load the data into it from a CSV file."""
    sql_script_dir = pathlib.Path(script_dir._paths[0]) / "sql"  # type: ignore
    dbcore.load_csv_file(
        engine,
        sql_script_dir / "create_us_water_blocks_table.sql",
        csvfile,
        WATER_BLOCKS_TABLE,
    )


def delete_water_blocks(engine: Engine) -> None:
    """Delete the water blocks located within the city boundaries."""
    query = (
        f"DELETE FROM {CENSUS_BLOCKS_TABLE} AS blocks "
        f"USING {WATER_BLOCKS_TABLE} AS water "
        "WHERE blocks.BLOCKID10 = water.geoid;"
    )
    dbcore.execute_query(engine, query)


def retrieve_population(engine: Engine) -> int:
    """Retrieve the population from the imported census data."""
    with engine.connect() as conn:
        result = conn.execute(text("SELECT SUM(pop10) FROM neighborhood_census_blocks"))
        return int(result.scalar_one())


def import_neighborhood(
    engine: Engine,
    country: str,
    boundary_file: pathlib.Path,
    population_file: pathlib.Path,
    water_blocks_file: pathlib.Path,
    output_srid: int,
    buffer: int,
) -> None:
    """
    Import neighborhood data.

    This function is idempotent. The data will be recreated every time.
    """
    logger.debug(f"{country=}")
    logger.debug(f"{output_srid=}")
    logger.debug(f"{buffer=}")
    logger.debug(f"{boundary_file=}")
    logger.debug(f"{population_file=}")
    logger.debug(f"{water_blocks_file=}")

    # Import neighborhood boundary.
    logger.info("Importing neighborhood boundary...")
    import_and_transform_shapefile(
        engine, boundary_file, BOUNDARY_TABLE, output_srid=output_srid
    )

    # Import census blocks.
    # By convention, this file is always named `population.shp`.
    logger.info("Importing census blocks...")
    import_and_transform_shapefile(
        engine, population_file, CENSUS_BLOCKS_TABLE, output_srid=output_srid
    )

    # Discard blocks outside of the boundary+buffer.
    logger.info(f"Removing blocks outside buffer with size {buffer}m...")
    delete_block_outside_buffer(engine, buffer)

    # For US cities, remove the water blocks.
    if country.upper() == constant.COUNTRY_USA:
        logger.info("Removing water blocks...")
        # By convention, this file is always named `censuswaterblocks.csv`.
        load_water_blocks(engine, water_blocks_file)
        delete_water_blocks(engine)

    # Ensure there are inhabitants within the boundaries.
    logger.info("Retrieving the population...")
    population = retrieve_population(engine)
    logger.debug(f"{population=}")
    if population == 0:
        raise ValueError("the population cannot be equal to zero")


class LODESPart(Enum):
    """Represent the part of the state file."""

    MAIN = "main"
    AUX = "aux"


def load_jobs(
    engine: Engine, state: str, lodes_part: LODESPart, csvfile: pathlib.Path
) -> None:
    """Load employment data from the US census website."""
    # Create table.
    table = f"state_od_{lodes_part.value}_JT00"
    query = (
        f"DROP TABLE IF EXISTS {table};"
        f"CREATE TABLE {table} ("
        "w_geocode varchar(15),"
        "h_geocode varchar(15),"
        "S000 integer,"
        "SA01 integer,"
        "SA02 integer,"
        "SA03 integer,"
        "SE01 integer,"
        "SE02 integer,"
        "SE03 integer,"
        "SI01 integer,"
        "SI02 integer,"
        "SI03 integer,"
        "createdate varchar(32));"
    )
    dbcore.execute_query(engine, query)

    # Load the data from the CSV file.
    dbcore.import_csv_file_with_header(engine, csvfile, table)


def retrieve_boundary_box(engine: Engine) -> tuple[float, float, float, float]:
    """Retrieve the city boundary box."""
    query = (
        f"SELECT ST_Extent(ST_Transform(geom, {ESPG_4326})) FROM {CENSUS_BLOCKS_TABLE};"
    )
    with engine.connect() as conn:
        result = conn.execute(text(query))
        row = result.first()
        res = ", ".join(row[0][4:-1].split())  # type: ignore
        split_res = res.split(",")
        return (
            float(split_res[0]),
            float(split_res[1]),
            float(split_res[2]),
            float(split_res[3]),
        )


def import_jobs(
    engine: Engine, state: str, lodes_year: int, input_dir: pathlib.Path
) -> None:
    """
    Import all jobs from US census data.

    This function is idempotent. The data will be recreated every time.
    """
    state = state.lower()
    for part in LODESPart:
        csvfile = input_dir / f"{state}_od_{part.value}_JT00_{lodes_year}.csv"
        csvfile = csvfile.resolve(strict=True)
        logger.debug(f"Importing job file: {csvfile}")
        if not csvfile.exists():
            raise ValueError(f"the job data file {csvfile} was not found")
        load_jobs(engine, state, part, csvfile)


# Compare the boundary box computed by PostGIS Vs GeoPandas.
# Santa Rosa, NM
# BBOX:
#   w/ SQL: -104.87012000000001,34.851831,-104.506362,35.051820000000006
#   w/ gpd: array([-104.714757,   34.905372, -104.629528,   34.955892])


def retrieve_state_speed_limit(engine: Engine, state_fips: str) -> str | None:
    """Retrieve the state speed limit from the imported speed limit data."""
    query = f"SELECT speed FROM state_speed WHERE fips_code_state = '{state_fips}';"
    return retrieve_speed_limit(engine, query)


def retrieve_city_speed_limit(engine: Engine, city_fips: str) -> str | None:
    """Retrieve the city speed limit from the imported speed limit data."""
    query = f"SELECT speed FROM city_speed WHERE fips_code_city = '{city_fips}';"
    return retrieve_speed_limit(engine, query)


def retrieve_speed_limit(engine: Engine, query: str) -> str | None:
    """Retrieve the speed limit from the imported speed limit data."""
    with engine.connect() as conn:
        result = conn.execute(text(query))
        row = result.first()
        return str(row.speed).strip() if row else None


def manage_speed_limits(
    engine: Engine,
    state_fips: str,
    city_fips: str,
    state_speed_limits_csv: pathlib.Path,
    city_speed_limits_csv: pathlib.Path,
    city_speed_limit_override: typing.Optional[str] = None,
) -> None:
    """Manage the state and city speed limits.."""
    # Prepare speed tables.
    sql_script_dir = pathlib.Path(script_dir._paths[0]) / "sql"  # type: ignore
    speed_table_script = sql_script_dir / "speed_tables.sql"
    dbcore.execute_sql_file(engine, speed_table_script)

    # Manage state speed limit.
    logger.info("Importing state speed limits...")
    state_default_speed_limit = None
    if state_fips != runner.NON_US_STATE_FIPS:
        dbcore.import_csv_file_with_header(
            engine, state_speed_limits_csv, STATE_SPEED_TABLE
        )
        state_default_speed_limit = retrieve_state_speed_limit(engine, state_fips)
    logger.debug(
        f'The speed limit for the state "{state_fips}" is {state_default_speed_limit}.'
    )

    # Manage city speed limit.
    logger.info("Importing city speed limits...")
    city_default_speed_limit = None
    if city_speed_limit_override:
        city_default_speed_limit = city_speed_limit_override
    else:
        dbcore.import_csv_file_with_header(
            engine, city_speed_limits_csv, CITY_SPEED_TABLE
        )
        city_default_speed_limit = retrieve_city_speed_limit(engine, city_fips)
    logger.debug(
        f'The speed limit for the city "{city_fips}" is {city_default_speed_limit}.'
    )

    # Save default values.
    logger.info("Saving speed limits into the database...")
    query = (
        f"INSERT INTO {RESIDENTIAL_SPEED_LIMIT_TABLE} "
        "(state_fips_code, city_fips_code, state_speed,city_speed) "
        f"VALUES ({state_fips}, {city_fips}, {state_default_speed_limit or 'NULL'}, "
        f"{city_default_speed_limit or 'NULL'});"
    )
    dbcore.execute_query(engine, query)

    # Validate data to prevent moving forward with corrupted values.
    logger.info("Validating the speed data...")
    retrieve_default_speed_limits(engine)


def retrieve_default_speed_limits(engine: Engine) -> tuple[int | None, int | None]:
    """Retrieve the state and city default speed limits."""
    query = f"SELECT state_speed, city_speed FROM {RESIDENTIAL_SPEED_LIMIT_TABLE};"
    with engine.connect() as conn:
        result = conn.execute(text(query))
        row = result.first()
        if row:
            state_speed = int(row.state_speed) if row.state_speed else None
            city_speed = int(row.city_speed) if row.city_speed else None
            logger.debug(f"{state_speed=} | {city_speed=}")
            return state_speed, city_speed
        raise ValueError(f"no value found in the {RESIDENTIAL_SPEED_LIMIT_TABLE} table")


def rename_neighborhood_tables(engine: Engine) -> None:
    """Rename neighborhood tables."""
    query = (
        "ALTER TABLE received.neighborhood_ways_vertices_pgr "
        "RENAME TO neighborhood_ways_intersections;"
    )
    query += (
        "ALTER TABLE received.neighborhood_ways_intersections "
        "RENAME CONSTRAINT neighborhood_ways_vertices_pgr_osm_id_key "
        "TO neighborhood_vertex_id;"
    )
    query += (
        "ALTER TABLE scratch.neighborhood_cycwys_ways_vertices_pgr "
        "RENAME CONSTRAINT neighborhood_cycwys_ways_vertices_pgr_osm_id_key "
        "TO neighborhood_vertex_id;"
    )
    dbcore.execute_query(engine, query)


def move_tables(engine: Engine) -> None:
    """Move some tables to the "received" schema."""
    query = "ALTER TABLE generated.neighborhood_osm_full_line SET SCHEMA received;"
    query += "ALTER TABLE generated.neighborhood_osm_full_point SET SCHEMA received;"
    query += "ALTER TABLE generated.neighborhood_osm_full_polygon SET SCHEMA received;"
    query += "ALTER TABLE generated.neighborhood_osm_full_roads SET SCHEMA received;"
    dbcore.execute_query(engine, query)


def import_osm_data(
    engine: Engine,
    osm_file: pathlib.Path,
    output_srid: int,
    state_fips: str,
    city_fips: str,
    state_speed_limits_csv: pathlib.Path,
    city_speed_limits_csv: pathlib.Path,
    city_speed_limit_override: typing.Optional[str] = None,
) -> None:
    """
    Import data related to OSM.

    Remark: can only be run afer `import_neighborhood()`. It requires some table to
    exist to compute the boundary box.
    """
    database_url = engine.engine.url.set(drivername="postgresql").render_as_string(
        hide_password=False
    )

    # Define the BBOX and clip the data.
    # Note(rgreinho): Normally these 2 steps are useless now since we clip the
    # data during the "prepare" phase. But we still need to validate this hypothesis.
    logger.debug("Clipping the OSM data...")
    bbox = retrieve_boundary_box(engine)
    logger.debug(f"{bbox=}")
    clipped_osm_file = runner.run_osm_convert(osm_file, bbox)

    # Ensure the file does not have backslashes.
    # Note(rgreinho): do we still need this step too?

    # Import the osm with highways.
    dir_ = pathlib.Path(script_dir._paths[0])  # type: ignore
    logger.info("Importing OSM data with highways...")
    runner.run_osm2pgrouting(
        database_url,
        "received",
        "neighborhood_",
        dir_ / "mapconfig_highway.xml",
        clipped_osm_file,
    )

    # Import the osm with cycleways that the above misses (bug in osm2pgrouting).
    # Note(rgreinho): is this still true?
    logger.info("Importing OSM data with cycleways...")
    runner.run_osm2pgrouting(
        database_url,
        "scratch",
        "neighborhood_cycwys_",
        dir_ / "mapconfig_cycleway.xml",
        clipped_osm_file,
    )

    # Rename a few tables.
    logger.info("Renaming tables...")
    rename_neighborhood_tables(engine)

    # Import full osm to fill out additional data needs not met by osm2pgrouting.
    logger.info("Importing all OSM data...")
    runner.run_osm2pgsql(
        database_url, output_srid, dir_ / "pfb.style", clipped_osm_file
    )

    # Manage speed limits.
    logger.info("Importing speed limits...")
    manage_speed_limits(
        engine,
        state_fips,
        city_fips,
        state_speed_limits_csv,
        city_speed_limits_csv,
        city_speed_limit_override,
    )

    # Move the full osm tables to the received schema.
    logger.debug("Moving tables to received schema...")
    move_tables(engine)


def import_all(
    engine: Engine,
    country: str,
    output_srid: int,
    buffer: int,
    boundary_file: pathlib.Path,
    population_file: pathlib.Path,
    water_blocks_file: pathlib.Path,
    input_dir: pathlib.Path,
    osm_file: pathlib.Path,
    state_speed_limits_csv: pathlib.Path,
    city_speed_limits_csv: pathlib.Path,
    city_fips: str,
    state: typing.Optional[str] = None,
    lodes_year: typing.Optional[int] = None,
    city_speed_limit_override: typing.Optional[str] = None,
) -> None:
    """Import all the data."""
    import_neighborhood(
        engine,
        country,
        boundary_file,
        population_file,
        water_blocks_file,
        output_srid,
        buffer,
    )
    state_abbrev, state_fips, run_import_jobs = analysis.derive_state_info(state)
    logger.debug(f"{run_import_jobs=}")
    if run_import_jobs:
        if not lodes_year:
            raise ValueError("'lodes_year' is required when importing job data")
        import_jobs(engine, state_abbrev, lodes_year, input_dir)
    import_osm_data(
        engine,
        osm_file,
        output_srid,
        state_fips,
        city_fips,
        state_speed_limits_csv,
        city_speed_limits_csv,
        city_speed_limit_override,
    )


def neighborhood_wrapper(
    database_url: str,
    input_dir: pathlib.Path,
    country: str,
    city: str,
    region: str,
    buffer: int,
) -> None:
    """
    Wrap the `import_neighborhood` .

    Wrap the `import_neighborhood` function to allow calling it with only parameters
    that cannot be computed.
    """
    # Handles us/usa as the same country.
    if country.upper() == "US":
        country = "usa"

    # Ensure US/USA cities have the right parameters.
    if country.upper() == constant.COUNTRY_USA and not region:
        raise ValueError("`state` is required for US cities")

    # Prepare the database connection.
    engine = dbcore.create_psycopg_engine(database_url)

    # Prepare the files to import.
    _, slug = analysis.osmnx_query(country, city, region)
    boundary_file = input_dir / f"{slug}.shp"
    population_file = input_dir / "population.shp"
    water_blocks_file = input_dir / "censuswaterblocks.csv"

    # compute the output SRID from the boundary file.
    output_srid = utils.get_srid(boundary_file.resolve(strict=True))
    logger.debug(f"{output_srid=}")

    # Import the neighborhood data.
    import_neighborhood(
        engine,
        country=country,
        boundary_file=boundary_file.resolve(),
        population_file=population_file.resolve(strict=True),
        water_blocks_file=water_blocks_file.resolve(),
        output_srid=output_srid,
        buffer=buffer,
    )


def jobs_wrapper(
    database_url: str, input_dir: pathlib.Path, state_abbreviation: str, lodes_year: int
) -> None:
    """
    Wrap the `import_jobs` function.

    Wrap the `import_jobs` function to allow calling it with only parameters that cannot
    be computed.
    """
    # validate the US state.
    state_abbreviation = state_abbreviation.lower()
    if len(state_abbreviation) != 2:
        raise ValueError("a state abbreviation must be 2 letter long")

    # Prepare the database connection.
    engine = dbcore.create_psycopg_engine(database_url)

    # Import the jobs.
    import_jobs(engine, state_abbreviation, lodes_year, input_dir)


def osm_wrapper(
    database_url: str,
    input_dir: pathlib.Path,
    country: str,
    city: str,
    region: str,
    fips_code: str,
) -> None:
    """
    Wrap the `import_osm_data` function.

    Wrap the `import_osm_data` function to allow calling it with only parameters that
    cannot be computed.
    """
    # Prepare the database connection.
    engine = dbcore.create_psycopg_engine(database_url)

    # Handles us/usa as the same country.
    if country.upper() == "US":
        country = "usa"

    # Prepare the files to import.
    _, slug = analysis.osmnx_query(country, city, region)
    boundary_file = input_dir / f"{slug}.shp"
    osm_file = input_dir / f"{slug}.osm"
    state_speed_limits_csv = input_dir / "state_fips_speed.csv"
    city_speed_limits_csv = input_dir / "city_fips_speed.csv"

    # Compute the output SRID from the boundary file.
    output_srid = utils.get_srid(boundary_file.resolve(strict=True))
    logger.debug(f"{output_srid=}")

    # Derive state FIPS code from state name.
    _, state_fips, _ = analysis.derive_state_info(region)

    # Import the OSM data.
    import_osm_data(
        engine,
        osm_file,
        output_srid,
        state_fips,
        fips_code,
        state_speed_limits_csv,
        city_speed_limits_csv,
    )


def all_wrapper(
    database_url: str,
    input_dir: pathlib.Path,
    country: str,
    city: str,
    region: str,
    fips_code: str = common.DEFAULT_CITY_FIPS_CODE,
    lodes_year: int = common.DEFAULT_LODES_YEAR,
    buffer: int = common.DEFAULT_BUFFER,
) -> None:
    """
    Wrap the all the `import_*` functions.

    Wrap the all the `import_*` functions to allow calling them with only parameters
    that cannot be computed.
    """
    # Import neighborhood data.
    neighborhood_wrapper(database_url, input_dir, country, city, region, buffer)

    # Import job data.
    state_abbreviation, _, import_jobs = analysis.derive_state_info(region)
    if import_jobs:
        jobs_wrapper(database_url, input_dir, state_abbreviation, lodes_year)

    # Import OSM data.
    osm_wrapper(database_url, input_dir, country, city, region, fips_code)
