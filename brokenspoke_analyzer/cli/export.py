"""Define the export sub-command."""

import asyncio
import pathlib
import typing

import rich
import typer
from loguru import logger
from obstore import store
from typing_extensions import Annotated

from brokenspoke_analyzer.cli import common
from brokenspoke_analyzer.core import exporter

app = typer.Typer()
console = rich.get_console()

CloudflareAccountID = Annotated[
    str, typer.Option(help="Cloudflare Account ID", envvar="CLOUDFLARE_ACCOUNT_ID")
]
WithBundle = Annotated[
    bool, typer.Argument(help="bundle all the files in a zip archive")
]


@app.command()
def local(
    database_url: common.DatabaseURL,
    country: common.Country,
    city: common.City,
    region: common.Region = None,
    export_dir: common.ExportDirArg = common.DEFAULT_EXPORT_DIR,
    with_bundle: WithBundle = False,
) -> pathlib.Path:
    """Export results to a directory following the PFB calver convention."""
    dir_ = exporter.create_calver_directories(
        country, city, region, base_dir=export_dir
    )
    logger.debug(f"{dir_=}")
    _local(database_url=database_url, export_dir=dir_, with_bundle=with_bundle)
    return dir_


@app.command()
def local_custom(
    database_url: common.DatabaseURL,
    export_dir: common.ExportDirArg,
    with_bundle: bool = False,
) -> None:
    """Export results to a custom directory."""
    _local(database_url=database_url, export_dir=export_dir, with_bundle=with_bundle)


@app.command()
def s3(
    database_url: common.DatabaseURL,
    bucket_name: str,
    country: common.Country,
    city: common.City,
    region: common.Region = None,
    with_bundle: bool = False,
) -> None:
    """Export results to a S3 bucket following the PFB calver convention."""
    with console.status("[green]Uploading results to AWS S3..."):
        asyncio.run(s3_(database_url, bucket_name, country, city, region, with_bundle))


@app.command()
def s3_custom(
    database_url: common.DatabaseURL,
    bucket_name: str,
    s3_dir: pathlib.Path = pathlib.Path(),
    with_bundle: bool = False,
) -> None:
    """Export results to a custom directory in a S3 bucket."""
    with console.status("[green]Uploading results to AWS S3..."):
        asyncio.run(s3_custom_(database_url, bucket_name, s3_dir, with_bundle))


@app.command()
def r2(
    database_url: common.DatabaseURL,
    account_id: str,
    bucket_name: str,
    country: common.Country,
    city: common.City,
    region: common.Region = None,
    with_bundle: bool = False,
) -> None:
    """Export results to a R2 bucket following the PFB calver convention."""
    with console.status("[green]Uploading results to Cloudflare R2..."):
        asyncio.run(s3_(database_url, bucket_name, country, city, region, with_bundle))


@app.command()
def r2_custom(
    database_url: common.DatabaseURL,
    account_id: str,
    bucket_name: str,
    s3_dir: pathlib.Path = pathlib.Path(),
    with_bundle: bool = False,
) -> None:
    """Export results to a custom R2 bucket."""
    with console.status("[green]Uploading results to Cloudflare R2..."):
        asyncio.run(s3_custom_(database_url, bucket_name, s3_dir, with_bundle))


def _local(
    database_url: str,
    export_dir: pathlib.Path,
    with_bundle: bool = False,
) -> None:
    console.log(f"[green]Saving results to {export_dir}...")
    exporter.local_files(
        database_url=database_url, export_dir=export_dir, with_bundle=with_bundle
    )


async def s3_(
    database_url: str,
    bucket_name: str,
    country: common.Country,
    city: common.City,
    region: common.Region = None,
    with_bundle: bool = False,
) -> pathlib.Path:
    """Export results to a S3 bucket following the PFB calver convention."""
    store = exporter.create_s3_store(bucket_name)
    return await exporter.export_store_with_calver(
        store, database_url, country, city, region, with_bundle
    )


async def s3_custom_(
    database_url: common.DatabaseURL,
    bucket_name: str,
    s3_dir: pathlib.Path = pathlib.Path(),
    with_bundle: bool = False,
) -> None:
    """Export results to a custom directory in a S3 bucket."""
    store = exporter.create_s3_store(bucket_name)
    return await exporter.export_store_with_custom_dir(
        store, database_url, s3_dir, with_bundle
    )


async def r2_(
    database_url: common.DatabaseURL,
    bucket_name: str,
    country: common.Country,
    city: common.City,
    region: common.Region = None,
    with_bundle: bool = False,
) -> pathlib.Path:
    """Export results to a R2 bucket following the PFB calver convention."""
    store = exporter.create_r2_store(bucket_name)
    return await exporter.export_store_with_calver(
        store, database_url, country, city, region, with_bundle
    )


async def r2_custom_(
    database_url: common.DatabaseURL,
    bucket_name: str,
    s3_dir: pathlib.Path = pathlib.Path(),
    with_bundle: bool = False,
) -> None:
    """Export results to a custom R2 bucket."""
    store = exporter.create_r2_store(bucket_name)
    return await exporter.export_store_with_custom_dir(
        store, database_url, s3_dir, with_bundle
    )
