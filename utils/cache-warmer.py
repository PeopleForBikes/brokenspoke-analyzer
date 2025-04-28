"""
Pre-populate the analyzer cache.

This is a small utility to warm-up you cache with US data.

The cache will be populated with the following items:
    - US 2010 Census blocks
    - US 2019 LODES data (employment)
    - US Water blocks
    - US State speed limits
    - US City speed limits
"""

import asyncio
import os
import pathlib

import aiohttp
import us
from loguru import logger

from brokenspoke_analyzer.core import (
    datastore,
    utils,
)


async def main():
    """Define the main function."""
    bna_store = datastore.BNADataStore(
        pathlib.Path(utils.get_user_cache_dir()),
        # datastore.CacheType.USER_CACHE,
        datastore.CacheType.AWS_S3,
        s3_bucket=os.getenv("BNA_CACHE_AWS_S3_BUCKET"),
    )

    async with aiohttp.ClientSession() as session:
        await bna_store.download_census_waterblocks(session)
        await bna_store.download_state_speed_limits(session)
        await bna_store.download_city_speed_limits(session)
        for fips, abbr in us.states.mapping("fips", "abbr").items():
            logger.info(f"Downloading LODES data for {abbr} ({fips})")
            lehd_url = (
                f"https://lehd.ces.census.gov/data/lodes/LODES7/{abbr.lower()}/od"
            )
            for part in ["main", "aux"]:
                lehd_gz = f"{abbr.lower()}_od_{part.lower()}_JT00_2019.csv.gz"
                url = f"{lehd_url}/{lehd_gz}"
                await bna_store.fetch_to_cache(session, url, lehd_gz)
            logger.info(f"Downloading census data for {abbr} ({fips})")
            tabblk2010_zip = f"tabblock2010_{fips}_pophu.zip"
            url = (
                f"https://www2.census.gov/geo/tiger/TIGER2010BLKPOPHU/{tabblk2010_zip}"
            )
            await bna_store.fetch_to_cache(session, url, tabblk2010_zip)


if __name__ == "__main__":
    asyncio.run(main())
