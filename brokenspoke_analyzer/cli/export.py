"""Define the export sub-command."""

import asyncio
import pathlib

import rich
import typer
from click.core import ParameterSource
from loguru import logger
from obstore import store
from typing_extensions import Annotated

from brokenspoke_analyzer.cli import common
from brokenspoke_analyzer.core import exporter

# import typing


app = typer.Typer()
console = rich.get_console()


def allow_only_env_var(
    ctx: typer.Context, param: typer.CallbackParam, value: str
) -> str:
    """Allow only environment variables for a parameter."""
    if param.name is None:
        raise ValueError(f"{param.name} must be set.")
    if ctx.get_parameter_source(param.name) != ParameterSource.ENVIRONMENT:
        raise typer.BadParameter("only allowed as environment variable")
    return value


CloudflareAccountID = Annotated[
    str,
    typer.Option(
        help="Cloudflare Account ID",
        envvar="CLOUDFLARE_ACCOUNT_ID",
        callback=allow_only_env_var,
    ),
]
R2AccessKeyID = Annotated[
    str,
    typer.Option(
        help="R2 Access Key ID",
        envvar="R2_ACCESS_KEY_ID",
        callback=allow_only_env_var,
    ),
]
R2SecretAccessKey = Annotated[
    str,
    typer.Option(
        help="R2 Secret Access Key",
        envvar="R2_SECRET_ACCESS_KEY",
        callback=allow_only_env_var,
    ),
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
    with_bundle: common.WithBundle = False,
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
    with_bundle: common.WithBundle = False,
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
    with_bundle: common.WithBundle = False,
) -> pathlib.Path:
    """Export results to a S3 bucket following the PFB calver convention."""
    with console.status("[green]Uploading results to AWS S3..."):
        return asyncio.run(
            s3_(database_url, bucket_name, country, city, region, with_bundle)
        )


@app.command()
def s3_custom(
    database_url: common.DatabaseURL,
    bucket_name: str,
    s3_dir: pathlib.Path = pathlib.Path(),
    with_bundle: common.WithBundle = False,
) -> pathlib.Path:
    """Export results to a custom S3 bucket."""
    with console.status("[green]Uploading results to AWS S3..."):
        return asyncio.run(s3_custom_(database_url, bucket_name, s3_dir, with_bundle))


@app.command()
def r2(
    database_url: common.DatabaseURL,
    account_id: CloudflareAccountID,
    access_key_id: R2AccessKeyID,
    secret_access_key: R2SecretAccessKey,
    bucket_name: str,
    country: common.Country,
    city: common.City,
    region: common.Region = None,
    with_bundle: bool = False,
) -> None:
    """
    Export results to a R2 bucket following the PFB calver convention.

    Authentication is done via environment variables:
    - CLOUDFLARE_ACCOUNT_ID
    - R2_ACCESS_KEY_ID
    - R2_SECRET_ACCESS_KEY
    """
    with console.status("[green]Uploading results to Cloudflare R2..."):
        asyncio.run(r2_(database_url, bucket_name, country, city, region, with_bundle))


@app.command()
def r2_custom(
    database_url: common.DatabaseURL,
    account_id: CloudflareAccountID,
    access_key_id: R2AccessKeyID,
    secret_access_key: R2SecretAccessKey,
    bucket_name: str,
    s3_dir: pathlib.Path = pathlib.Path(),
    with_bundle: bool = False,
) -> None:
    """
    Export results to a custom R2 bucket.

    Authentication is done via environment variables:
    - CLOUDFLARE_ACCOUNT_ID
    - R2_ACCESS_KEY_ID
    - R2_SECRET_ACCESS_KEY
    """
    with console.status("[green]Uploading results to Cloudflare R2..."):
        asyncio.run(r2_custom_(database_url, bucket_name, s3_dir, with_bundle))


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
    return await exporter.export_to_s3_with_calver(
        bucket_name, database_url, country, city, region, with_bundle
    )


async def s3_custom_(
    database_url: common.DatabaseURL,
    bucket_name: str,
    s3_dir: pathlib.Path = pathlib.Path(),
    with_bundle: bool = False,
) -> pathlib.Path:
    """Export results to a custom directory in a S3 bucket."""
    return await exporter.export_to_s3_with_custom_dir(
        bucket_name, database_url, s3_dir, with_bundle
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
    return await exporter.export_to_r2_with_calver(
        bucket_name, database_url, country, city, region, with_bundle
    )


async def r2_custom_(
    database_url: common.DatabaseURL,
    bucket_name: str,
    r2_dir: pathlib.Path = pathlib.Path(),
    with_bundle: bool = False,
) -> pathlib.Path:
    """Export results to a custom R2 bucket."""
    return await exporter.export_to_r2_with_custom_dir(
        bucket_name, database_url, r2_dir, with_bundle
    )
