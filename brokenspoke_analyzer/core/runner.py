"""Define helper function to run external commands."""
import json
import multiprocessing
import pathlib
import subprocess
import typing
import urllib

from loguru import logger
from slugify import slugify

NON_US_STATE_FIPS = "0"
NON_US_STATE_ABBREV = "ZZ"


def run(cmd: typing.Sequence[str]) -> None:
    logger.debug(f"cmd={' '.join(cmd)}")
    subprocess.run(cmd, check=True)


def run_analysis(
    state_abbrev: str,
    state_fips: str,
    city_shp: pathlib.Path,
    pfb_osm_file: pathlib.Path,
    output_dir: pathlib.Path,
    docker_image: str,
    container_name: typing.Optional[str] = None,
    city_fips: typing.Optional[str] = None,
) -> None:
    """Run a BNA analysis."""
    dest = pathlib.Path("/data") / output_dir.name
    if state_fips == NON_US_STATE_FIPS:
        pfb_country = "nonus"
        pfb_state = ""
        run_import_jobs = 0
    else:
        pfb_country = "USA"
        pfb_state = state_abbrev.lower()
        run_import_jobs = 1
    docker_cmd = ["docker", "run", "--rm"]
    if container_name:
        docker_cmd.extend(["--name", container_name])
    if city_fips:
        docker_cmd.extend(["-e", f"PFB_CITY_FIPS={city_fips}"])
    docker_cmd.extend(
        [
            "-e",
            f'PFB_SHPFILE="{dest / city_shp.name}"',
            "-e",
            f'PFB_OSM_FILE="{dest / pfb_osm_file.name}"',
            "-e",
            f"PFB_COUNTRY={pfb_country}",
            "-e",
            f"PFB_STATE={sanitize_values(pfb_state)}",
            "-e",
            f"PFB_STATE_FIPS={state_fips}",
            "-e",
            f'NB_OUTPUT_DIR="{dest}"',
            "-e",
            f"RUN_IMPORT_JOBS={run_import_jobs}",
            "-e",
            "PFB_DEBUG=1",
            "-v",
            f'"{output_dir}":"{dest}"',
            "-v",
            f'"{output_dir}/population.zip":"/data/population.zip"',
            docker_image,
        ]
    )
    cmd = " ".join(docker_cmd)
    logger.debug(f"{cmd=}")
    subprocess.run(cmd, shell=True, check=True)


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


def sanitize_values(value: str) -> str:
    """
    Removes spaces and other invalid characters from the value.

    Examples:

    >>> sanitize_values("a directory with spaces")
    'a_directory_with_spaces'

    >>> sanitize_values("")
    ''
    """
    return slugify(value, save_order=True, separator="_")


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
    number_processes: typing.Optional[int] = 0,
    prefix: typing.Optional[str] = "neighborhood_osm_full",
) -> None:
    """Import OSM data into PostGIS."""
    # Asserts are here to make MyPy happy.
    assert number_processes is not None
    assert prefix is not None
    cores = multiprocessing.cpu_count() if number_processes == 0 else number_processes
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
    run(osm2pgsql_cmd)


def run_psql_command_string(database_url: str, command: str) -> None:
    """Execute a one command string, command, and then exit."""
    psql_cmd = ["psql", "-c", command, database_url]
    run(psql_cmd)


def run_osm_convert(
    osm_file: pathlib.Path, bbox: tuple[float, float, float, float]
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
    database_url: str, filename: pathlib.Path, table: str
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
