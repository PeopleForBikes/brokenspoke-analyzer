"""Test module."""

import pathlib

import pytest
from loguru import logger

from brokenspoke_analyzer.core import datastore
from brokenspoke_analyzer.pyrosm import data

logger.enable("brokenspoke_analyzer")


def test_truthy():
    """Dummy test."""
    assert True


# def test_available_regions():
#     """Test available region."""
#     regions = []
#     for region in data.available["regions"]:
#         regions.extend(data.available["regions"][region])
#     subregions = []
#     for subregion in data.available["subregions"]:
#         subregions.extend(data.available["subregions"][subregion])
#     _all = []
#     _all.extend(regions)
#     _all.extend(subregions)
#     _all.extend(data.available["cities"])
#     # print(f"{len(_all)=}")
#     # print(f"{_all=}")
#     _all.sort()
#     for i, v in enumerate(_all):
#         spacer = "   * - " if i % 2 == 0 else "     - "
#         print(f"{spacer}{v.title()}")


# @pytest.mark.asyncio
# async def test_datastore():
#     """Test some features of the BNA Data Store."""
#     bna_store = datastore.BNADataStore(
#         pathlib.Path(
#             "/Users/rgreinhofer/projects/PeopleForBikes/brokenspoke-analyzer/data/test"
#         ),
#         datastore.CacheType.USER_CACHE,
#     )
#     await bna_store.download_census_waterblocks()
#     await bna_store.download_lodes_data("ma", 2019)
#     await bna_store.download_2010_census_blocks("25")
