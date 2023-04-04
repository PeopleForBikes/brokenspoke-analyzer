"""Define helper function to run external commands."""
import multiprocessing
import pathlib
import subprocess
import sys

from loguru import logger
from rich.console import Console

NON_US_STATE_FIPS = 0
NON_US_STATE_ABBREV = "ZZ"


def run(cmd):
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


def run_with_status(cmd, status_msg="Running...", completion_msg="Complete."):
    """Run an external command with a spinner and its status."""
    console = Console()
    with console.status(status_msg):
        run(cmd)
        console.log(completion_msg)


# pylint: disable=too-many-arguments,duplicate-code
def run_analysis(
    state_abbrev,
    state_fips,
    city_shp,
    pfb_osm_file,
    output_dir,
    docker_image,
):
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
    docker_cmd = " ".join(
        [
            "docker",
            "run",
            "--rm",
            f'-e PFB_SHPFILE="{dest / city_shp.name}"',
            f'-e PFB_OSM_FILE="{dest / pfb_osm_file}"',
            f"-e PFB_COUNTRY={pfb_country}",
            f"-e PFB_STATE={pfb_state}",
            f"-e PFB_STATE_FIPS={state_fips}",
            f"-e NB_OUTPUT_DIR={dest}",
            f"-e RUN_IMPORT_JOBS={run_import_jobs}",
            "-e PFB_DEBUG=1",
            f'-v "{output_dir}":{dest}',
            docker_image,
        ]
    )
    run(docker_cmd)


def run_osmium(polygon_file_path, region_file_path, reduced_file_path):
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


def run_osmosis(polygon_file_name, region_file_name, reduced_file_name):
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
