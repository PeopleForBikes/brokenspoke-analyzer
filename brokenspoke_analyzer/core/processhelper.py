"""Define helper function to run external commands."""
import multiprocessing
import pathlib
import subprocess
import sys

from loguru import logger
from rich.console import Console


def run(cmd):
    """Run an external command."""
    logger.debug(f"{cmd=}")
    try:
        subprocess.run(cmd, shell=True, check=True, capture_output=True, cwd=None)
    except subprocess.CalledProcessError as cpe:
        print(
            f'"{cpe.cmd}" failed to execute with error code {cpe.returncode} for the following reason:\n'
            f"{cpe.stderr.decode('utf-8')}."
        )
        sys.exit(1)


def run_with_status(cmd, status_msg="Running...", completion_msg="Complete."):
    """Run an external command with a spinner and its status."""
    console = Console()
    with console.status(status_msg):
        run(cmd)
        console.log(completion_msg)


def run_analysis(
    state_abbrev,
    state_fips,
    city_shp,
    pfb_osm_file,
    output_dir,
):
    # pylint: disable=too-many-arguments,duplicate-code
    """Run a BNA analysis."""
    #  / slugify(country) / slugify(state) / slugify(city)
    docker_cmd = " ".join(
        [
            "docker",
            "run",
            "--rm",
            f'-e PFB_SHPFILE="/{city_shp}"',
            f'-e PFB_OSM_FILE="/{output_dir / pfb_osm_file}"',
            f"-e PFB_STATE={state_abbrev.lower()}",
            f"-e PFB_STATE_FIPS={state_fips}",
            f"-e NB_OUTPUT_DIR=/{output_dir}",
            f'-v "{pathlib.Path.cwd()}/{output_dir}/":/{output_dir}/',
            "azavea/analyzer:13-3.1",
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
