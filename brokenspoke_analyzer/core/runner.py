"""Define helper function to run external commands."""

import pathlib
import subprocess
import typing

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
