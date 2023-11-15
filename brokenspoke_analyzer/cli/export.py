"""Define the export sub-command."""
import pathlib

import rich
import typer
from loguru import logger
from typing_extensions import Annotated

from brokenspoke_analyzer.cli import common
from brokenspoke_analyzer.core import exporter

Force = Annotated[
    bool, typer.Option(help="Do not fail if the destination folder already exists")
]


app = typer.Typer()
console = rich.get_console()


@app.command()
def s3(
    database_url: common.DatabaseURL,
    bucket_name: str,
    country: common.Country,
    city: common.City,
    region: common.Region = None,
) -> pathlib.Path:
    """Export results to S3."""
    with console.status("[bold green]Uploading results to AWS S3..."):
        folder = exporter.create_calver_s3_directories(
            bucket_name, country, city, region
        )
        exporter.s3(database_url, bucket_name, folder)
        return folder


@app.command()
def local_custom(
    database_url: common.DatabaseURL,
    export_dir: common.ExportDirArg,
) -> None:
    """Export results into a custom directory."""
    _local(database_url=database_url, export_dir=export_dir)


@app.command()
def local(
    database_url: common.DatabaseURL,
    country: common.Country,
    city: common.City,
    region: common.Region = None,
    export_dir: common.ExportDirArg = common.DEFAULT_EXPORT_DIR,
) -> pathlib.Path:
    """Export results into a directory following the PFB calver convention."""
    dir_ = exporter.create_calver_directories(
        country, city, region, base_dir=export_dir
    )
    logger.debug(f"{dir_=}")
    _local(database_url=database_url, export_dir=dir_)
    return dir_


def _local(database_url: str, export_dir: pathlib.Path) -> None:
    console.log(f"[bold green]Saving results to {export_dir}...")
    # Prepare the output directory.
    export_dir.mkdir(parents=True, exist_ok=True)

    # Export the catalogued tables to their associated format.
    exporter.auto_export(
        export_dir.resolve(strict=True), exporter.TABLE_CATALOG, database_url
    )
