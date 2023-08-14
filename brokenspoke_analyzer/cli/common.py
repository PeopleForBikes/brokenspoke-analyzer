import typer

# Default values
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
    None, help="give a specific name to the container running the BNA"
)
CityFIPS = typer.Option(None, help="city FIPS code")
SpeedLimit = typer.Option(30, help="override the default speed limit (in mph)")
BlockSize = typer.Option(
    500, help="size of a synthetic block for non-US cities (in meters)"
)
BlockPopulation = typer.Option(
    100, help="population of a synthetic block for non-US cities"
)
Retries = typer.Option(2, help="number of times to retry downloading files")
