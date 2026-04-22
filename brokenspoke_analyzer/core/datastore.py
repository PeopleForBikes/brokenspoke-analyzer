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
    from_url,
)

from brokenspoke_analyzer.core import (
    datasource,
    downloader,
    file_utils,
    utils,
)

if TYPE_CHECKING:
    from obstore.store import ObjectStore


CHUNK_SIZE = 5 * 1024 * 1024  # 5MB


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
    CUSTOM = 2


class BNADataStore:
    """Define the BNA data store."""

    def __init__(
        self,
        path: pathlib.Path,
        cache_type: CacheType,
        *,
        mirror: typing.Optional[str] = None,
        custom_dir: typing.Optional[pathlib.Path] = None,
    ):
        """
        Initialize the BNA data store.

        This will create or load the data and the cache stores.

        The data store is ALWAYS a local directory.
        The cache store is the user cache directory, whose location varies
        depending on the OS. It however be overridden to be a custom location if
        needed.

        If a mirror is specified, it is used instead of the original URL.

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
                url = f"file://{file_utils.get_user_cache_dir()}"
            case CacheType.CUSTOM:
                if not custom_dir:
                    raise ValueError("a custom directory must be specified")
                url = f"file://{custom_dir}"
        self.cache = from_url(url, client_options=client_options)  # type: ignore

        # Set the mirror if any was provided.
        self.mirror = mirror

    def is_cached(self, path: str) -> bool:
        """Check whether a file already exists in the cache store."""
        return exists(self.cache, path)

    def is_stored(self, path: str) -> bool:
        """Check whether a file already exists in the data store."""
        return exists(self.store, path)

    async def copy_to_store(
        self, path: str, destination: typing.Optional[str] = None
    ) -> None:
        """Copy a file from the cache to the store."""
        if not exists(self.cache, path):
            raise FileNotFoundError(f"{path} was not found in the cache")

        # Change the destination path if we do not want it to match the source path.
        destination_path = destination if destination else path

        # Copy the file if it does not already exist in the store.
        if exists(self.store, destination_path):
            return
        res = await self.cache.get_async(path)
        await self.store.put_async(destination_path, res)

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

    async def fetch(
        self,
        session: aiohttp.ClientSession,
        url: str,
        path: str,
        cache_only: bool = False,
    ) -> None:
        """Fetch a file from a URL."""
        await self.fetch_to_cache(session, url, path)
        if not cache_only:
            await self.copy_to_store(path)

    async def fetch_from_source(
        self,
        session: aiohttp.ClientSession,
        source: datasource.SourceAdapter,
        cache_only: bool = False,
    ) -> None:
        """Fetch file(s) from a SourceAdapter."""
        for url in source.urls:
            path = str(source.subpath / url.name)
            await self.fetch_to_cache(session, str(url), path)
            if not cache_only:
                await self.copy_to_store(path, url.name)
        if not cache_only:
            datastore = self.store.prefix
            source.prepare(datastore)
            source.validate(datastore)

    async def download_state_speed_limits(
        self, session: aiohttp.ClientSession, cache_only: bool = False
    ) -> None:
        """Download the state speed limits."""
        s = datasource.StateSpeedLimitAdapter()
        await self.fetch_from_source(session, s, cache_only=cache_only)

    async def download_city_speed_limits(
        self, session: aiohttp.ClientSession, cache_only: bool = False
    ) -> None:
        """Download the city speed limits."""
        s = datasource.CitySpeedLimitAdapter()
        await self.fetch_from_source(session, s)

    async def download_lodes_data(
        self,
        session: aiohttp.ClientSession,
        state_abbrev: str,
        lodes_year: typing.Optional[int] = None,
        cache_only: bool = False,
    ) -> None:
        """Download employment data from the US census website."""
        state_abbrev = state_abbrev.lower()

        # Puerto Rico is part of the US but the US Census Bureau never collected
        # employment data. As a result we are just skipping it.
        if state_abbrev in {"pr"}:
            logger.warning(f"There is no LODES data for the state of '{state_abbrev}'")
            return

        # Autodetect latest LODES year if not specified.
        if not lodes_year:
            lodes_year = await downloader.autodetect_latest_lodes_year(
                session, state_abbrev
            )
        s = datasource.LodesAdapter(state_abbrev, lodes_year, self.mirror)
        await self.fetch_from_source(session, s, cache_only=cache_only)

    async def download_2020_census_blocks(
        self, session: aiohttp.ClientSession, fips: str, cache_only: bool = False
    ) -> None:
        """Download a 2020 census tabulation block code for a specific state."""
        s = datasource.CensusAdapter(fips, self.mirror)
        await self.fetch_from_source(session, s, cache_only=cache_only)

    async def download_osm_data(
        self, session: aiohttp.ClientSession, region: str, cache_only: bool = False
    ) -> pathlib.Path:
        """Retrieve the region file from Geofabrik or BBike."""
        s = datasource.OSMAdapter(region, self.mirror)
        await self.fetch_from_source(session, s, cache_only=cache_only)
        return pathlib.Path(s.urls[0].name)
