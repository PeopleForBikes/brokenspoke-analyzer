"""
Publish the analysis results.

The files themselves are written by `core/pipeline/export.py`; this module
places them -- the calver directory tree, the optional bundle, and the upload
to an object store.

To upload we use the `obstore` library, which provides a unified interface to
S3 and R2. However, since `obstore` does not have the concept of folders, we
cannot create directories. For this use case, we leverage the native `boto3`
library. Same goes for listing the objects, as `obstore` cannot differentiate
between files and directories.

References:
- <https://github.com/developmentseed/obstore/issues/101>
- <https://github.com/developmentseed/obstore/issues/644>
"""

from __future__ import annotations

import datetime
import enum
import os
import pathlib
import shutil
import typing
from typing import TYPE_CHECKING

import boto3
import yarl
from loguru import logger
from obstore.store import from_url

if TYPE_CHECKING:
    from obstore.store import ObjectStore


# Catalog the tables and associate them to an export format.
class Exporter(enum.StrEnum):
    """Define the available exporters."""

    none = "none"
    local = "local"
    s3 = "s3"
    s3_custom = "s3_custom"
    r2 = "r2"
    r2_custom = "r2_custom"


def create_calver_directories(
    country: str,
    city: str,
    region: str | None,
    date_override: str | None = None,
    base_dir: pathlib.Path = pathlib.Path(),
) -> pathlib.Path:
    """
    Create a directory structure following calver to export the tables.

    The calver scheme is based and inspired by the BNA mechanics standards:
    <country>/<egion>/<city>/YY.MM[.Micro]
    See https://calver.org/#scheme for more details.

    * usa/tx/austin/23.08
    * usa/tx/austin/23.12.2
    * spain/valencia/valencia/23.08

    Examples:
        >>> today = datetime.datetime.now(tz=datetime.UTC).date()
        >>> calver = f"{today.strftime('%y.%m')}"
        >>> directory = create_calver_directories("usa", "austin", "tx")
        >>> assert directory == pathlib.Path(f"usa/tx/austin/{calver}")
    """
    p = calver_base(country, city, region, date_override, base_dir)

    # List all the directories with the same calver stem.
    dirs = list(p.parent.glob(f"{p.name}*"))

    # If there is none, it means it is the first one.
    if not dirs:
        return p

    revision = calver_revision(dirs)
    return pathlib.Path(f"{p}.{revision}")


def calver_base(
    country: str,
    city: str,
    region: str | None = None,
    date_override: str | None = None,
    base_dir: pathlib.Path = pathlib.Path(),
) -> pathlib.Path:
    """
    Build the base part of the calver path.

    Examples:
        >>> today = datetime.datetime.now(tz=datetime.UTC).date()
        >>> calver = f"{today.strftime('%y.%m')}"
        >>> directory = calver_base("usa", "austin", "tx")
        >>> assert directory == pathlib.Path(f"usa/tx/austin/{calver}")
    """
    # Start with the base path.
    p = base_dir

    # Add the country.
    p /= country.lower()

    # Add the region, falling back to the country name.
    if region:
        p /= region.lower()
    else:
        p /= country.lower()

    # Add the city.
    p /= city.lower()

    # Use the date override if any.
    if date_override:
        return p / date_override

    # Otherwise use the appropriate calver.
    today = datetime.datetime.now(tz=datetime.UTC).date()
    p /= f"{today.strftime('%y.%m')}"

    return p


def calver_revision(dirs: typing.Sequence[pathlib.Path]) -> int:
    """
    Build the revision part of the calver path.

    Examples:
        >>> dirs=[pathlib.Path('usa/new mexico/santa rosa/23.08')]
        >>> calver_revision(dirs)
        1
        >>> dirs.append(pathlib.Path('usa/new mexico/santa rosa/23.08.1'))
        >>> calver_revision(dirs)
        2
        >>> dirs.append(pathlib.Path('usa/new mexico/santa rosa/23.08.15'))
        >>> calver_revision(dirs)
        16
        >>> dirs.append(pathlib.Path('usa/new mexico/santa rosa/23.08.150'))
        >>> calver_revision(dirs)
        151
    """
    # Collect the directories with the suffixes.
    suffix_count = 2
    with_micro = [
        int(d.suffixes[-1].replace(".", ""))
        for d in dirs
        if len(d.suffixes) == suffix_count
    ]

    # If there is no directory with a micro part, create the first one.
    if not with_micro:
        return 1

    # Otherwise get the highest micro and increment it.
    return max(with_micro) + 1


def bundle(src_dir: pathlib.Path) -> pathlib.Path:
    """Bundle the content of `src_dir` into a zip file and save it into `src_dir`."""
    bundle_file = pathlib.Path("bundle.zip")
    dest = src_dir / bundle_file
    shutil.make_archive(bundle_file.stem, bundle_file.suffix[1:], src_dir)
    shutil.move(bundle_file, dest)
    return dest


