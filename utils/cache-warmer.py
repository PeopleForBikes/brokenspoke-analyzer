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

import aiohttp
import rich
from loguru import logger

from brokenspoke_analyzer.cli import root
from brokenspoke_analyzer.core import (
    datastore,
    file_utils,
)
from brokenspoke_analyzer.pyrosm.data import geofabrik

# Ensure DC is considered a US state.
# https://github.com/unitedstates/python-us/issues/67
os.environ["DC_STATEHOOD"] = "1"
import us


async def main():
    """Define the main function."""
    # Disable logging.
    root._verbose_callback(0)

    # Prepare the Rich output.
    console = rich.get_console()

    CACHE_ONLY = True
    bna_store = datastore.BNADataStore(
        pathlib.Path(file_utils.get_user_cache_dir()),
        datastore.CacheType.USER_CACHE,
    )

    # Start the downloads.
    async with aiohttp.ClientSession() as session:
        # Download the single files first.
        console.log("Downloading state speed limits")
        await bna_store.download_state_speed_limits(session, cache_only=CACHE_ONLY)
        console.log("Downloading city speed limits")
        await bna_store.download_city_speed_limits(session, cache_only=CACHE_ONLY)

        # Download the state-specific files.
        for i, (fips, abbr) in enumerate(us.states.mapping("fips", "abbr").items()):
            # Skip US territories.
            # They are part of the US but we don't have any data for them.
            if fips in {"60", "66", "69", "72", "78"}:
                continue
            with console.status(
                f"[{i + 1}/{len(us.states.STATES)}] Processing {abbr} ({fips})"
            ):
                console.log(f"Downloading US Census data for {abbr} ({fips})")
                await bna_store.download_2020_census_blocks(session, fips)
                console.log(f"Downloading LODES data for {abbr} ({fips})")
                await bna_store.download_lodes_data(
                    session, abbr, cache_only=CACHE_ONLY
                )

        # Download the OSM data for the specified regions.
        osm_regions = []
        # Add the US states.
        osm_regions.extend(geofabrik.USA()._sources.keys())

        # Start the downloads.
        for i, region in enumerate(osm_regions):
            with console.status(
                f"[{i + 1}/{len(osm_regions)}] Processing OSM {region}"
            ):
                console.log(f"Downloading OSM data for {region}")
                await bna_store.download_osm_data(
                    session, region, cache_only=CACHE_ONLY
                )


if __name__ == "__main__":
    asyncio.run(main())
