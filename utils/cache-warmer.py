"""
Pre-populate the analyzer cache.

This is a small utility to warm-up you cache with US data.

The cache will be populated with the following items:
    - US 2020 Census blocks
    - US 2022 LODES data (employment)
    - US Water blocks
    - US State speed limits
    - US City speed limits

From the root of this repository run:
```bash
uv run python utils/cache-warmer.py
```
"""

from __future__ import annotations

import asyncio
import os
import pathlib
from typing import Annotated

import aiohttp
import rich
import typer
from pyrosm import geofabrik

from brokenspoke_analyzer.cli import (
    common,
    root,
)
from brokenspoke_analyzer.core import (
    datasource,
    datastore,
    exporter,
    file_utils,
)

# Ensure DC is considered a US state.
# https://github.com/unitedstates/python-us/issues/67
os.environ["DC_STATEHOOD"] = "1"
import us

ClearOsm = Annotated[bool, typer.Option(help="Delete OSM data before upload.")]

app = typer.Typer(no_args_is_help=True)


async def _run_downloads(
    bna_store: datastore.BNADataStore,
    *,
    cache_only: bool = True,
    clear_osm: bool = False,
) -> None:
    """Run the download pipeline using the provided BNADataStore."""
    console = rich.get_console()

    async with aiohttp.ClientSession() as session:
        console.log("Downloading state speed limits")
        await bna_store.download_state_speed_limits(session, cache_only=cache_only)
        console.log("Downloading city speed limits")
        await bna_store.download_city_speed_limits(session, cache_only=cache_only)

        for i, (fips, abbr) in enumerate(us.states.mapping("fips", "abbr").items()):
            if fips in {"60", "66", "69", "72", "78"}:
                continue
            with console.status(
                f"[{i + 1}/{len(us.states.STATES)}] Processing {abbr} ({fips})",
            ):
                console.log(f"Downloading US Census data for {abbr} ({fips})")
                await bna_store.download_2020_census_blocks(
                    session, fips, cache_only=cache_only
                )
                console.log(f"Downloading LODES data for {abbr} ({fips})")
                await bna_store.download_lodes_data(
                    session,
                    abbr,
                    cache_only=cache_only,
                )

        osm_regions = []
        osm_regions.extend(geofabrik.USA()._sources.keys())
        if clear_osm:
            console.log("Deleting existing OSM data from cache")
            await bna_store.clear_source(
                datasource.OSMAdapter("all"), cache_only=cache_only
            )
        for i, region in enumerate(osm_regions):
            with console.status(
                f"[{i + 1}/{len(osm_regions)}] Processing OSM {region}",
            ):
                console.log(f"Downloading OSM data for {region}")
                await bna_store.download_osm_data(
                    session,
                    region,
                    cache_only=cache_only,
                )


def _build_store(mirror: str | None) -> datastore.BNADataStore:
    return datastore.BNADataStore(
        pathlib.Path(file_utils.get_user_cache_dir()),
        datastore.CacheType.USER_CACHE,
        mirror=mirror,
    )


def _build_s3_store(bucket: str, mirror: str | None) -> datastore.BNADataStore:
    store = _build_store(mirror)
    store.cache = exporter.create_s3_store(bucket)
    return store


@app.command("local")
def local(
    mirror: common.Mirror = None,
    *,
    clear_osm: ClearOsm = False,
) -> None:
    """Warm the local user cache using the existing cache-warmer pipeline."""
    root._verbose_callback(0)
    bna_store = _build_store(mirror)
    asyncio.run(_run_downloads(bna_store, cache_only=True, clear_osm=clear_osm))


@app.command("s3")
def s3(
    bucket: Annotated[str, typer.Option(help="Target S3 bucket name.")],
    mirror: common.Mirror = None,
    *,
    clear_osm: ClearOsm = False,
) -> None:
    """Warm an S3 bucket directly from upstream artifact sources."""
    root._verbose_callback(0)
    bna_store = _build_s3_store(bucket, mirror)
    asyncio.run(_run_downloads(bna_store, cache_only=True, clear_osm=clear_osm))


def main() -> None:
    """Run the default cache-warmer behavior for backwards compatibility."""
    root._verbose_callback(0)
    bna_store = _build_store(mirror=None)
    asyncio.run(_run_downloads(bna_store, cache_only=True))


if __name__ == "__main__":
    app()
