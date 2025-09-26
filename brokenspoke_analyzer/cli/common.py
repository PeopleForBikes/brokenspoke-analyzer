"""Defines the values shared amongst the CLI modules."""

import pathlib
import typing

import typer
from typing_extensions import Annotated

from brokenspoke_analyzer.core import constant

# Default constants.
DEFAULT_BLOCK_POPULATION = 100
DEFAULT_BLOCK_SIZE = 500
DEFAULT_BUFFER = 2680
DEFAULT_LODES_YEAR = 2022
DEFAULT_CITY_FIPS_CODE = "0"  # "0" means an non-US city.
DEFAULT_CITY_SPEED_LIMIT = 30
DEFAULT_CONTAINER_NAME = "brokenspoke-analyzer"
DEFAULT_DOCKER_IMAGE = "azavea/pfb-network-connectivity:0.19.0"
DEFAULT_DATA_DIR = pathlib.Path("./data").resolve()
DEFAULT_EXPORT_DIR = pathlib.Path("./results").resolve()
DEFAULT_RETRIES = 2
DEFAULT_MAX_TRIP_DISTANCE = 2680
DEFAULT_COMPUTE_PARTS = constant.COMPUTE_PARTS_ALL

# Default Typer Arguments/Options.
BlockPopulation = Annotated[
    typing.Optional[int],
    typer.Option(help="population of a synthetic block for non-US cities"),
]
BlockSize = Annotated[
    typing.Optional[int],
    typer.Option(help="size of a synthetic block for non-US cities (in meters)"),
]
Buffer = Annotated[typing.Optional[int], typer.Option(help="define the buffer area")]
CacheDir = Annotated[
    typing.Optional[pathlib.Path],
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
    typing.Optional[typing.List[constant.ComputePart]],
    typer.Option(help="parts of the analysis to compute"),
]
ContainerName = Annotated[
    typing.Optional[str],
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
    typing.Optional[str], typer.Option(help="override the BNA Docker image")
]
export_dir_kwargs = dict(
    file_okay=False,
    dir_okay=True,
    writable=True,
    readable=True,
    help="directory where to export the results",
)
ExportDirArg = Annotated[pathlib.Path, typer.Argument(**export_dir_kwargs)]
ExportDirOpt = Annotated[pathlib.Path, typer.Option(**export_dir_kwargs)]
FIPSCode = Annotated[typing.Optional[str], typer.Argument(help="US city FIPS code")]
LODESYear = Annotated[
    typing.Optional[int], typer.Option(help="year to use to retrieve US job data")
]
MaxTripDistance = Annotated[typing.Optional[int], typer.Option()]
Mirror = Annotated[
    typing.Optional[str],
    typer.Option(help="use a mirror to fetch the US census files"),
]
NoCache = Annotated[
    typing.Optional[bool], typer.Option("--no-cache", help="disable the cache folder")
]
Region = Annotated[
    typing.Optional[str],
    typer.Argument(help="world region (e.g., state, province, community, etc...)"),
]
Retries = Annotated[
    typing.Optional[int],
    typer.Option(help="number of times to retry downloading files"),
]
SpeedLimit = Annotated[
    typing.Optional[int], typer.Option(help="override the default speed limit (in mph)")
]
State = Annotated[typing.Optional[str], typer.Argument(help="US state")]
