"""Defines the values shared amongst the CLI modules."""

import pathlib
from datetime import (
    UTC,
    datetime,
)
from importlib import metadata
from typing import (
    Annotated,
    TypedDict,
)
lazy from collections.abc import Callable

import typer

from bna.lib import (
    constant,
)

# Default constants shared with the library.
DEFAULT_BUFFER = constant.DEFAULT_BUFFER
DEFAULT_CITY_FIPS_CODE = constant.DEFAULT_CITY_FIPS_CODE
DEFAULT_COMPUTE_PARTS = constant.DEFAULT_COMPUTE_PARTS
DEFAULT_MAX_TRIP_DISTANCE = constant.DEFAULT_MAX_TRIP_DISTANCE
DEFAULT_RETRIES = constant.DEFAULT_RETRIES

# Default constants specific to the CLI.
DEFAULT_BLOCK_POPULATION = 100
DEFAULT_BLOCK_SIZE = 500
DEFAULT_CITY_SPEED_LIMIT = 30
DEFAULT_CONTAINER_NAME = "brokenspoke-analyzer"
DEFAULT_DATA_DIR = pathlib.Path("./data").resolve()
DEFAULT_DOCKER_IMAGE = "azavea/pfb-network-connectivity:0.19.0"
DEFAULT_EXPORT_DIR = pathlib.Path("./results").resolve()
DEFAULT_LODES_YEAR = 2022
DEFAULT_WORLDPOP_YEAR: int = datetime.now(tz=UTC).year

# Default Typer Arguments/Options.
BlockPopulation = Annotated[
    int,
    typer.Option(help="population of a synthetic block for non-US cities"),
]
BlockSize = Annotated[
    int,
    typer.Option(help="size of a synthetic block for non-US cities (in meters)"),
]
Buffer = Annotated[int, typer.Option(help="define the buffer area")]
CacheDir = Annotated[
    pathlib.Path | None,
    typer.Option(
        file_okay=False,
        dir_okay=True,
        exists=True,
        resolve_path=True,
        readable=True,
        writable=True,
        help="path to the cache directory",
    ),
]
City = Annotated[str, typer.Argument()]
ComputeParts = Annotated[
    list[constant.ComputePart] | None,
    typer.Option(help="parts of the analysis to compute"),
]
ContainerName = Annotated[
    str | None,
    typer.Option(help="give a specific name to the container running the BNA"),
]
Country = Annotated[str, typer.Argument()]
DatabaseURL = Annotated[str, typer.Option(help="database URL", envvar="DATABASE_URL")]
DataDir = Annotated[
    pathlib.Path,
    typer.Option(
        file_okay=False,
        dir_okay=True,
        resolve_path=True,
        help="directory where the files to import are located",
    ),
]
DockerImage = Annotated[
    str | None,
    typer.Option(help="override the BNA Docker image"),
]


class ExportDirKwargs(TypedDict):
    """Keyword arguments shared by the export directory argument and option."""

    file_okay: bool
    dir_okay: bool
    writable: bool
    readable: bool
    help: str


export_dir_kwargs: ExportDirKwargs = {
    "file_okay": False,
    "dir_okay": True,
    "writable": True,
    "readable": True,
    "help": "directory where to export the results",
}
ExportDirArg = Annotated[pathlib.Path, typer.Argument(**export_dir_kwargs)]
ExportDirOpt = Annotated[pathlib.Path, typer.Option(**export_dir_kwargs)]
FIPSCode = Annotated[str, typer.Argument(help="US city FIPS code")]
LODESYear = Annotated[
    int | None,
    typer.Option(help="year to use to retrieve US job data"),
]
MaxTripDistance = Annotated[int, typer.Option()]
Mirror = Annotated[
    str | None,
    typer.Option(help="use a mirror to fetch the US census files"),
]
NoCache = Annotated[
    bool | None,
    typer.Option("--no-cache", help="disable the cache folder"),
]
Region = Annotated[
    str | None,
    typer.Argument(help="world region (e.g., state, province, community, etc...)"),
]
Retries = Annotated[
    int, typer.Option(min=0, help="number of times to retry downloading files")
]
SpeedLimit = Annotated[
    int | None,
    typer.Option(help="override the city default speed limit (in mph)"),
]
State = Annotated[str | None, typer.Argument(help="US state")]
WithBundle = Annotated[bool, typer.Option(help="bundle all the files in a zip archive")]
WorldPopYear = Annotated[
    int,
    typer.Option(help="year to use to retrieve WorldPop data"),
]


def version_callback(distribution: str) -> Callable[..., None]:
    """Build a ``--version`` option callback for a distribution.

    The returned callback prints ``<distribution> version: <version>`` and
    exits when the flag is given. Click runs option callbacks on every
    invocation, so the version is only looked up when the flag is given:
    the rest of the command line never depends on the distribution metadata.

    Parameters
    ----------
    distribution
        Name of the installed distribution whose version to print.

    Returns
    -------
    Callable[..., None]
        A callback to pass to ``typer.Option(callback=...)``.

    Examples
    --------
    >>> callback = version_callback("bna-cli")
    >>> callback(value=False)
    """

    def _callback(*, value: bool) -> None:
        if value:
            version = metadata.version(distribution)
            typer.echo(f"{distribution} version: {version}")
            raise typer.Exit

    return _callback
