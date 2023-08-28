import pathlib
import typing

import typer
from loguru import logger
from typing_extensions import Annotated

from brokenspoke_analyzer.cli import common
from brokenspoke_analyzer.core import exporter

Force = Annotated[
    bool, typer.Option(help="Do not fail if the destination folder already exists")
]
Region = Annotated[
    typing.Optional[str],
    typer.Argument(
        help=(
            "Represent the world region (e.g., state, province, community, etc...). "
            "Falls back to the country name if not provided."
        )
    ),
]


app = typer.Typer()


@app.command()
def s3() -> None:
    """Export results to S3."""
    raise NotImplementedError("the S3 export is not yet implemented")


@app.command()
def local(
    database_url: common.DatabaseURL,
    export_dir: common.ExportDir,
    force: Force = False,
) -> None:
    """Export results into a custom directory."""
    _local(database_url=database_url, export_dir=export_dir, force=force)


@app.command()
def local_calver(
    database_url: common.DatabaseURL,
    country: common.Country,
    city: common.City,
    region: Region = None,
    force: Force = False,
    export_dir: common.ExportDir = pathlib.Path("data/results"),
) -> None:
    """Export results into a directory following the calver convention."""
    dir_ = exporter.create_calver_directories(
        country, city, region, base_dir=export_dir
    )
    logger.debug(f"{dir_=}")
    _local(database_url=database_url, export_dir=dir_, force=force)


def _local(database_url: str, export_dir: pathlib.Path, force: bool) -> None:
    # Prepare the output directory.
    export_dir.mkdir(parents=True, exist_ok=force)

    # Export the catalogued tables to their associated format.
    exporter.auto_export(
        export_dir.resolve(strict=True), exporter.TABLE_CATALOG, database_url
    )
