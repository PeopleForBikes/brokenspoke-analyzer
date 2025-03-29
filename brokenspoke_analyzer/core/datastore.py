"""Define the Datastores."""

from __future__ import annotations

import enum
import pathlib
import typing
from collections import abc
from typing import TYPE_CHECKING

import aiohttp
from loguru import logger
from obstore.store import (
    HTTPStore,
    from_url,
)

from brokenspoke_analyzer.core import (
    downloader,
    utils,
)

if TYPE_CHECKING:
    from obstore.store import ObjectStore


CHUNK_SIZE = 5 * 1024 * 1024  # 5MB
PFB_PUBLIC_DOCUMENTS_URL = "https://s3.amazonaws.com/pfb-public-documents"
TIGER_URL = "https://www2.census.gov/geo/tiger"


def exists(store: ObjectStore, path: str) -> bool:
    """Check whether a file already exists in a store."""
    try:
        store.head(path)
    except FileNotFoundError:
        return False
    else:
        return True


class CacheType(enum.Enum):
    """Define the types of caching strategies available to retrieve and store artifacts."""

    NONE = 0
    USER_CACHE = 1
    AWS_S3 = 2


class BNADataStore:
    """Define the BNA data store."""

    def __init__(self, path: pathlib.Path, cache_type: CacheType):
        """
        Initialize the BNA data store.

        This will create or load the data and the cache stores.

        The data store is ALWAYS a local directory.
        The cache store location varies depending on the strategy.

        """
        # `path` MUST start with '/'.
        if not str(path).startswith("/"):
            raise ValueError(f"path must start with '/': {path}")

        # Define the common data store options.
        client_options = {"connect_timeout": "1h"}

        # Create the data store.
        self.store = from_url(  # type: ignore
            f"file://{path}", client_options=client_options, mkdir=True
        )

        # Create the cache store based on the selected strategy.
        match cache_type:
            case CacheType.NONE:
                # path MUST start with '/'.
                self.cache = from_url(  # type: ignore
                    f"file://{path}", client_options=client_options, mkdir=True
                )
            case CacheType.USER_CACHE:
                self.cache = from_url(  # type: ignore
                    f"file://{utils.get_user_cache_dir()}",
                    client_options=client_options,
                    mkdir=True,
                )
            case CacheType.AWS_S3:
                self.cache = from_url(f"s3://{path}", client_options=client_options)  # type: ignore

    def is_cached(self, path: str) -> bool:
        """Check whether a file already exists in the cache store."""
        return exists(self.cache, path)

    def _is_stored(self, path: str) -> bool:
        """Check whether a file already exists in the data store."""
        return exists(self.store, path)

    async def copy_to_store(self, path: str) -> None:
        """Copy a file from the cache to the store."""
        if not exists(self.cache, path):
            raise FileNotFoundError(f"{path} was not found in the cache")
        if exists(self.store, path):
            return
        res = await self.cache.get_async(path)
        await self.store.put_async(path, res)

    async def fetch_to_cache(self, root: str, path: str) -> None:
        """Fetch a file into the cache."""
        # Check whether the file already exists in the cache.
        if not self.is_cached(path):
            # If not, download it from the orignal source, using a HTTP store to
            # fetch the file, and store it into the cache data store.
            http_store = HTTPStore.from_url(
                root, client_options={"connect_timeout": "1h"}
            )
            http_response = await http_store.get_async(path)
            await self.cache.put_async(path, http_response)

    async def _fetch_to_store(self, root: str, path: str) -> None:
        """Fetch a file and store it."""
        # Check whether the file already exists in the store.
        if not self._is_stored(path):
            # If not, download it from the orignal source, using a HTTP store to
            # fetch the file, and store it into the cache data store.
            http_store = HTTPStore.from_url(
                root, client_options={"connect_timeout": "1h"}
            )
            http_response = await http_store.get_async(path)
            await self.store.put_async(path, http_response)

    async def fetch_to_store_with_cache(self, root: str, path: str) -> None:
        """Fetch a file to the cache and copy it to the store."""
        await self.fetch_to_cache(root, path)
        await self.copy_to_store(path)

    async def download_state_speed_limits(self) -> None:
        """Download the state speed limits."""
        await self.fetch_to_store_with_cache(
            PFB_PUBLIC_DOCUMENTS_URL, "state_fips_speed.csv"
        )

    async def download_city_speed_limits(self) -> None:
        """Download the city speed limits."""
        await self.fetch_to_store_with_cache(
            PFB_PUBLIC_DOCUMENTS_URL, "city_fips_speed.csv"
        )

    async def download_census_waterblocks(self) -> None:
        """Download the census waterblocks."""
        waterblock_zip = "censuswaterblocks.zip"
        waterblock_csv = "censuswaterblocks.csv"

        # If the zip file is cached and the csv file is stored, there is nothing to do.
        if self.is_cached(waterblock_zip) and self._is_stored(waterblock_csv):
            return

        # Otherwise fetch the zip file to the cache and the store.
        await self.fetch_to_store_with_cache(PFB_PUBLIC_DOCUMENTS_URL, waterblock_zip)

        # Unzip it in the store and delete the zip file.
        utils.unzip(self.store.prefix / waterblock_zip, self.store.prefix)

    async def download_lodes_data(
        self,
        state: str,
        year: int,
    ) -> None:
        """Download employment data from the US census website: https://lehd.ces.census.gov/."""
        lehd_url = f"https://lehd.ces.census.gov/data/lodes/LODES7/{state.lower()}/od"

        for part in ["main", "aux"]:
            lehd_gz = f"{state.lower()}_od_{part.lower()}_JT00_{year}.csv.gz"
            lehd_csv = f"{state.lower()}_od_{part.lower()}_JT00_{year}.csv"

            # If the gz file is cached and the csv file is stored, there is nothing to do.
            if self.is_cached(lehd_gz) and self._is_stored(lehd_csv):
                return

            # Otherwise fetch the gz file to the cache and the store.
            await self.fetch_to_store_with_cache(lehd_url, lehd_gz)

            # Gunzip it in the store and delete the gz file.
            utils.gunzip(self.store.prefix / lehd_gz, self.store.prefix / lehd_csv)

    async def download_2010_census_blocks(self, fips: str) -> None:
        """Download a 2010 census tabulation block code for a specific state."""
        tabblk2010_url = f"{TIGER_URL}/TIGER2010BLKPOPHU"
        tabblk2010_zip = f"tabblock2010_{fips}_pophu.zip"
        logger.info(f"{tabblk2010_zip=}")

        # Check the cache.
        if self.is_cached(tabblk2010_zip):
            logger.info("is cached")
            await self.copy_to_store(tabblk2010_zip)
            logger.info("is stored")
        else:
            logger.info("was not cached")
            # Otherwise fetch the gz file to the cache and the store.
            # await self.fetch_to_store_with_cache(tabblk2010_url, tabblk2010_zip)
            async with aiohttp.ClientSession() as session:
                logger.info("initialize download")
                await downloader.download_2010_census_blocks(
                    session, self.store.prefix, fips
                )
                logger.info("download complete")
            await self.cache.put_async(
                tabblk2010_zip, self.store.prefix / tabblk2010_zip
            )

        # Unzip and rename the tabulation block files to "population".
        utils.prepare_census_blocks(
            self.store.prefix / tabblk2010_zip, self.store.prefix
        )
