"""Define helper function to run external commands."""

import json
import multiprocessing
import pathlib
import subprocess
import typing
import urllib.parse

from loguru import logger

NON_US_STATE_FIPS = "0"
NON_US_STATE_ABBREV = "ZZ"


def run(cmd: typing.Sequence[str]) -> None:
    """Run a command and log the stdout/stderr at the trace level."""
    logger.debug(f"cmd={' '.join(cmd)}")
    p = subprocess.run(
        cmd,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    for line in p.stdout.splitlines():
        logger.trace(line.decode("utf-8").strip())


def run_osmium_extract(
    polygon_file_path: pathlib.Path,
    region_file_path: pathlib.Path,
    reduced_file_path: pathlib.Path,
) -> None:
    """Reduce the OSM file to the boundaries with OSMium."""
    osmium_cmd = [
        "osmium",
        "extract",
        "-p",
        str(polygon_file_path.resolve(strict=True)),
        str(region_file_path.resolve(strict=True)),
        "-o",
        str(reduced_file_path.resolve()),
    ]
    run(osmium_cmd)


def run_osm2pgrouting(
    database_url: str,
    schema: str,
    prefix: str,
    configuration_file: pathlib.Path,
    osm_file: pathlib.Path,
) -> None:
    """Import OSM data into pgRouting."""
    # Parse the database connection string.
    urlparts = urllib.parse.urlparse(database_url)

    # Prepare the command.
    osm2pgrouting_cmd = [
        "osm2pgrouting",
        "--username",
        str(urlparts.username),
        "--password",
        str(urlparts.password),
        "--host",
        str(urlparts.hostname),
        "--port",
        str(urlparts.port),
        "--dbname",
        str(urlparts.path[1:]),
        "--file",
        str(osm_file.resolve(strict=True)),
        "--schema",
        schema,
        "--prefix",
        prefix,
        "--conf",
        str(configuration_file.resolve(strict=True)),
        "--clean",
    ]
    run(osm2pgrouting_cmd)


def run_osm2pgsql(
    database_url: str,
    output_srid: int,
    style_file: pathlib.Path,
    osm_file: pathlib.Path,
    number_processes: int | None = 0,
    prefix: str | None = "neighborhood_osm_full",
) -> None:
    """Import OSM data into PostGIS."""
    # Asserts are here to make MyPy happy.
    if number_processes is None:
        raise ValueError("number_processes cannot be None")
    if prefix is None:
        raise ValueError("prefix cannot be None")

    # Retrieve the number of cores.
    cores = multiprocessing.cpu_count() if number_processes == 0 else number_processes

    # Prepare the command.
    osm2pgsql_cmd = [
        "osm2pgsql",
        "--database",
        database_url,
        "--create",
        "--prefix",
        prefix,
        "--proj",
        str(output_srid),
        "--style",
        str(style_file.resolve(strict=True)),
        "--number-processes",
        str(cores),
        str(osm_file.resolve(strict=True)),
    ]

    # Get osm2pgsql version.
    cap = subprocess.run(["osm2pgsql", "--version"], capture_output=True, check=True)
    logger.debug(f"{cap=}")
    version = cap.stderr.splitlines()[0].split()[-1]
    logger.debug(f"{version=}")
    major, minor, patch = list(map(int, version.split(b".")))
    logger.debug(f"{major=}, {minor=}, {patch=}")

    # Befware of the breaking change in 1.9.0 with the --schema flag.
    # (https://github.com/openstreetmap/osm2pgsql/releases/tag/1.9.0)
    # and manually set it if needed.
    major_version = 1
    minor_version = 9
    if major == major_version and minor >= minor_version:
        osm2pgsql_cmd.insert(1, "generated")
        osm2pgsql_cmd.insert(1, "--schema")

    # Run it.
    run(osm2pgsql_cmd)


def run_psql_command_string(database_url: str, command: str) -> None:
    """Execute a one command string, command, and then exit."""
    psql_cmd = ["psql", "-c", command, database_url]
    run(psql_cmd)


def run_osm_convert(
    osm_file: pathlib.Path,
    bbox: tuple[float, float, float, float],
) -> pathlib.Path:
    """Convert OSM data."""
    output = osm_file.with_suffix(".clipped.osm")
    bbox_str = ",".join([str(i) for i in bbox])
    osmconvert_cmd = [
        "osmconvert",
        str(osm_file.resolve(strict=True)),
        "--drop-broken-refs",
        f"-b={bbox_str}",
        f"-o={output.resolve()}",
    ]
    run(osmconvert_cmd)
    return output


def run_docker_info() -> typing.Any:
    """Return a dict containing Docker system information."""
    docker_info_cmd = ["docker", "info", "--format", "json"]
    logger.debug(f"cmd={' '.join(docker_info_cmd)}")
    docker_info = subprocess.run(docker_info_cmd, check=True, capture_output=True)
    return json.loads(docker_info.stdout)


def run_pgsql2shp(database_url: str, filename: pathlib.Path, table: str) -> None:
    """Dump a PostGIS table into a shapefile."""
    # Parse the database connection string.
    urlparts = urllib.parse.urlparse(database_url)

    pgsql2shp_cmd = [
        "pgsql2shp",
        "-u",
        str(urlparts.username),
        "-P",
        str(urlparts.password),
        "-h",
        str(urlparts.hostname),
        "-p",
        str(urlparts.port),
        "-f",
        str(filename),
        str(urlparts.path[1:]),
        table,
    ]
    run(pgsql2shp_cmd)


def run_ogr2ogr_geojson_export(
    database_url: str,
    filename: pathlib.Path,
    table: str,
) -> None:
    """Dump a table into a GeoJSON file."""
    urlparts = urllib.parse.urlparse(database_url)
    ogr2ogr_cmd = [
        "ogr2ogr",
        "-skipfailures",
        "-t_srs",
        "EPSG:4326",
        "-f",
        "GeoJSON",
        str(filename.resolve()),
        (
            f"PG:host={urlparts.hostname} user={urlparts.username} "
            f"password={urlparts.password} dbname={urlparts.path[1:]}"
        ),
        "-sql",
        f"select * from {table}",
    ]
    run(ogr2ogr_cmd)
