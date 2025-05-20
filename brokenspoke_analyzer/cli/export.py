"""Define the export sub-command."""

import pathlib
import typing

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
    with_bundle: typing.Optional[bool] = False,
) -> pathlib.Path:
    """Export results to a S3 bucket following the PFB calver convention."""
    with console.status("[green]Uploading results to AWS S3..."):
        folder = exporter.create_calver_s3_directories(
            bucket_name, country, city, region
        )
        exporter.s3(database_url, bucket_name, folder, with_bundle)
        return folder


@app.command()
def s3_custom(
    database_url: common.DatabaseURL,
    bucket_name: str,
    s3_dir: typing.Optional[pathlib.Path] = pathlib.Path(),
    with_bundle: typing.Optional[bool] = False,
) -> pathlib.Path:
    """Export results to a custom S3 bucket."""
    with console.status("[green]Uploading results to AWS S3..."):
        folder = exporter.s3_directories(bucket_name, s3_dir)
        exporter.s3(database_url, bucket_name, folder, with_bundle)
        return folder


@app.command()
def local_custom(
    database_url: common.DatabaseURL,
    export_dir: common.ExportDirArg,
    with_bundle: typing.Optional[bool] = False,
) -> None:
    """Export results to a custom directory."""
    _local(database_url=database_url, export_dir=export_dir, with_bundle=with_bundle)


@app.command()
def local(
    database_url: common.DatabaseURL,
    country: common.Country,
    city: common.City,
    region: common.Region = None,
    export_dir: common.ExportDirArg = common.DEFAULT_EXPORT_DIR,
    with_bundle: typing.Optional[bool] = False,
) -> pathlib.Path:
    """Export results to a directory following the PFB calver convention."""
    dir_ = exporter.create_calver_directories(
        country, city, region, base_dir=export_dir
    )
    logger.debug(f"{dir_=}")
    _local(database_url=database_url, export_dir=dir_, with_bundle=with_bundle)
    return dir_


def _local(
    database_url: str,
    export_dir: pathlib.Path,
    with_bundle: typing.Optional[bool] = False,
) -> None:
    console.log(f"[green]Saving results to {export_dir}...")
    exporter.local_files(
        database_url=database_url, export_dir=export_dir, with_bundle=with_bundle
    )
