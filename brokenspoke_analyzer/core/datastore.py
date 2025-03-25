"""Define the Datastores."""

from __future__ import annotations

import enum
import pathlib
from collections import abc
from typing import TYPE_CHECKING

import aiohttp
from loguru import logger
from obstore.store import (
    from_url,
)

from brokenspoke_analyzer.core import (
    utils,
)

if TYPE_CHECKING:
    from obstore.store import ObjectStore


CHUNK_SIZE = 5 * 1024 * 1024  # 5MB
PFB_PUBLIC_DOCUMENTS_URL = "https://s3.amazonaws.com/pfb-public-documents"
TIGER_2010_URL = "https://www2.census.gov/geo/tiger/TIGER2010BLKPOPHU"


def exists(store: ObjectStore, path: str) -> bool:
    """
    Check whether a file already exists in a store.

    Example:
        >>> import obstore
        >>> from obstore.store import MemoryStore
        >>> store = MemoryStore()
        >>> exists(store, "does_not_exist.txt")
        False

        >>> with obstore.open_writer(store, "new_file.csv") as writer:
        >>>      writer.write(b"col1,col2,col3")
        >>> exists(store, "new_file.csv")
        True
    """
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

    def __init__(
        self,
        path: pathlib.Path,
        cache_type: CacheType,
        *,
        s3_bucket: str | None = None,
    ):
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
                url = f"file://{path}"
            case CacheType.USER_CACHE:
                url = f"file://{utils.get_user_cache_dir()}"
            case CacheType.AWS_S3:
                url = f"s3://{s3_bucket}"
        self.cache = from_url(url, client_options=client_options)  # type: ignore

    def is_cached(self, path: str) -> bool:
        """Check whether a file already exists in the cache store."""
        return exists(self.cache, path)

    def is_stored(self, path: str) -> bool:
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

    async def fetch_to_cache(
        self, session: aiohttp.ClientSession, url: str, path: str
    ) -> None:
        """Fetch a file into the cache."""
        logger.debug(f"fetching {url}")
        # Check whether the file already exists in the cache.
        if self.is_cached(path):
            logger.debug(f"{path} was cached")
            return

        # If not, download it from the url and store it into the cache data store.
        async with session.get(url) as resp:
            await self.cache.put_async(path, resp.content.iter_chunked(CHUNK_SIZE))

    async def fetch(self, session: aiohttp.ClientSession, url: str, path: str) -> None:
        """Fetch a file from a URL."""
        await self.fetch_to_cache(session, url, path)
        await self.copy_to_store(path)

    async def download_state_speed_limits(self, session: aiohttp.ClientSession) -> None:
        """Download the state speed limits."""
        state_speed_csv = "state_fips_speed.csv"
        url = f"{PFB_PUBLIC_DOCUMENTS_URL}/{state_speed_csv}"
        await self.fetch(session, url, state_speed_csv)

    async def download_city_speed_limits(self, session: aiohttp.ClientSession) -> None:
        """Download the city speed limits."""
        city_speed_csv = "city_fips_speed.csv"
        url = f"{PFB_PUBLIC_DOCUMENTS_URL}/{city_speed_csv}"
        await self.fetch(session, url, city_speed_csv)

    async def download_census_waterblocks(self, session: aiohttp.ClientSession) -> None:
        """Download the census waterblocks."""
        waterblock_zip = "censuswaterblocks.zip"
        url = f"{PFB_PUBLIC_DOCUMENTS_URL}/{waterblock_zip}"
        await self.fetch(session, url, waterblock_zip)

        # Unzip it in the store and delete the zip file.
        utils.unzip(self.store.prefix / waterblock_zip, self.store.prefix)

    async def download_lodes_data(
        self,
        session: aiohttp.ClientSession,
        state: str,
        year: int,
    ) -> None:
        """
        Download employment data from the US census website: https://lehd.ces.census.gov/.

        LODES stands for LEHD Origin-Destination Employment Statistics.

        OD means Origin-Data, which represents the jobs that are associated with
        both a home census block and a work census block.

        The filename is composed of the following parts:
        ``[ST]_od_[PART]_[TYPE]_[YEAR].csv.gz``.

        * [ST] = lowercase, 2-letter postal code for a chosen state
        * [PART] = Part of the state file, can have a value of either "main" or
            "aux".
            Complimentary parts of the state file, the main part includes jobs with
            both workplace and residence in the state and the aux part includes jobs
            with the workplace in the state and the residence outside of the state.
        * [TYPE] = Job Type, can have a value of "JT00 for All Jobs, "JT01" for
            Primary Jobs, "JT02" for All Private Jobs, "JT03" for Private Primary
            Jobs, "JT04" for All Federal Jobs, or "JT05" for Federal Primary Jobs.
        * [YEAR] = Year of job data. Can have the value of 2002-2020 for most
            states.

        As an example, the main OD file of Primary Jobs in 2007 for California would
        be the file: ``ca_od_main_JTO1_2007.csv.gz``.

        More information about the formast can be found on the website:
        https://lehd.ces.census.gov/data/#lodes.
        """
        lehd_url = f"https://lehd.ces.census.gov/data/lodes/LODES7/{state.lower()}/od"

        for part in ["main", "aux"]:
            lehd_gz = f"{state.lower()}_od_{part.lower()}_JT00_{year}.csv.gz"
            lehd_csv = f"{state.lower()}_od_{part.lower()}_JT00_{year}.csv"
            url = f"{lehd_url}/{lehd_gz}"
            await self.fetch(session, url, lehd_gz)

            # Gunzip it in the store and delete the gz file.
            utils.gunzip(self.store.prefix / lehd_gz, self.store.prefix / lehd_csv)

    async def download_2010_census_blocks(
        self, session: aiohttp.ClientSession, fips: str
    ) -> None:
        """Download a 2010 census tabulation block code for a specific state."""
        tabblk2010_zip = f"tabblock2010_{fips}_pophu.zip"
        url = f"{TIGER_2010_URL}/{tabblk2010_zip}"
        await self.fetch(session, url, tabblk2010_zip)

        # Unzip and rename the tabulation block files to "population".
        utils.prepare_census_blocks(
            self.store.prefix / tabblk2010_zip, self.store.prefix
        )
