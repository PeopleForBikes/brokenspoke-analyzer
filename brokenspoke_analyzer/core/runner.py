"""Define helper function to run external commands."""
import multiprocessing
import pathlib
import subprocess
import sys
import typing

from loguru import logger
from rich.console import Console
from slugify import slugify

NON_US_STATE_FIPS = "0"
NON_US_STATE_ABBREV = "ZZ"


def run(cmd: str) -> None:
    """Run an external command."""
    logger.debug(f"{cmd=}")
    try:
        subprocess.run(cmd, shell=True, check=True, capture_output=True, cwd=None)
    except subprocess.CalledProcessError as cpe:
        print(
            f'"{cpe.cmd}" failed to execute with error code {cpe.returncode} '
            "for the following reason:\n"
            f"{cpe.stderr.decode('utf-8')}."
        )
        sys.exit(1)


# TODO(rgreinho): this belongs to the CLI package.
def run_with_status(
    cmd: str,
    status_msg: typing.Optional[str] = "Running...",
    completion_msg: typing.Optional[str] = "Complete.",
) -> None:
    """Run an external command with a spinner and its status."""
    console = Console()
    with console.status(status_msg):  # type: ignore
        run(cmd)
        console.log(completion_msg)


# pylint: disable=too-many-arguments,duplicate-code
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
    dest = pathlib.Path("/") / output_dir.name
    if state_fips == NON_US_STATE_FIPS:
        pfb_country = "nonus"
        pfb_state = ""
        run_import_jobs = 0
    else:
        pfb_country = "USA"
        pfb_state = state_abbrev.lower()
        run_import_jobs = 1
    docker_cmd_args = ["docker", "run", "--rm"]
    if container_name:
        docker_cmd_args.extend(["--name", container_name])
    if city_fips:
        docker_cmd_args.extend([f"-e PFB_CITY_FIPS={city_fips}"])
    docker_cmd_args.extend(
        [
            f'-e PFB_SHPFILE="{dest / city_shp.name}"',
            f'-e PFB_OSM_FILE="{dest / pfb_osm_file.name}"',
            f"-e PFB_COUNTRY={pfb_country}",
            f"-e PFB_STATE={sanitize_values(pfb_state)}",
            f"-e PFB_STATE_FIPS={state_fips}",
            f'-e NB_OUTPUT_DIR="{dest}"',
            f"-e RUN_IMPORT_JOBS={run_import_jobs}",
            "-e PFB_DEBUG=1",
            f'-v "{output_dir}":"{dest}"',
            f'-v "{output_dir}/population.zip":/data/population.zip',
            docker_image,
        ]
    )
    docker_cmd = " ".join(docker_cmd_args)
    # logger.debug(f"{docker_cmd=}")
    run(docker_cmd)


def run_osmium(
    polygon_file_path: pathlib.Path,
    region_file_path: pathlib.Path,
    reduced_file_path: pathlib.Path,
) -> None:
    """Reduce the OSM file to the boundaries."""
    osmium_cmd = " ".join(
        [
            "osmium",
            "extract",
            "-p",
            f'"{polygon_file_path}"',
            f'"{region_file_path}"',
            "-o",
            f'"{reduced_file_path}"',
        ]
    )
    run(osmium_cmd)


def run_osmosis(
    polygon_file_name: pathlib.Path,
    region_file_name: pathlib.Path,
    reduced_file_name: pathlib.Path,
) -> None:
    """Reduce the OSM file to the boundaries."""
    osmosis_cmd = " ".join(
        [
            "osmosis",
            "--read-pbf-fast",
            f'file="{region_file_name}"',
            f"workers={multiprocessing.cpu_count()}",
            "--bounding-polygon",
            f'file="{polygon_file_name}"',
            "--write-xml",
            f'file="{reduced_file_name}"',
        ]
    )
    run(osmosis_cmd)


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
