"""
Utility to sync up an R2 bucket with an AWS bucket.

Could have probably just used [Rclone](https://rclone.org/commands/rclone_sync/)
though...
"""

from __future__ import annotations

import asyncio
import os
from typing import TYPE_CHECKING

import obstore
from loguru import logger
from obstore.store import (
    S3Store,
    from_url,
)

from brokenspoke_analyzer.core import (
    datastore,
)

if TYPE_CHECKING:
    from obstore.store import (
        S3Store,
    )


async def aws_r2_sync():
    """Copy the files from the AWS S3 bucket to the Cloudflare R2 bucket."""
    # Get the bucket name.
    bucket = os.getenv("BNA_CACHE_AWS_S3_BUCKET")

    # Collect the AWS credentials.
    aws_access_key_id = os.getenv("BNA_AWS_ACCESS_KEY_ID")
    aws_secret_access_key = os.getenv("BNA_AWS_SECRET_ACCESS_KEY")
    aws_session_token = os.getenv("BNA_AWS_SESSION_TOKEN")
    aws_region = os.getenv("BNA_AWS_REGION")

    # Collect the R2 credentials.
    r2_account_id = os.getenv("BNA_R2_ACCOUNT_ID")
    r2_access_key_id = os.getenv("BNA_R2_ACCESS_KEY_ID")
    r2_secret_access_key = os.getenv("BNA_R2_SECRET_ACCESS_KEY")
    r2_region = os.getenv("BNA_R2_REGION")

    # Define the common data store options.
    client_options = {"connect_timeout": "1h"}

    # Create the AWS store.
    aws_store = from_url(
        f"s3://{bucket}",
        client_options=client_options,
        access_key_id=aws_access_key_id,
        secret_access_key=aws_secret_access_key,
        session_token=aws_session_token,
        region=aws_region,
    )

    # Create the R2 store.
    r2_store = S3Store(
        bucket,
        client_options=client_options,
        access_key_id=r2_access_key_id,
        secret_access_key=r2_secret_access_key,
        endpoint=f"https://{r2_account_id}.r2.cloudflarestorage.com",
        region=r2_region,
    )

    # List all the files in the AWS cache.
    list_stream = await obstore.list_with_delimiter_async(aws_store, "/")
    objects_size = len(list_stream["objects"])
    for i, object_ in enumerate(list_stream["objects"]):
        path = object_["path"]
        logger.info(
            f"Object {i}/{objects_size} - File Name: {path}, size: {object_['size']}"
        )
        if datastore.exists(r2_store, path):
            logger.info(f"Skipping {path} as it already exists at the destination.")

            # This only constructs the stream, it doesn't materialize the data in memory
            stream = await obstore.get_async(aws_store, path)
            # A streaming upload is created to copy the file to path2
            await obstore.put_async(r2_store, path, stream)


if __name__ == "__main__":
    asyncio.run(aws_r2_sync())
