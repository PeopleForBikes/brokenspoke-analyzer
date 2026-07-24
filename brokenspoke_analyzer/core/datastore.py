"""Define the Datastores."""

from __future__ import annotations

import enum
import logging
import pathlib
from typing import TYPE_CHECKING

import aiohttp
from loguru import logger
from obstore import exceptions as obstore_exceptions
from obstore.store import (
    from_url,
)
from tenacity import (
    Retrying,
    before_log,
    stop_after_attempt,
)

from brokenspoke_analyzer.core import (
    analysis,
    datasource,
    downloader,
    file_utils,
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
    """Define the types of caching strategies available to retrieve store artifacts."""

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
        mirror: str | None = None,
        custom_dir: pathlib.Path | None = None,
    ) -> None:
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
        self.store = from_url(
            f"file://{path}",
            client_options=client_options,
            mkdir=True,
        )  # ty:ignore[no-matching-overload]

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
        self.cache = from_url(url, client_options=client_options)  # ty:ignore[no-matching-overload]

        # Set the mirror if any was provided.
        self.mirror = mirror

    def is_cached(self, path: str) -> bool:
        """Check whether a file already exists in the cache store."""
        return exists(self.cache, path)

    def is_stored(self, path: str) -> bool:
        """Check whether a file already exists in the data store."""
        return exists(self.store, path)

    async def copy_to_store(
        self,
        path: str,
        destination: str | None = None,
    ) -> None:
        """Copy a file from the cache to the store."""
        if not self.is_cached(path):
            raise FileNotFoundError(f"{path} was not found in the cache")

        # Change the destination path if we do not want it to match the source path.
        destination_path = destination or path

        # Copy the file if it does not already exist in the store.
        if self.is_stored(destination_path):
            return
        res = await self.cache.get_async(path)
        await self.store.put_async(destination_path, res)

    async def _cleanup_partial_cache(self, path: str) -> None:
        """Delete a partially written cache artifact if the cache store supports it."""
        delete_async = getattr(self.cache, "delete_async", None)
        if callable(delete_async):
            try:
                await delete_async(path)
            except FileNotFoundError:
                return
            except (obstore_exceptions.BaseError, OSError) as exc:
                logger.warning(
                    "failed to delete partial cache object %s: %s",
                    path,
                    exc,
                )
            return

        delete_sync = getattr(self.cache, "delete", None)
        if callable(delete_sync):
            try:
                delete_sync(path)
            except FileNotFoundError:
                return
            except (obstore_exceptions.BaseError, OSError) as exc:
                logger.warning(
                    "failed to delete partial cache object %s: %s",
                    path,
                    exc,
                )
            return

        logger.warning(
            "cache store does not support delete; partial artifact may remain: %s",
            path,
        )

    async def fetch_to_cache(
        self,
        session: aiohttp.ClientSession,
        url: str,
        path: str,
    ) -> None:
        """Fetch a file into the cache."""
        logger.debug(f"fetching {url}")
        # Check whether the file already exists in the cache.
        if self.is_cached(path):
            logger.debug(f"{path} was cached")
            return

        # If not, download it from the url and store it into the cache data store.
        async with session.get(url) as resp:
            resp.raise_for_status()
            try:
                await self.cache.put_async(path, resp.content.iter_chunked(CHUNK_SIZE))
            except (
                aiohttp.ClientError,
                obstore_exceptions.BaseError,
                OSError,
                RuntimeError,
            ):
                await self._cleanup_partial_cache(path)
                raise

    async def fetch(
        self,
        session: aiohttp.ClientSession,
        url: str,
        path: str,
        *,
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
        *,
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

    async def clear_source(
        self,
        source: datasource.SourceAdapter,
        *,
        cache_only: bool = False,
    ) -> None:
        """Clear file(s) from a SourceAdapter."""
        await self.cache.delete_async(source.subpath)
        if not cache_only:
            await self.store.delete_async(source.subpath)

    async def put_file(
        self,
        path: str,
        file: pathlib.Path,
        *,
        cache_only: bool = False,
    ) -> None:
        """Put a file into the store."""
        logger.debug(f"Putting file {path} into the BNA store from {file}")

        # Check whether the file already exists in the cache.
        if not self.is_cached(path):
            logger.debug(f"Putting file {file} into the cache at {path}")
            await self.cache.put_async(path, file)
        else:
            logger.debug(f"{path} was cached")

        # Put the file in the store if needed.
        if not cache_only:
            logger.debug(f"Putting file {file} into the store at {path}")
            await self.copy_to_store(path)

    async def download_state_speed_limits(
        self,
        session: aiohttp.ClientSession,
        *,
        cache_only: bool = False,
    ) -> None:
        """Download the state speed limits."""
        s = datasource.StateSpeedLimitAdapter()
        await self.fetch_from_source(session, s, cache_only=cache_only)

    async def download_city_speed_limits(
        self,
        session: aiohttp.ClientSession,
        *,
        cache_only: bool = False,
    ) -> None:
        """Download the city speed limits."""
        s = datasource.CitySpeedLimitAdapter()
        await self.fetch_from_source(session, s, cache_only=cache_only)

    async def download_lodes_data(
        self,
        session: aiohttp.ClientSession,
        state_abbrev: str,
        lodes_year: int | None = None,
        *,
        cache_only: bool = False,
    ) -> None:
        """Download employment data from the US census website."""
        state_abbrev = state_abbrev.lower()

        # Puerto Rico is part of the US but the US Census Bureau never collected
        # employment data. As a result we are just skipping it.
        if state_abbrev == "pr":
            logger.warning(f"There is no LODES data for the state of '{state_abbrev}'")
            return

        # Autodetect latest LODES year if not specified.
        if not lodes_year:
            lodes_year = await downloader.autodetect_latest_lodes_year(
                session,
                state_abbrev,
            )
        s = datasource.LodesAdapter(state_abbrev, lodes_year, self.mirror)
        await self.fetch_from_source(session, s, cache_only=cache_only)

    async def download_2020_census_blocks(
        self,
        session: aiohttp.ClientSession,
        fips: str,
        *,
        cache_only: bool = False,
    ) -> None:
        """Download a 2020 census tabulation block code for a specific state."""
        s = datasource.CensusAdapter(fips, self.mirror)
        await self.fetch_from_source(session, s, cache_only=cache_only)

    async def download_worldpop(
        self,
        session: aiohttp.ClientSession,
        country: str,
        year: str = "2026",
        *,
        cache_only: bool = False,
    ) -> None:
        """
        Download a WorldPop 1km resolution geoTIFF for a specific country.

        Default year to 2026 to match current year
        """
        s = datasource.WorldPopAdapter(country, year, self.mirror)
        await self.fetch_from_source(session, s, cache_only=cache_only)

    async def download_osm_data(
        self,
        session: aiohttp.ClientSession,
        region: str,
        *,
        cache_only: bool = False,
    ) -> pathlib.Path:
        """Retrieve the region file from Geofabrik or BBike."""
        s = datasource.OSMAdapter(region, self.mirror)
        await self.fetch_from_source(session, s, cache_only=cache_only)
        return pathlib.Path(s.urls[0].name)

    async def download_city_boundaries(
        self,
        retries: int,
        structured_query: dict[str, str],
        text_query: str,
        slug: str,
        fips_code: str | None = None,
    ) -> None:
        """Retrieve the city boundaries file."""
        # Create retrier instance to use for all direct downloads.
        retryer = Retrying(
            stop=stop_after_attempt(retries),
            reraise=True,
            before=before_log(logger, logging.DEBUG),
        )

        # Retrieve the boundary file.
        extensions = {".geojson", ".cpg", ".dbf", ".prj", ".shp", ".shx"}
        boundary_file_name_stem = pathlib.Path(slug)
        if all(
            self.is_cached(str(boundary_file_name_stem.with_suffix(ext)))
            for ext in extensions
        ):
            logger.debug("Boundary files are cached. Copying them to the store...")
            for ext in extensions:
                await self.copy_to_store(str(boundary_file_name_stem.with_suffix(ext)))
            return

        # Retrieve the city boundaries.
        boundary_gdf = retryer(
            analysis.retrieve_city_boundaries,
            structured_query=structured_query,
            text_query=text_query,
            fips_code=fips_code,
        )

        # Prepare the "boundaries" folder in the cache if needed.
        prefix = self.cache.prefix / "boundaries"
        prefix.mkdir(parents=True, exist_ok=True)
        logger.debug(f"{prefix=}")

        # Prepare the shapefile.
        boundary_file = prefix / boundary_file_name_stem
        boundary_shapefile = boundary_file.with_suffix(".shp")
        logger.debug(f"Copying boundary file to {boundary_shapefile}")
        boundary_gdf.to_file(boundary_shapefile, encoding="utf-8")

        # Preparing the geojosn file.
        boundary_geojson_file = boundary_file.with_suffix(".geojson")
        logger.debug(f"Copying boundary geojson file to {boundary_geojson_file}")
        boundary_gdf.to_file(boundary_geojson_file)

        # Put the files into the store.
        for ext in extensions:
            await self.put_file(
                str(boundary_file_name_stem.with_suffix(ext)),
                prefix / boundary_file.with_suffix(ext),
            )