def get_s3_bucket(bucket_name: str) -> typing.Any:
    """
    Get the S3 bucket.

    Authentication is done via AWS environment variables:
    - AWS_ACCESS_KEY_ID
    - AWS_SECRET_ACCESS_KEY
    - AWS_REGION
    - AWS_SESSION_TOKEN (optional)
    """
    # Initialize the S3 client.
    s3 = boto3.resource(service_name="s3")
    return s3.Bucket(bucket_name)


def get_r2_bucket(bucket_name: str) -> typing.Any:
    """
    Get the R2 bucket.

    Authentication is done via R2 environment variables:
    - CLOUDFLARE_ACCOUNT_ID
    - R2_ACCESS_KEY_ID
    - R2_SECRET_ACCESS_KEY
    """
    r2_account_id = os.environ["CLOUDFLARE_ACCOUNT_ID"]
    r2_access_key_id = os.environ["R2_ACCESS_KEY_ID"]
    r2_secret_access_key = os.environ["R2_SECRET_ACCESS_KEY"]
    s3 = boto3.resource(
        service_name="s3",
        endpoint_url=f"https://{r2_account_id}.r2.cloudflarestorage.com",
        aws_access_key_id=r2_access_key_id,
        aws_secret_access_key=r2_secret_access_key,
        region_name="auto",
    )
    return s3.Bucket(bucket_name)


def calver_directory_s3(
    bucket: typing.Any,
    country: str,
    city: str,
    region: str | None = None,
) -> pathlib.Path:
    """Create the calver directory in the S3 bucket."""
    # Create the calver directory.
    s3_dir = calver_base(country, city, region)

    # Check for any existing match.
    matches = [
        pathlib.Path(obj.key)
        for obj in bucket.objects.filter(Prefix=str(s3_dir))
        if str(s3_dir) in obj.key and obj.key.endswith("/")
    ]

    # In case there is already a calver folder, we must increment the revision.
    if matches:
        rev = calver_revision(matches)
        s3_dir = pathlib.Path(f"{s3_dir}.{rev}/")

    # Return the calver folder.
    return s3_dir


def mkdir_calver_directory_s3(
    bucket: typing.Any,
    country: str,
    city: str,
    region: str | None = None,
) -> pathlib.Path:
    """Create the calver directory in the S3 bucket."""
    # Create the calver directory.
    s3_dir = calver_directory_s3(bucket, country, city, region)

    # Create the folder in the bucket.
    return mkdir_s3(bucket, s3_dir)


def mkdir_s3(bucket: typing.Any, s3_dir: pathlib.Path = pathlib.Path()) -> pathlib.Path:
    """Create a custom directory in the S3 bucket."""
    bucket.put_object(Body="", Key=str(s3_dir).rstrip("/") + "/")
    return s3_dir


# ------------------------------------------------------------------------------
# Below we are using `obstore` to implement store functions.
def create_s3_store(
    bucket_name: str,
    prefix: pathlib.Path | None = None,
) -> ObjectStore:
    """
    Create the S3 store.

    Authentication is done via AWS environment variables:
    - AWS_ACCESS_KEY_ID
    - AWS_SECRET_ACCESS_KEY
    - AWS_REGION
    - AWS_SESSION_TOKEN (optional)
    """
    url = yarl.URL(f"s3://{bucket_name}")
    if prefix:
        url /= str(prefix)
    logger.debug(f"Creating S3 store with URL: {url}")
    client_options = {"timeout": "1h"}
    return from_url(str(url), client_options=client_options)  # ty:ignore[no-matching-overload]


def create_r2_store(
    bucket_name: str,
    prefix: pathlib.Path | None = None,
) -> ObjectStore:
    """
    Create the R2 store.

    Authentication is done via environment variables:
    - CLOUDFLARE_ACCOUNT_ID
    - R2_ACCESS_KEY_ID
    - R2_SECRET_ACCESS_KEY
    """
    account_id = os.environ["CLOUDFLARE_ACCOUNT_ID"]
    access_key_id = os.environ["R2_ACCESS_KEY_ID"]
    secret_access_key = os.environ["R2_SECRET_ACCESS_KEY"]
    url = yarl.URL(f"https://{account_id}.r2.cloudflarestorage.com/{bucket_name}")
    if prefix:
        url /= str(prefix)
    logger.debug(f"Creating R2 store with URL: {url}")
    client_options = {"timeout": "1h"}
    return from_url(
        str(url),
        access_key_id=access_key_id,
        secret_access_key=secret_access_key,
        client_options=client_options,
    )  # ty:ignore[no-matching-overload]


async def upload_file(store: ObjectStore, path: pathlib.Path) -> None:
    """Upload a file to the store."""
    await store.put_async(str(path), path)
