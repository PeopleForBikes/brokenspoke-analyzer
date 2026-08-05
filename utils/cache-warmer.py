"""
Pre-populate the analyzer cache.

This is a small utility to warm-up you cache with US data.

The cache will be populated with the following items:
    - US 2020 Census blocks
    - US 2022 LODES data (employment)
    - US 2025 Census Places
    - US 2025 Census County Subdivisions
    - US Water blocks
    - US State speed limits
    - US City speed limits
    - OSM data for countries we process

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
import pycountry
import rich
import typer
from pyrosm.data import geofabrik

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

        # Download US Census data.
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
                console.log(f"Downloading US Census Place for {abbr} ({fips})")
                place = datasource.PlaceAdapter(2025, fips)
                await bna_store.fetch_from_source(session, place, cache_only=cache_only)
                console.log(
                    f"Downloading US Census County Subdivisions for {abbr} ({fips})"
                )
                cousub = datasource.CountySubdivisionAdapter(2025, fips)
                await bna_store.fetch_from_source(
                    session, cousub, cache_only=cache_only
                )

        # Download Worldpop data.
        for i, country in enumerate(pycountry.countries):
            with console.status(
                f"[{i + 1}/{len(pycountry.countries)}] "
                f"Downloading Worldpop data for {country.name}"
            ):
                console.log(f"Downloading Worldpop data for {country.name}")
                try:
                    await bna_store.download_worldpop(
                        session, country.alpha_3, 2026, cache_only=cache_only
                    )
                except aiohttp.ClientResponseError as e:
                    console.log(
                        f"Skipping Worldpop data for {country.name}: {e.message}"
                    )

        # Download OSM data.
        osm_regions = []
        osm_regions.extend(geofabrik.USA()._sources.keys())
        osm_regions.extend(geofabrik.Europe()._sources.keys())
        osm_regions.extend(geofabrik.Asia()._sources.keys())
        osm_regions.extend(geofabrik.AustraliaOceania()._sources.keys())
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

                # Skip regions with known issues.
                if region in {
                    "east-timor",
                    "france",
                    "georgia",
                    "germany",
                    "ile-de-clipperton",
                    "pitcairn-islands",
                    "polynesie-francaise",
                    "russia",
                    "wallis-et-futuna",
                }:
                    console.log(f"Skipping {region} due to ambiguity/issues")
                    continue

                # Fetch the region file.
                try:
                    await bna_store.download_osm_data(
                        session,
                        region,
                        cache_only=cache_only,
                    )
                except asyncio.TimeoutError as e:  # noqa: UP041
                    console.log(f"Timeout downloading OSM data for {region}: {e}")
                except (ValueError, aiohttp.ClientResponseError) as e:
                    console.log(f"Error downloading OSM data for {region}: {e}")


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
