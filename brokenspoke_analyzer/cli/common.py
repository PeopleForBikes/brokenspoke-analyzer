import pathlib
import typing

import typer
from typing_extensions import Annotated

# Default constants.
DEFAULT_BLOCK_POPULATION = 100
DEFAULT_BLOCK_SIZE = 500
DEFAULT_BUFFER = 2680
DEFAULT_LODES_YEAR = 2019
DEFAULT_CITY_FIPS_CODE = "0"  # "0" means an non-US city.
DEFAULT_CITY_SPEED_LIMIT = 30
DEFAULT_CONTAINER_NAME = "brokenspoke-analyzer"
DEFAULT_DOCKER_IMAGE = "azavea/pfb-network-connectivity:0.19.0"
DEFAULT_OUTPUT_DIR = pathlib.Path("./data")
DEFAULT_EXPORT_DIR = pathlib.Path("./results")
DEFAULT_RETRIES = 2
DEFAULT_MAX_TRIP_DISTANCE = 2680

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
LODESYear = Annotated[
    typing.Optional[int], typer.Option(help="year to use to retrieve US job data")
]
City = Annotated[str, typer.Argument()]
ContainerName = Annotated[
    typing.Optional[str],
    typer.Option(help="give a specific name to the container running the BNA"),
]
Country = Annotated[str, typer.Argument()]
DatabaseURL = Annotated[str, typer.Option(help="database URL", envvar="DATABASE_URL")]
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
InputDir = Annotated[
    pathlib.Path,
    typer.Option(
        file_okay=False,
        dir_okay=True,
        resolve_path=True,
        help="directory where the files to import are located",
    ),
]
MaxTripDistance = Annotated[typing.Optional[int], typer.Option()]
OutputDir = Annotated[
    typing.Optional[pathlib.Path],
    typer.Option(
        exists=False,
        file_okay=False,
        dir_okay=True,
        writable=True,
        readable=True,
        resolve_path=True,
        help="directory where to store the files required for the analysis",
    ),
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
