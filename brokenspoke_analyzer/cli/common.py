import pathlib
import typing

import typer
from typing_extensions import Annotated

# Default constant.
DEFAULT_BLOCK_POPULATION = 100
DEFAULT_BLOCKSIZE = 500
DEFAULT_BUFFER = 2680
DEFAULT_CENSUS_YEAR = 2019
DEFAULT_CITY_FIPS_CODE = "0"  # "0" means an non-US city.
DEFAULT_CITY_SPEED_LIMIT = 30
DEFAULT_CONTAINER_NAME = "brokenspoke-analyzer"
DEFAULT_RETRIES = 2
DEFAULT_MAX_TRIP_DISTANCE = 2680

# Default Typer Arguments/Options.
OutputDir = typer.Option(
    default="./data",
    exists=False,
    file_okay=False,
    dir_okay=True,
    writable=True,
    readable=True,
    resolve_path=True,
)
DockerImage = typer.Option(
    "azavea/pfb-network-connectivity:0.18.0", help="override the BNA Docker image"
)
ContainerName = typer.Option(
    DEFAULT_CONTAINER_NAME, help="give a specific name to the container running the BNA"
)
FIPSCode = Annotated[typing.Optional[str], typer.Argument(help="US city FIPS code")]
SpeedLimit = typer.Option(
    DEFAULT_CITY_SPEED_LIMIT, help="override the default speed limit (in mph)"
)
BlockSize = typer.Option(
    DEFAULT_BLOCKSIZE, help="size of a synthetic block for non-US cities (in meters)"
)
BlockPopulation = typer.Option(
    DEFAULT_BLOCK_POPULATION, help="population of a synthetic block for non-US cities"
)
Retries = typer.Option(
    DEFAULT_RETRIES, help="number of times to retry downloading files"
)
DatabaseURL = Annotated[str, typer.Option(help="database URL", envvar="DATABASE_URL")]
InputDir = Annotated[
    pathlib.Path,
    typer.Option(
        file_okay=False,
        dir_okay=True,
        resolve_path=True,
        help="directory where the files to import are located",
    ),
]
Country = Annotated[str, typer.Argument()]
City = Annotated[str, typer.Argument()]
State = Annotated[typing.Optional[str], typer.Argument(help="US state")]
Buffer = Annotated[typing.Optional[int], typer.Option(help="define the buffer area")]
CensusYear = Annotated[typing.Optional[int], typer.Argument()]
ExportDir = Annotated[
    pathlib.Path,
    typer.Argument(
        file_okay=False,
        dir_okay=True,
        writable=True,
        readable=True,
        help="local directory where to export the results",
    ),
]
